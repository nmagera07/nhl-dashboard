"""
Tools the model can call: read-only queries against the dashboard API and
the playoff-odds model's "what if" simulations.

The model decides *which* question to ask; the numbers always come from
here (the dashboard's data and the deterministic simulation), never from the
model's own arithmetic. Results are compact on purpose: every tool round
resends the conversation, and free tiers cap tokens per minute.
"""

import asyncio
import inspect
import json
import logging
import math
from typing import Any

import httpx

from . import compact
from .dashboard import DashboardClient, DashboardUnavailable

logger = logging.getLogger(__name__)

SCOPES = ["league", "Eastern", "Western", "Atlantic", "Metropolitan", "Central", "Pacific"]
TEAM = {"type": "string", "description": "Team abbreviation, e.g. PIT, TOR, VGK."}


def _fn(name, description, properties=None, required=()):
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {"type": "object", "properties": properties or {}, "required": list(required)},
        },
    }


TOOLS = [
    _fn("get_standings", "Current standings with playoff spots and playoff odds for the league, a conference, or a division.",
        {"scope": {"type": "string", "enum": SCOPES, "description": "Defaults to league."}}),
    _fn("get_team", "One team's full season: record, ranks, goal and xG numbers, playoff odds, and its top players.",
        {"team": TEAM}, ["team"]),
    _fn("get_playoff_odds", "A team's playoff odds now, a week ago, at the start of the season, and its high and low this season.",
        {"team": TEAM}, ["team"]),
    _fn("get_schedule", "A team's next games, each opponent's strength rank (1 = strongest), and games left.",
        {"team": TEAM, "games": {"type": "integer", "minimum": 1, "maximum": 20, "description": "How many upcoming games. Default 5."}},
        ["team"]),
    _fn("explain_odds",
        "Why the playoff-odds model rates a team the way it does: its rating split into this season's goals, this season's "
        "expected goals (xG), and last season's carryover, plus how its remaining schedule helps or hurts. With an opponent, "
        "also compares the two and gives the model's win probability for their next meeting. Use for any 'why are their odds "
        "X', 'why is the model high/low on them', or 'why is X favored over Y' question.",
        {"team": TEAM, "opponent": {"type": "string", "description": "Optional second team to compare, e.g. NYR."}},
        ["team"]),
    _fn("rank_schedule_strength", "Every team ranked from easiest to hardest remaining schedule, by average opponent strength.",
        {"conference": {"type": "string", "enum": ["Eastern", "Western"], "description": "Optional: only one conference."}}),
    _fn("simulate_scenario",
        "Simulate the rest of the season with the playoff-odds model if a team goes a given record over its next games. "
        "Returns its playoff odds and projected points with and without the scenario. Use for any 'what if' question.",
        {"team": TEAM,
         "games": {"type": "integer", "minimum": 1, "maximum": 30, "description": "How many of its next games."},
         "wins": {"type": "integer", "minimum": 0, "maximum": 30},
         "ot_losses": {"type": "integer", "minimum": 0, "maximum": 30, "description": "Losses in overtime/shootout (still a point). Default 0."}},
        ["team", "games", "wins"]),
    _fn("simulate_roster_change",
        "Simulate a hypothetical trade or a player missing the rest of the season with the playoff-odds model: each "
        "affected team's playoff odds with and without the move, from the player's value in goals/game. Use for "
        "'what if they traded X', 'what if X goes to Y', 'X for Y', or 'what if X is out for the season'. Skaters only.",
        {"player": {"type": "string", "description": "The player who moves, e.g. 'Dylan Larkin'."},
         "to_team": {"type": "string", "description": "Optional team he goes to. Leave out if unknown or he's just out."},
         "player_back": {"type": "string", "description": "Optional player coming back in the trade (he joins the first player's team)."}},
        ["player"]),
    _fn("playoff_path",
        "What a team needs: its playoff odds for every possible record over its next games (e.g. 0-10 up to 10-0), from the model.",
        {"team": TEAM, "games": {"type": "integer", "minimum": 1, "maximum": 15, "description": "Default 10."}},
        ["team"]),
    _fn("get_recent_results", "A team's most recent results (up to its last 5 games): scores, opponents, W/L/OT, and any game in progress.",
        {"team": TEAM}, ["team"]),
    _fn("get_game",
        "One game's box score (scoring summary, three stars, team and player stats). Finds the team's most recent game, "
        "or the one on a date, or the latest one against an opponent.",
        {"team": TEAM,
         "date": {"type": "string", "description": "Optional, YYYY-MM-DD."},
         "opponent": {"type": "string", "description": "Optional opponent abbreviation, e.g. CBJ."}},
        ["team"]),
    _fn("find_player", "Look up a player by name: season stats, career, and 5-on-5 advanced stats.",
        {"name": {"type": "string", "description": "Full or last name, e.g. 'Crosby'."}}, ["name"]),
    _fn("get_injuries",
        "The current injury report (ESPN): each injured player's status (injured reserve, out, day-to-day), injury, "
        "expected return, and a short note. Ask about one player by name (searches every team, so no need to know his "
        "team), one team, or the whole league.",
        {"player": {"type": "string", "description": "Optional player name, e.g. 'Drew Helleson'."},
         "team": {"type": "string", "description": "Optional team abbreviation, e.g. PIT."}}),
    _fn("get_news",
        "Recent NHL headlines (NHL.com, ESPN, Sportsnet) with short summaries, plus recent transactions (signings, "
        "trades, recalls, IR moves). For one team, or the whole league if none is given.",
        {"team": {"type": "string", "description": "Optional team abbreviation, e.g. PIT."}}),
    _fn("get_leaders", "League leaders: points, goals, or goalie wins.",
        {"category": {"type": "string", "enum": ["points", "goals", "goalie_wins"], "description": "Default: all three."}}),
]

