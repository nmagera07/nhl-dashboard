"""
Eval cases: a question, the page it's asked from, and a `truth` function
that works out today's correct answer from the dashboard API. Standings and
schedules change daily, so hardcoded answers would rot; computing the truth
at eval time keeps every case checkable.

Each truth function returns the checks to run on the answer (and may set
"question" when the question itself depends on today's data):
    tool:     (names, args) the agent should have called (None = any/none)
    facts:    strings, at least one of which the answer must mention
    percent:  a percentage the answer must state (within 1 point)
    rubric:   a judge rubric, for qualities rules can't check
"""

import json
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

Truth = dict[str, Any]


@dataclass
class Case:
    id: str
    question: str
    truth: Callable[[Any], Awaitable[Truth]]
    context: dict = field(default_factory=lambda: {"page": "standings"})
    digest: bool = False  # write the morning digest from truth["facts"] instead of asking the chat


def _pct(fraction) -> float:
    return round(float(fraction) * 100, 1)


def _names(row) -> list[str]:
    return [row.get("team_abbrev"), row.get("team_name"), row.get("common_name")]


async def division_leader(api) -> Truth:
    standings = await api("/standings/latest")
    leader = next(r for r in standings if r["division"] == "Metropolitan" and r["division_sequence"] == 1)
    return {"tool": None, "facts": _names(leader)}


async def next_game(api) -> Truth:
    schedule, standings = await api("/teams/PIT/schedule"), await api("/standings/latest")
    nxt = schedule["upcoming"][0]
    opponent = next((r for r in standings if r["team_abbrev"] == nxt["opponent"]), {"team_abbrev": nxt["opponent"]})
    return {"tool": ("get_schedule", {"team": "PIT"}), "facts": _names(opponent)}


async def scenario(api) -> Truth:
    result = await api("/season-sim/scenario?team=PIT&games=4&wins=4")
    return {"tool": ("simulate_scenario", {"team": "PIT", "games": 4, "wins": 4}),
            "percent": _pct(result["with_scenario"]["playoff_pct"])}


async def playoff_path(api) -> Truth:
    path = await api("/season-sim/path?team=DET&games=10")
    needed = next((row["record"] for row in path["by_record"] if row["playoff_pct"] > 0.5), None)
    facts = [needed] if needed else ["can't", "even 10-0"]
    return {"tool": ("playoff_path", {"team": "DET"}), "facts": facts}


async def odds_history(api) -> Truth:
    history = await api("/playoff-odds/history")
    first = min((p for p in history["points"] if p["team_abbrev"] == "TOR"), key=lambda p: p["as_of_date"])
    return {"tool": ("get_playoff_odds", {"team": "TOR"}), "percent": _pct(first["playoff_pct"])}


async def last_result(api) -> Truth:
    last = (await api("/teams/PIT/schedule"))["recent"][0]
    us, them = last["team_score"], last["opponent_score"]
    return {"tool": (("get_recent_results", "get_game"), None), "score": (us, them)}


async def last_game_scorers(api) -> Truth:
    last = (await api("/teams/PIT/schedule"))["recent"][0]
    game = await api(f"/games/{last['id']}/boxscore")
    scorers = [g["lastName"]["default"] for p in game.get("summary", {}).get("scoring", [])
               for g in p.get("goals", []) if (g.get("teamAbbrev") or {}).get("default") == "PIT"]
    return {"tool": ("get_game", {"team": "PIT"}), "facts": scorers or ["didn't score", "no goals", "shut out"]}


async def player_points(api) -> Truth:
    crosby = next(p for p in await api("/players/leaders") if p["last_name"] == "Crosby" and p["first_name"] == "Sidney")
    n = crosby["points"]
    return {"tool": ("find_player", None), "facts": [f"{n} point", f"{n} pts", f"{n} total point"]}


async def points_leader(api) -> Truth:
    players = [p for p in await api("/players/leaders") if p.get("position_code") != "G"]
    top = max(p["points"] or 0 for p in players)
    return {"tool": None, "facts": [p["last_name"] for p in players if (p["points"] or 0) == top]}


