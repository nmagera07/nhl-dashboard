"""
The PuckPulse draft board and mock draft.

The board is a consensus: each prospect's average rank across public lists
(assets/draft_board_<year>.json, updated by hand when a source posts a new
list, about monthly). A prospect a list doesn't rank counts as one past
its end, so being left off a top 40 costs a player, but not as much as
ranking 64th would.

The mock draft pairs a draft order with the board: each team takes the
best player left, which with one board is simply the next one.
"""

import json
import os

ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
ROUND = 32


def load(year):
    """The board file for a draft year, or None if there isn't one yet."""
    path = os.path.join(ASSETS, f"draft_board_{year}.json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def consensus(board):
    """[{rank, name, pos, team, league, avg, ranks: {source: rank or None}}], best first."""
    sources = board["sources"]
    rows = []
    for name, info in board["prospects"].items():
        ranks = {s["name"]: s["ranks"].index(name) + 1 if name in s["ranks"] else None for s in sources}
        counted = [r if r is not None else len(s["ranks"]) + 1 for s, r in zip(sources, ranks.values())]
        rows.append({"name": name, **info, "avg": round(sum(counted) / len(counted), 1), "ranks": ranks})
    # Ties go to the player with the better best ranking.
    rows.sort(key=lambda r: (r["avg"], min(v for v in r["ranks"].values() if v is not None)))
    return [{"rank": i + 1, **r} for i, r in enumerate(rows)]


def today_order(lottery_today, standings):
    """
    The first round if the season ended today: the 16 lottery teams in
    order (no lottery jumps, the single likeliest outcome), then the playoff
    teams, worst record first. (Really, playoff teams pick by how far they
    go; before the playoffs, record is the best guess.)
    """
    lottery_teams = [t["team"] for t in lottery_today]
    rest = sorted((r for r in standings if r["team_abbrev"] not in lottery_teams), key=lambda r: -r["league_sequence"])
    return (lottery_teams + [r["team_abbrev"] for r in rest])[:ROUND]


def projected_order(projected, standings):
    """
    The first round by the season simulation: teams sorted by their
    expected pick, where missing the lottery counts as a pick in the
    middle of the playoff teams' range (24.5). Teams the simulation never
    has missing the playoffs fall back to record, worst first.
    """
    expected = {}
    for t in projected:
        picks = t["picks"]
        expected[t["team"]] = sum(p * (i + 1) for i, p in enumerate(picks)) + (1 - sum(picks)) * 24.5
    worst_first = sorted(standings, key=lambda r: -r["league_sequence"])
    order = sorted(worst_first, key=lambda r: expected.get(r["team_abbrev"], 24.5))
    return [r["team_abbrev"] for r in order][:ROUND]


def mock_draft(order, prospects):
    """[{pick, team, prospect}] for each team in order, taking the best player left."""
    return [{"pick": i + 1, "team": team, "prospect": prospect} for i, (team, prospect) in enumerate(zip(order, prospects))]