# What the chat shows while a tool runs, and the evidence label after.
LABELS = {
    "get_standings": ("Checking the standings", "Current standings"),
    "get_team": ("Looking up the team", "Team season and roster"),
    "get_playoff_odds": ("Checking playoff odds history", "Playoff odds history"),
    "get_schedule": ("Checking the schedule", "Remaining schedule"),
    "explain_odds": ("Breaking down the odds", "Playoff-odds model breakdown"),
    "rank_schedule_strength": ("Ranking remaining schedules", "Strength of remaining schedules"),
    "simulate_scenario": ("Simulating 2,000 seasons", "Season simulation (playoff-odds model)"),
    "simulate_roster_change": ("Simulating the trade", "Season simulation with the roster change (playoff-odds model)"),
    "playoff_path": ("Simulating every record", "Season simulation (playoff-odds model)"),
    "get_recent_results": ("Checking recent results", "Recent results"),
    "get_game": ("Pulling up the box score", "NHL game box score"),
    "find_player": ("Looking up the player", "Player profile and stats"),
    "get_leaders": ("Checking the league leaders", "League leaders"),
    "get_injuries": ("Checking the injury report", "Injury report (ESPN)"),
    "get_news": ("Checking the latest news", "Headlines and transactions"),
}

MAX_RESULT_CHARS = 6000


class ToolError(Exception):
    """A tool couldn't answer (bad arguments, unknown team or player)."""