async def easiest_schedule(api) -> Truth:
    inputs = await api("/season-sim")
    teams = inputs["teams"]
    opp: dict[str, list[float]] = {t: [] for t in teams}
    for _, home, away, *_ in inputs["games"]:  # rows also carry back-to-back flags
        opp[home].append(teams[away]["rating"])
        opp[away].append(teams[home]["rating"])
    west = {t: sum(v) / len(v) for t, v in opp.items() if v and teams[t]["conference"].startswith("Western")}
    ranked = sorted(west, key=west.get)
    spread = west[ranked[-1]] - west[ranked[0]]
    rubric = ("The schedule differences are tiny (under 0.05 goals per game). Pass only if the answer says or clearly "
              "implies the gap is small, marginal, or negligible rather than presenting it as a big advantage."
              if spread < 0.05 else "Pass if the answer names the easiest schedule without overstating certainty.")
    return {"tool": ("rank_schedule_strength", None), "facts": [ranked[0]], "rubric": rubric}


async def pdo_reading(api) -> Truth:
    pdo = (await api("/players/8471675")).get("advanced_stats", {}).get("pdo")
    if pdo is None:
        return {"skip": "no PDO yet"}
    if pdo < 99:
        meaning = f"below the ~100 average, suggesting bad luck that tends to even out (it is {pdo:.1f})"
    elif pdo > 101:
        meaning = f"above the ~100 average, suggesting good luck that tends to even out (it is {pdo:.1f})"
    else:
        meaning = f"close to the ~100 average, i.e. no unusual luck (it is {pdo:.1f})"
    return {"tool": ("find_player", None),
            "rubric": f"Crosby's 5-on-5 PDO is {meaning}. Pass only if the answer interprets it that way; "
                      "fail if it calls it average when it isn't, or reads the direction backwards."}


def _factor_lines(team, w) -> str:
    # v2.4+: the prior is the roster's players plus goaltending; older data carries last season's xG instead.
    parts = [("goals", w["goals"]), ("expected goals (xG)", w.get("xg")),
             ("last season", w.get("last_season") or None), ("roster talent", w.get("roster")),
             ("goaltending", w.get("goalies")), ("schedule", (w.get("schedule") or {}).get("effect"))]
    return f"{team}: " + ", ".join(f"{name} {v:+.3f}" for name, v in parts if v is not None)


async def why_odds(api) -> Truth:
    pit = (await api("/playoff-odds/why"))["teams"].get("PIT")
    if not pit:
        return {"skip": "no odds breakdown yet"}
    return {
        "tool": ("explain_odds", {"team": "PIT"}),
        "rubric": "The model's rating breakdown, in goals/game (positive pushes the odds up; under 0.03 is negligible): "
                  + _factor_lines("PIT", pit) + f". The prior (roster and goaltending) is still {round(pit['last_season_share'] * 100)}% "
                  "of the rating. If the question's premise is wrong (e.g. the odds aren't high), saying so is right. Pass only if the answer names the factors that actually push PIT up or down, in the right "
                  "direction, and doesn't credit a negligible factor as a big reason. Fail if it gets any factor's "
                  "direction backwards (e.g. calls a negative schedule a boost), if it reads goals well above xG as "
                  "proof the scoring is sustainable (it means the opposite), or on invented reasons (injuries, "
                  "trades) that aren't in the breakdown. Saying PIT is scoring above its xG, i.e. running hot "
                  "on finishing or goaltending that may cool off, is correct (the tool reports it).",
    }


async def why_favored(api) -> Truth:
    why = (await api("/playoff-odds/why"))["teams"]
    if "CAR" not in why or "NYR" not in why:
        return {"skip": "no odds breakdown yet"}
    standings = await api("/standings/latest")
    fav = "CAR" if why["CAR"]["rating"] >= why["NYR"]["rating"] else "NYR"
    row = next((r for r in standings if r["team_abbrev"] == fav), {"team_abbrev": fav})
    return {
        "tool": ("explain_odds", None),
        "facts": _names(row),
        "rubric": f"The model rates {fav} higher. Breakdown (goals/game): " + _factor_lines("CAR", why["CAR"]) + "; "
                  + _factor_lines("NYR", why["NYR"]) + ". Pass only if the answer says the model favors " + fav
                  + " and explains it with the factors where the two teams differ most, without invented reasons or a factor's "
                  "direction backwards. Rounded numbers, or citing the raw goal/xG differentials instead of the effects, "
                  "are fine; so is noting which team is scoring above or below its xG.",
    }


