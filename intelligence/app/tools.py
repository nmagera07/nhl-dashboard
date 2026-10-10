"""
Tools the model can call: read-only queries against the dashboard API and
the playoff-odds model's "what if" simulations.

The model decides *which* question to ask; the numbers always come from
here (the dashboard's data and the deterministic simulation), never from the
model's own arithmetic. Results are compact on purpose: every tool round
resends the conversation, and free tiers cap tokens per minute.
"""

import asyncio
import json
import logging
from typing import Any

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
    _fn("playoff_path",
        "What a team needs: its playoff odds for every possible record over its next games (e.g. 0-10 up to 10-0), from the model.",
        {"team": TEAM, "games": {"type": "integer", "minimum": 1, "maximum": 15, "description": "Default 10."}},
        ["team"]),
    _fn("find_player", "Look up a player by name: season stats, career, and 5-on-5 advanced stats.",
        {"name": {"type": "string", "description": "Full or last name, e.g. 'Crosby'."}}, ["name"]),
    _fn("get_leaders", "League leaders: points, goals, and goalie wins."),
]

# What the chat shows while a tool runs, and the evidence label after.
LABELS = {
    "get_standings": ("Checking the standings", "Current standings"),
    "get_team": ("Looking up the team", "Team season and roster"),
    "get_playoff_odds": ("Checking playoff odds history", "Playoff odds history"),
    "get_schedule": ("Checking the schedule", "Remaining schedule"),
    "rank_schedule_strength": ("Ranking remaining schedules", "Strength of remaining schedules"),
    "simulate_scenario": ("Simulating 2,000 seasons", "Season simulation (playoff-odds model)"),
    "playoff_path": ("Simulating every record", "Season simulation (playoff-odds model)"),
    "find_player": ("Looking up the player", "Player profile and stats"),
    "get_leaders": ("Checking the league leaders", "League leaders"),
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
        abbrev = await self._team(team)
        inputs = await self._sim_inputs()
        ranks = self._strength_ranks(inputs)
        upcoming = [(d, h, a) for d, h, a in inputs["games"] if abbrev in (h, a)]
        return {
            "team": abbrev,
            "games_left": len(upcoming),
            "next": [{"date": d, "opponent": a if h == abbrev else h, "home": h == abbrev,
                      "opponent_strength_rank": ranks.get(a if h == abbrev else h)}
                     for d, h, a in upcoming[: max(1, min(int(games), 20))]],
            "strength_rank_note": "1 = strongest team by the playoff-odds model's rating.",
        }

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

    async def _tool_find_player(self, name: str):
        query = (name or "").strip().lower()
        if len(query) < 2:
            raise ToolError("Give at least part of the player's name.")
        players = await self._get("/players/leaders")
        matches = [p for p in players if query in f"{p.get('first_name', '')} {p.get('last_name', '')}".lower()]
        if not matches:
            raise ToolError(f"No current player matches '{name}'.")
        if len(matches) > 1 and not any(query == f"{p['first_name']} {p['last_name']}".lower() for p in matches):
            exact_last = [p for p in matches if (p.get("last_name") or "").lower() == query]
            matches = exact_last or matches
        if len(matches) > 1:
            return {"multiple_matches": [compact._name(p) + f" ({p.get('team_abbrev')})" for p in matches[:8]],
                    "hint": "Ask again with the full name."}
        player = await self._get(f"/players/{matches[0]['player_id']}")
        return compact.player_facts(player)

    async def _tool_get_leaders(self):
        return compact.leaders(await self._get("/players/leaders"))


def _days_before(iso: str, days: int) -> str:
    from datetime import date, timedelta

    return str(date.fromisoformat(str(iso)[:10]) - timedelta(days=days))