class ToolRunner:
    """Runs tool calls for one question, memoizing dashboard reads."""

    def __init__(self, dashboard: DashboardClient):
        self.dashboard = dashboard
        self._memo: dict[str, Any] = {}

    async def _get(self, path: str) -> Any:
        if path not in self._memo:
            self._memo[path] = await self.dashboard._get(path)
        return self._memo[path]

    async def run(self, name: str, arguments: str | dict) -> str:
        """Run one tool call; always returns JSON text for the model (errors included)."""
        try:
            args = json.loads(arguments or "{}") if isinstance(arguments, str) else dict(arguments or {})
            handler = getattr(self, f"_tool_{name}", None)
            if handler is None:
                raise ToolError(f"Unknown tool '{name}'.")
            # Small models sometimes send junk keys (Groq's gpt-oss called
            # get_leaders with {"": ""}); drop what the tool doesn't take.
            accepted = inspect.signature(handler).parameters
            extra = [k for k in args if k not in accepted]
            if extra:
                logger.info("Ignoring unexpected arguments to %s: %s", name, extra)
                args = {k: v for k, v in args.items() if k in accepted}
            result = await handler(**args)
        except (ToolError, TypeError, ValueError) as exc:  # bad arguments from the model
            result = {"error": str(exc)}
        except DashboardUnavailable:
            result = {"error": "The dashboard data is temporarily unavailable."}
        text = json.dumps(result, default=str, separators=(",", ":"))
        if len(text) > MAX_RESULT_CHARS:
            logger.warning("Tool %s returned %d chars; truncating", name, len(text))
            text = text[:MAX_RESULT_CHARS] + '..."(truncated)"'
        return text

    # --- helpers -------------------------------------------------------------

    async def _standings(self):
        return await self._get("/standings/latest")

    async def _team(self, team: str) -> str:
        """Accept 'PIT', 'pit', 'Penguins', or 'Pittsburgh Penguins'."""
        value = (team or "").strip().lower()
        for row in await self._standings():
            names = {row.get("team_abbrev", "").lower(), (row.get("team_name") or "").lower(), (row.get("common_name") or "").lower()}
            if value in names or (len(value) > 3 and value in (row.get("team_name") or "").lower()):
                return row["team_abbrev"]
        raise ToolError(f"Unknown team '{team}'. Use a 3-letter abbreviation like PIT.")

    async def _sim_inputs(self):
        return await self._get("/season-sim")

    # --- tools ---------------------------------------------------------------

    async def _tool_get_standings(self, scope: str = "league"):
        standings, odds = await asyncio.gather(self._standings(), self._get("/playoff-odds"))
        by_team, as_of = compact.odds_by_team(standings, odds)
        if scope not in SCOPES:
            raise ToolError(f"scope must be one of {SCOPES}")
        rows = [r for r in standings if scope == "league"
                or (r.get("conference") or "").startswith(scope) or r.get("division") == scope]
        rows.sort(key=lambda r: r.get("league_sequence") or 99)
        return {
            "as_of": str(standings[0]["snapshot_date"]) if standings else None,
            "playoff_odds_as_of": as_of,
            "teams": [{k: v for k, v in compact.standing_row(r, by_team.get(r.get("team_abbrev"))).items()
                       if k in compact.LEAGUE_ROW_FIELDS + ("xgoals_for_pct",)} for r in rows],
        }

    async def _tool_get_team(self, team: str):
        abbrev = await self._team(team)
        standings, roster, odds = await asyncio.gather(
            self._standings(), self._get(f"/teams/{abbrev}/roster"), self._get("/playoff-odds"))
        return compact.team_facts(abbrev, standings, roster, odds)

    async def _tool_get_playoff_odds(self, team: str):
        abbrev = await self._team(team)
        history = await self._get("/playoff-odds/history")
        points = sorted((p for p in history.get("points", []) if p["team_abbrev"] == abbrev), key=lambda p: p["as_of_date"])
        if not points:
            return {"team": abbrev, "error": "No playoff odds yet this season."}
        latest = points[-1]
        week_ago = next((p for p in reversed(points) if p["as_of_date"] <= _days_before(latest["as_of_date"], 7)), None)
        pct = lambda p: round(float(p["playoff_pct"]) * 100, 1)  # noqa: E731
        high, low = max(points, key=lambda p: p["playoff_pct"]), min(points, key=lambda p: p["playoff_pct"])
        return compact._clean({
            "team": abbrev,
            "now_pct": pct(latest), "as_of": latest["as_of_date"],
            "week_ago_pct": pct(week_ago) if week_ago else None,
            "season_start_pct": pct(points[0]), "season_start_date": points[0]["as_of_date"],
            "high_pct": pct(high), "high_date": high["as_of_date"],
            "low_pct": pct(low), "low_date": low["as_of_date"],
        })

    def _strength_ranks(self, inputs) -> dict[str, int]:
        ordered = sorted(inputs["teams"], key=lambda t: -inputs["teams"][t]["rating"])
        return {t: i + 1 for i, t in enumerate(ordered)}

    async def _tool_get_schedule(self, team: str, games: int = 5):
        # Dates come from the live NHL schedule, not the model's morning
        # snapshot: by evening, a game the snapshot calls "upcoming" may be
        # over (asked "when do they play next?" after a game, it answered
        # with the game they'd just played).
        abbrev = await self._team(team)
        schedule, inputs = await asyncio.gather(self._get(f"/teams/{abbrev}/schedule"), self._sim_inputs())
        ranks = self._strength_ranks(inputs)
        live = schedule.get("live")
        return compact._clean({
            "team": abbrev,
            "playing_now": {"opponent": live["opponent"], "home": live["home"],
                            "score": f"{live.get('team_score')}-{live.get('opponent_score')}"} if live else None,
            "regular_season_games_left": schedule.get("regular_season_games_left"),
            "next": [{"date": g["date"], "start": _eastern_time(g.get("start_time_utc")), "opponent": g["opponent"],
                      "home": g["home"], "opponent_strength_rank": ranks.get(g["opponent"])}
                     for g in schedule.get("upcoming", [])[: max(1, min(int(games), 20))]],
            "strength_rank_note": "1 = strongest team by the playoff-odds model's rating.",
        })

    async def _tool_explain_odds(self, team: str, opponent: str | None = None):
        abbrev = await self._team(team)
        opp = await self._team(opponent) if opponent else None
        if opp == abbrev:
            raise ToolError("Pick two different teams to compare.")
        standings, odds, why = await asyncio.gather(self._standings(), self._get("/playoff-odds"), self._get("/playoff-odds/why"))
        teams = why.get("teams") or {}
        if abbrev not in teams or (opp and opp not in teams):
            return {"error": "The odds breakdown isn't available yet; it's computed each morning."}
        pct, _ = compact.odds_by_team(standings, odds)
        names = {r["team_abbrev"]: r.get("team_name") for r in standings}
        result = {
            "as_of": why.get("as_of_date"),
            "teams": [_breakdown(t, names.get(t), teams[t], pct.get(t), len(teams)) for t in (abbrev, opp) if t],
            "how_to_read": "Rating = goals + xg + last_season (goals/game vs. an average team). 'push' says which way each "
                           "factor moves the rating; use it as given, and say 'negligible' factors barely matter. Compare factors by "
                           "'effect', not weight: last_season.weight_vs_this_season_pct is how much the model still trusts "
                           "last season over this season's few games (it fades as games are played). Playoff "
                           "odds also depend on points already banked, not just the rating.",
        }
        if opp:
            result["matchup"] = await self._matchup(abbrev, opp)
        return compact._clean(result)

    async def _matchup(self, team: str, opp: str) -> dict:
        """The two teams' next meeting with the model's win probability."""
        inputs, schedule = await asyncio.gather(self._sim_inputs(), self._get(f"/teams/{team}/schedule"))
        upcoming = schedule.get("upcoming", [])
        game = next((g for g in upcoming if g["opponent"] == opp), None)
        if game:
            date, home = game["date"], team if game["home"] else opp
        else:
            # Beyond the live feed's window: the model's remaining schedule.
            after = upcoming[-1]["date"] if upcoming else inputs.get("as_of_date", "")
            later = next((g for g in inputs.get("games", []) if g[0] > after and {g[1], g[2]} == {team, opp}), None)
            date, home = (later[0], later[1]) if later else (None, None)
        ratings = {t: inputs["teams"][t]["rating"] for t in (team, opp) if t in inputs.get("teams", {})}
        out = {"rating_gap": round(ratings[team] - ratings[opp], 3) if len(ratings) == 2 else None}
        if date and len(ratings) == 2:
            model = inputs.get("model", {})
            away = opp if home == team else team
            p_home = 1 / (1 + math.exp(-(ratings[home] - ratings[away] + model.get("home_edge", 0.264)) / model.get("scale", 1.47)))
            p_team = p_home if home == team else 1 - p_home
            out["next_meeting"] = {
                "date": date, "home_team": home,
                f"{team}_win_pct": round(p_team * 100, 1), f"{opp}_win_pct": round((1 - p_team) * 100, 1),
                "note": f"{home} is at home (worth about 0.26 goals/game). Single games are close to coin flips.",
            }
        return compact._clean(out)

    async def _tool_rank_schedule_strength(self, conference: str | None = None):
        inputs = await self._sim_inputs()
        teams = inputs["teams"]
        totals: dict[str, list[float]] = {t: [] for t in teams}
        for _, home, away in inputs["games"]:
            if home in teams and away in teams:
                totals[home].append(teams[away]["rating"])
                totals[away].append(teams[home]["rating"])
        rows = [
            {"team": t, "games_left": len(v), "avg_opponent_rating": round(sum(v) / len(v), 3)}
            for t, v in totals.items() if v and (not conference or teams[t]["conference"].startswith(conference))
        ]
        rows.sort(key=lambda r: r["avg_opponent_rating"])
        spread = round(rows[-1]["avg_opponent_rating"] - rows[0]["avg_opponent_rating"], 3) if rows else 0
        return {
            "easiest_first": rows,
            "spread_easiest_to_hardest": spread,
            "note": "Opponent rating = the model's goals-per-game strength estimate; lower average = easier. "
                    "Gaps under about 0.05 goals per game are negligible (common early in the season); say so instead of overselling them.",
        }

    async def _tool_simulate_scenario(self, team: str, games: int, wins: int, ot_losses: int = 0):
        abbrev = await self._team(team)
        return await self.dashboard._get(
            f"/season-sim/scenario?team={abbrev}&games={int(games)}&wins={int(wins)}&ot_losses={int(ot_losses)}")

    async def _tool_playoff_path(self, team: str, games: int = 10):
        abbrev = await self._team(team)
        return await self.dashboard._get(f"/season-sim/path?team={abbrev}&games={int(games)}")

    async def _tool_get_recent_results(self, team: str):
        abbrev = await self._team(team)
        schedule = await self._get(f"/teams/{abbrev}/schedule")
        game = lambda g: compact._clean({  # noqa: E731
            "date": g.get("date"), "opponent": g.get("opponent"), "home": g.get("home"),
            "result": g.get("result"), "score": f"{g.get('team_score')}-{g.get('opponent_score')}",
            "decided_in": g.get("last_period_type") if g.get("last_period_type") in ("OT", "SO") else None,
        })
        return compact._clean({
            "team": abbrev,
            "in_progress": game(schedule["live"]) | {"result": "LIVE"} if schedule.get("live") else None,
            "recent_newest_first": [game(g) for g in schedule.get("recent", [])],
            "score_note": "Scores are this team's goals first.",
        })

    async def _tool_get_game(self, team: str, date: str | None = None, opponent: str | None = None):
        abbrev = await self._team(team)
        opp = await self._team(opponent) if opponent else None
        if date:
            try:
                day = str(_parse_date(date))
            except ValueError as exc:
                raise ToolError("date must be YYYY-MM-DD") from exc
            games = (await self._get(f"/games/date/{day}")).get("games", [])
            match = next((g for g in games if abbrev in (g["awayTeam"]["abbrev"], g["homeTeam"]["abbrev"])
                          and (not opp or opp in (g["awayTeam"]["abbrev"], g["homeTeam"]["abbrev"]))), None)
            if not match:
                raise ToolError(f"{abbrev} didn't play{' ' + opp if opp else ''} on {day}.")
            game_id = match["id"]
        else:
            schedule = await self._get(f"/teams/{abbrev}/schedule")
            candidates = ([schedule["live"]] if schedule.get("live") else []) + schedule.get("recent", [])
            match = next((g for g in candidates if not opp or g.get("opponent") == opp), None)
            if not match:
                raise ToolError(f"No recent {abbrev} game{' against ' + opp if opp else ''}; give a date (YYYY-MM-DD).")
            game_id = match["id"]
        return compact.game_facts(await self._get(f"/games/{game_id}/boxscore"))

    async def _match_players(self, name: str) -> list[dict]:
        query = (name or "").strip().lower()
        if len(query) < 2:
            raise ToolError("Give at least part of the player's name.")
        players = await self._get("/players/leaders")
        full = lambda p: f"{p.get('first_name', '')} {p.get('last_name', '')}".lower()  # noqa: E731
        matches = [p for p in players if query in full(p)]
        if not matches:
            raise ToolError(f"No current player matches '{name}'.")
        exact = [p for p in matches if full(p) == query] or [p for p in matches if (p.get("last_name") or "").lower() == query]
        return exact or matches

    @staticmethod
    def _ambiguous(matches: list[dict]) -> dict:
        return {"multiple_matches": [compact._name(p) + f" ({p.get('team_abbrev')})" for p in matches[:8]],
                "hint": "Ask again with the full name."}

    async def _tool_find_player(self, name: str):
        matches = await self._match_players(name)
        if len(matches) > 1:
            return self._ambiguous(matches)
        player = await self._get(f"/players/{matches[0]['player_id']}")
        return compact.player_facts(player)

    async def _tool_simulate_roster_change(self, player: str, to_team: str | None = None, player_back: str | None = None):
        out = await self._match_players(player)
        if len(out) > 1:
            return self._ambiguous(out)
        out = out[0]
        back = None
        if player_back:
            back = await self._match_players(player_back)
            if len(back) > 1:
                return self._ambiguous(back)
            back = back[0]
        to = await self._team(to_team) if to_team else (back["team_abbrev"] if back else None)
        moves = [f"{out['player_id']}:{to or 'NONE'}"]
        if back:
            moves.append(f"{back['player_id']}:{out['team_abbrev']}")
        try:
            result = await self.dashboard._get("/season-sim/roster-change?" + "&".join(f"move={m}" for m in moves))
        except DashboardUnavailable as exc:
            cause = exc.__cause__
            if isinstance(cause, httpx.HTTPStatusError) and cause.response.status_code < 500:
                # The API's reason: a goalie, same team, or values not computed yet.
                raise ToolError(cause.response.json().get("detail", "That move can't be simulated.")) from exc
            raise
        return {
            **result,
            "how_to_read": "value_goals_per_game = the player's worth over a replacement-level player, in the same "
                           "goals/game units as team ratings (about 0.3 for the very best skaters). Compare each team's "
                           "with_change to its own baseline. With no destination or return, his minutes go to a "
                           "replacement-level player; a player who arrives is assumed to replace one. It's the rest "
                           "of the season, a rough estimate that ignores line chemistry and the salary cap: say so.",
        }

    async def _tool_get_injuries(self, player: str | None = None, team: str | None = None):
        if player:
            # The whole league's report, searched by name: a model asked about a
            # player tends to guess his team, and a wrong guess read as "healthy".
            query = player.strip().lower()
            report = await self._get("/injuries")
            found = [{"team": t, **compact._clean(i)} for t, rows in (report.get("teams") or {}).items()
                     for i in rows if query in (i.get("player") or "").lower()]
            if found:
                return {"source": "ESPN injury report", "matches": found}
            return {"source": "ESPN injury report", "matches": [],
                    "note": f"No one matching '{player}' is on the injury report (that doesn't guarantee he's playing)."}
        abbrev = await self._team(team) if team else None
        report = await self._get(f"/injuries?team={abbrev}" if abbrev else "/injuries")
        teams = {t: [compact._clean(i) for i in rows] for t, rows in (report.get("teams") or {}).items() if rows or abbrev}
        return {"source": "ESPN injury report", "teams": teams,
                "note": "Players not listed aren't on the report; that doesn't guarantee they're playing."}

    async def _tool_get_news(self, team: str | None = None):
        abbrev = await self._team(team) if team else None
        query = f"?team={abbrev}" if abbrev else ""
        headlines, moves = await asyncio.gather(
            self._get(f"/news{query}{'&' if query else '?'}limit=8"), self._get(f"/transactions{query}{'&' if query else '?'}limit=10"))
        return compact._clean({
            "team": abbrev,
            "headlines": [compact._clean({"title": h["title"], "source": h["source"], "published": h["published"][:16],
                                          "summary": h.get("summary")}) for h in headlines.get("headlines", [])],
            "transactions": moves.get("transactions", []),
        })

    async def _tool_get_leaders(self, category: str | None = None):
        leaders = compact.leaders(await self._get("/players/leaders"))
        return {category: leaders[category]} if category in leaders else leaders