async def _player_id(api, first, last):
    return next(p["player_id"] for p in await api("/players/leaders") if p["first_name"] == first and p["last_name"] == last)


async def trade_away(api) -> Truth:
    larkin = await _player_id(api, "Dylan", "Larkin")
    try:
        result = await api(f"/season-sim/roster-change?move={larkin}:NONE")
    except Exception:
        return {"skip": "no player values yet"}
    det = next(t for t in result["teams"] if t["team"] == "DET")
    return {
        "tool": ("simulate_roster_change", None),
        "percent": _pct(det["with_change"]["playoff_pct"]),
        "rubric": f"Detroit's odds go from {_pct(det['baseline']['playoff_pct'])}% to {_pct(det['with_change']['playoff_pct'])}% "
                  "in the model. Pass only if the answer gives that change, presents it as a rough model estimate (not "
                  "a certainty), and doesn't claim to know about any real trade.",
    }


async def trade_swap(api) -> Truth:
    larkin, matthews = await _player_id(api, "Dylan", "Larkin"), await _player_id(api, "Auston", "Matthews")
    try:
        result = await api(f"/season-sim/roster-change?move={larkin}:TOR&move={matthews}:DET")
    except Exception:
        return {"skip": "no player values yet"}
    lines = "; ".join(f"{t['team']} {_pct(t['baseline']['playoff_pct'])}% -> {_pct(t['with_change']['playoff_pct'])}%"
                      for t in result["teams"])
    return {
        "tool": ("simulate_roster_change", None),
        "rubric": f"The model's result: {lines}. Pass only if the answer reports both teams' changes consistently with "
                  "these numbers (rounding is fine) and doesn't invent other effects.",
    }


async def injury_status(api) -> Truth:
    report = (await api("/injuries"))["teams"]
    hurt = next(((team, rows[0]) for team, rows in sorted(report.items()) if rows and rows[0].get("status")), None)
    if not hurt:
        return {"skip": "nobody on the injury report"}
    team, row = hurt
    return {"question": f"Is {row['player']} injured right now?", "tool": ("get_injuries", None), "facts": [row["status"], row["status"].lower()],
            "rubric": f"The injury report lists {row['player']} ({team}) as {row['status']}"
                      + (f" with a {row['injury']} injury" if row.get("injury") else "")
                      + (f", expected back {row['expected_return']}" if row.get("expected_return") else "")
                      + (f". The report's note: \"{row['note']}\"" if row.get("note") else "")
                      + ". Details from the note are fine, dates may be written without the year, and \"as of the latest "
                        "report\" or crediting ESPN's injury report counts as attributing it; repeating the note's quote is fine, and the team needn't be named. Pass only if the answer gives that status (and the right team, "
                        "if it names one) without inventing details. Fail if it says he isn't injured or isn't listed."}



async def _today_games(api):
    from datetime import datetime
    from zoneinfo import ZoneInfo

    day = datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d")
    games = [g for g in (await api(f"/games/date/{day}")).get("games", []) if g.get("gameState") in ("FUT", "PRE")]
    return day, games


def _starter_name(board, side):
    reported = (board.get("reported_starters") or {}).get(side)
    if reported:
        return reported["name"]
    nhl = (board.get("nhl_starters") or {}).get(side)
    if nhl:
        return nhl
    top = ((board.get("goalies") or {}).get(side) or [None])[0]
    return top["name"] if top else None


async def first_line(api) -> Truth:
    _, games = await _today_games(api)
    for g in games:
        lineup = await api(f"/games/{g['id']}/lineup")
        if lineup.get("available") and (lineup["home"].get("forwards") or [None])[0]:
            team, line = g["homeTeam"]["abbrev"], lineup["home"]["forwards"][0]
            return {"question": f"Who's on {team}'s first line tonight?", "tool": ("get_lineup", {"team": team}),
                    "facts": [n.split()[-1] for n in line],
                    "rubric": f"NHL.com's projected first line for {team} is {', '.join(line)}. Pass if the answer names "
                              "these players, says it's NHL.com's projection, and that it can change before puck drop."}
    return {"skip": "no game today with NHL.com's projected lineup posted yet"}


async def goalie_tonight(api) -> Truth:
    day, games = await _today_games(api)
    if not games:
        return {"skip": "no games left today"}
    g = games[0]
    board = (await api(f"/bets?date={day}"))["games"].get(str(g["id"]))
    team = g["homeTeam"]["abbrev"]
    name = _starter_name(board or {}, "home")
    if not name:
        return {"skip": f"no starter for {team} yet"}
    return {"question": f"Who's starting in goal for {team} tonight?", "tool": (("get_lineup", "get_bets"), None),
            "facts": [name.split()[-1]],
            "rubric": f"The best source available names {name} as {team}'s starter. Pass if the answer names him, says "
                      "where that comes from, and doesn't present it as certain if it's only a projection."}


async def value_bets(api) -> Truth:
    day, games = await _today_games(api)
    open_ids = {str(g["id"]) for g in games}  # a flag on a game that's started can't be bet anymore
    board = {k: v for k, v in (await api(f"/bets?date={day}")).get("games", {}).items() if k in open_ids}
    flagged = [f"{b['away']} @ {b['home']}" for b in board.values()
               for market in ("moneyline", "puck_line") for side in ("home", "away")
               if ((b.get(market) or {}).get(side) or {}).get("value")]
    return {"tool": ("get_bets", None), "facts": ["21+"],
            "rubric": ("The value flags today are on: " + "; ".join(flagged) if flagged else "Nothing is flagged as value today")
                      + ". Pass if the answer matches that, explains it in plain words, never calls a bet a lock or a sure "
                        "thing or tells the user to bet, and says it's for entertainment, not betting advice, 21+."}


async def mock_pick(api) -> Truth:
    mock = (await api("/draft-lottery")).get("mock") or {}
    picks = mock.get("projected") or mock.get("today") or []
    if len(picks) < 6:
        return {"skip": "no mock draft"}
    pick = picks[5]
    return {"question": f"Who does the PuckPulse mock draft have {pick['team']} taking?", "tool": ("get_draft_lottery", {"team": pick["team"]}),
            "facts": [pick["prospect"]["name"].split()[-1]],
            "rubric": f"The mock draft has {pick['team']} taking {pick['prospect']['name']} at No. {pick['pick']}. Pass if the "
                      "answer says so and doesn't present the mock draft as a certainty."}


async def fantasy_update(api) -> Truth:
    updates = (await api("/fantasy?limit=150")).get("updates", [])
    if not updates:
        return {"skip": "no fantasy updates"}
    u = updates[0]
    return {"question": f"What's the latest fantasy news on {u['player']}?", "tool": ("get_fantasy_news", None),
            "facts": [u["player"].split()[-1]],
            "rubric": f"RotoWire's latest on {u['player']}: \"{u['title']}\" ({u.get('summary') or 'no detail'}). Pass if the "
                      "answer gives that update. Fail if it says there's no news on him."}


async def last_night(api) -> Truth:
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo

    day = (datetime.now(ZoneInfo("America/New_York")) - timedelta(days=1)).strftime("%Y-%m-%d")
    finals = [g for g in (await api(f"/games/date/{day}")).get("games", []) if g.get("gameState") in ("FINAL", "OFF")]
    if not finals:
        return {"skip": "no games last night"}
    lines = [f"{g['awayTeam']['abbrev']} {g['awayTeam']['score']}, {g['homeTeam']['abbrev']} {g['homeTeam']['score']}" for g in finals]
    winner = lambda g: g["homeTeam"]["abbrev"] if g["homeTeam"]["score"] > g["awayTeam"]["score"] else g["awayTeam"]["abbrev"]  # noqa: E731
    return {"tool": ("get_scores", None), "facts": [winner(finals[0])],
            "rubric": f"Last night's finals ({day}): " + "; ".join(lines) + ". Pass if the answer lists these results "
                      "correctly (who won each), and fail if it says it can't see last night's scores."}


async def best_goalie(api) -> Truth:
    goalies = (await api("/goalies/advanced")).get("goalies", [])
    if not goalies:
        return {"skip": "no goalie stats yet"}
    top = goalies[:3]
    return {"tool": ("get_leaders", {"category": "gsax"}), "facts": [top[0]["name"].split()[-1]],
            "rubric": "By goals saved above expected (GSAx), the top goalies are " + ", ".join(f"{g['name']} ({g['gsax']:+.2f})" for g in top)
                      + ". Pass if the answer names the leader by GSAx (wins or save percentage alone isn't enough) and "
                        "explains GSAx in plain words."}