NEGLIGIBLE = 0.03  # goals/game; matches the app's "little effect"


def _push(effect: float | None) -> str | None:
    """Spelled out, so the model can't flip a sign or oversell a rounding error."""
    if effect is None:
        return None
    if abs(effect) < NEGLIGIBLE:
        return "negligible"
    return "pushes up" if effect > 0 else "pulls down"


def _finishing(w: dict) -> str | None:
    """Goals vs. xG: the read models (and fans) care about most."""
    gd, xgd, gp = w.get("goal_diff"), w.get("xg_diff"), w.get("games_played") or 0
    if xgd is None or not gp:
        return None
    gap = (gd - xgd) / gp
    if gap > 0.4:
        return "Scoring well above its chance quality (goals > xG): finishing or goaltending running hot, which usually cools off."
    if gap < -0.4:
        return "Scoring well below its chance quality (goals < xG): finishing or goaltending running cold, which usually improves."
    return "Goals and xG roughly agree: results match the chances."


def _breakdown(team: str, name: str | None, w: dict, playoff_pct: float | None, league_size: int) -> dict:
    """One team's "why these odds?" in the shape the model reads best."""
    sched = w.get("schedule") or {}
    return compact._clean({
        "team": team,
        "name": name,
        "playoff_pct": round(playoff_pct * 100, 1) if playoff_pct is not None else None,
        "rating": w.get("rating"),
        "rating_rank": f"{w.get('rating_rank')} of {league_size}",
        "goals": {"goal_diff": w.get("goal_diff"), "games_played": w.get("games_played"), "effect": w.get("goals"),
                  "push": _push(w.get("goals"))},
        "xg": {"xg_diff": w.get("xg_diff"), "effect": w.get("xg"), "push": _push(w.get("xg"))} if w.get("xg") is not None else None,
        "goals_vs_xg": _finishing(w),
        "last_season": {("xg_diff_per_game" if w.get("xg") is not None else "goal_diff_per_game"): w.get("last_season_per_game"),
                        "weight_vs_this_season_pct": round((w.get("last_season_share") or 0) * 100),
                        "effect": w.get("last_season"), "push": _push(w.get("last_season"))},
        "schedule": {"games_left": sched.get("games_left"), "rank": f"{_ordinal(sched.get('rank'))} easiest of {league_size}",
                     "effect": sched.get("effect"), "push": _push(sched.get("effect"))} if sched.get("games_left") else None,
    })


def _ordinal(n: int | None) -> str | None:
    if n is None:
        return None
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def _eastern_time(utc_iso: str | None) -> str | None:
    """'2026-10-10T23:00:00Z' -> '7:00 PM ET' (how fans read start times)."""
    if not utc_iso:
        return None
    from datetime import datetime
    from zoneinfo import ZoneInfo

    local = datetime.fromisoformat(utc_iso.replace("Z", "+00:00")).astimezone(ZoneInfo("America/New_York"))
    return local.strftime("%-I:%M %p ET")


def _parse_date(value: str):
    from datetime import date

    return date.fromisoformat(value.strip()[:10])


def _days_before(iso: str, days: int) -> str:
    from datetime import date, timedelta

    return str(date.fromisoformat(str(iso)[:10]) - timedelta(days=days))