async def report_card(api) -> Truth:
    card = await api("/report-card")
    ml = (card.get("season") or {}).get("moneyline") or {}
    if not ml.get("games"):
        return {"skip": "no graded games yet"}
    better = "better" if ml["brier_ours"] < ml["brier_books"] else "worse"
    return {"tool": ("get_report_card", None),
            "rubric": f"On moneylines this season PuckPulse's Brier score is {ml['brier_ours']} vs the books' {ml['brier_books']} "
                      f"over {ml['games']} games (lower is better), so PuckPulse has been {better}. Pass if the answer gets that "
                      "direction right and explains what the score means in plain words; it may cite the season's total games "
                      "instead of the moneyline count."}


DIGEST_FACTS_FILE = None  # set by --digest-facts: judge a digest written from these facts


async def morning_digest(api) -> Truth:
    if DIGEST_FACTS_FILE:
        facts = json.loads(open(DIGEST_FACTS_FILE).read())
    else:
        try:
            facts = (await api("/digest/latest"))["facts"]
        except Exception:
            return {"skip": "no digest stored yet"}
    winners = [g["home"] if g["home_score"] > g["away_score"] else g["away"] for g in facts.get("last_night", [])]
    names = facts.get("team_names", {})
    return {
        "facts_input": facts,
        "facts": [names.get(w, w) for w in winners] + winners,
        "rubric": "Here are the facts the digest was written from: " + json.dumps(facts) + " The digest is meant to be "
                  "selective, so leaving out games or moves is fine. Fail only on a wrong or invented claim: a wrong "
                  "winner, score, team, or how a game ended (OT vs SO); last night's and tonight's games mixed up; or "
                  "stats, injuries, or storylines that aren't in the facts.",
    }


CASES = [
    Case("division_leader", "Who's in first place in the Metropolitan Division?", division_leader),
    Case("next_game", "When do the Penguins play next?", next_game),
    Case("scenario", "What happens to Pittsburgh's playoff odds if they win their next 4 games?", scenario),
    Case("playoff_path", "What record does Detroit need over its next 10 games to have a better-than-even chance at the playoffs?", playoff_path),
    Case("odds_history", "What were Toronto's playoff odds at the start of the season?", odds_history),
    Case("last_result", "What was the score of the Penguins' last game?", last_result),
    Case("last_game_scorers", "Who scored for Pittsburgh in their last game?", last_game_scorers),
    Case("player_points", "How many points does Sidney Crosby have this season?", player_points),
    Case("points_leader", "Who leads the NHL in points right now?", points_leader),
    Case("easiest_schedule", "Who has the easiest remaining schedule in the Western Conference?", easiest_schedule),
    Case("pdo_reading", "What does Sidney Crosby's PDO say about his start?", pdo_reading),
    Case("why_odds", "Why are Pittsburgh's playoff odds so high?", why_odds),
    Case("why_favored", "Who does the model like more between Carolina and the Rangers, and why?", why_favored),
    Case("trade_away", "What if the Red Wings traded away Dylan Larkin? How would that affect their playoff odds?", trade_away),
    Case("trade_swap", "What would a Larkin-for-Matthews trade do to Detroit's and Toronto's playoff chances?", trade_swap),
    Case("injury_status", "(a player on today's injury report)", injury_status),
    Case("first_line", "(a team playing tonight with NHL.com's lineup posted)", first_line),
    Case("goalie_tonight", "(a team playing tonight)", goalie_tonight),
    Case("value_bets", "Any value bets on tonight's games?", value_bets),
    Case("mock_pick", "(the sixth pick in the mock draft)", mock_pick),
    Case("fantasy_update", "(the newest RotoWire update)", fantasy_update),
    Case("report_card", "How have PuckPulse's odds done against the sportsbooks this season?", report_card),
    Case("last_night", "Who won last night?", last_night),
    Case("best_goalie", "Who's the best goalie in the league this season?", best_goalie),
    Case("morning_digest", "(write the morning digest)", morning_digest, digest=True),
]
