"""
Player values for "what if they traded X?" questions.

Each skater's worth in goals/game over a replacement-level player, the same
unit as the playoff-odds model's team ratings, so a trade is arithmetic:
the team losing him drops by his value, the team getting him gains it, and
season_scenarios.roster_change() replays the season with those ratings.

How a value is built:
  1. Game Score (Dom Luszczyszyn's box-score composite): goals, assists,
     shots, blocks, penalties, faceoffs, plus 5-on-5 on-ice shot attempts
     and goals, from MoneyPuck's skater season summaries.
  2. Per game, blended over this season and last, pulled toward
     replacement level by SHRINK_GAMES pseudo-games, so six hot games don't
     make a star.
  3. Minus replacement level (fringe players' Game Score per game, by
     position), times GS_TO_GOALS: goals/game of team goal differential
     per point of team Game Score per game.

GS_TO_GOALS and the replacement levels come from `--calibrate` (3 seasons,
96 team-seasons; team Game Score tracks goal differential at r = 0.86).
Tried first and dropped: relative 5-on-5 xG alone, which rated Crosby and
Makar below average and third-pair defensemen among the league's best.

Known limits: skaters only (no goalies); line-mates and team quality leak
into on-ice numbers; a player coming in is assumed to replace a
replacement-level player. Answers should say "roughly".

Usage:
    python player_values.py --calibrate     # refit the constants
    python player_values.py --top 20        # today's most valuable skaters
"""

import argparse
import csv
import io
from collections import defaultdict

import requests

MONEYPUCK_SKATERS_URL = "https://moneypuck.com/moneypuck/playerData/seasonSummary/{year}/regular/skaters.csv"
MONEYPUCK_TEAMS_URL = "https://moneypuck.com/moneypuck/playerData/seasonSummary/{year}/regular/teams.csv"
MONEYPUCK_HEADERS = {"User-Agent": "nhl-dashboard (personal, non-commercial; credits MoneyPuck.com)"}

# From --calibrate, 2023-24 to 2025-26.
GS_TO_GOALS = 0.194                         # team GD/game per team Game Score/game
REPLACEMENT_GS = {"F": 0.183, "D": 0.165}   # Game Score/game of fringe (5-29 GP) players
SHRINK_GAMES = 10                           # pseudo-games of replacement level
FRINGE_GP = (5, 30)


def _f(row, key):
    return float(row.get(key) or 0)


def game_score(all_row, ev_row):
    """Season Game Score from a player's all-situations and 5-on-5 rows."""
    return (
        0.75 * _f(all_row, "I_F_goals") + 0.7 * _f(all_row, "I_F_primaryAssists")
        + 0.55 * _f(all_row, "I_F_secondaryAssists") + 0.075 * _f(all_row, "I_F_shotsOnGoal")
        + 0.05 * _f(all_row, "shotsBlockedByPlayer")
        + 0.15 * _f(all_row, "penaltiesDrawn") - 0.15 * _f(all_row, "penalties")
        + 0.01 * _f(all_row, "faceoffsWon") - 0.01 * _f(all_row, "faceoffsLost")
        + 0.05 * _f(ev_row, "OnIce_F_shotAttempts") - 0.05 * _f(ev_row, "OnIce_A_shotAttempts")
        + 0.15 * _f(ev_row, "OnIce_F_goals") - 0.15 * _f(ev_row, "OnIce_A_goals")
    )


def position_group(position):
    return "D" if position == "D" else "F"


def season_game_scores(csv_text):
    """{player_id: {"name", "team", "pos", "gp", "gs"}} from a MoneyPuck skaters CSV."""
    by_player = defaultdict(dict)
    for row in csv.DictReader(io.StringIO(csv_text)):
        by_player[int(row["playerId"])][row["situation"]] = row
    out = {}
    for pid, rows in by_player.items():
        if "all" not in rows or "5on5" not in rows:
            continue
        gp = int(_f(rows["all"], "games_played"))
        if gp:
            out[pid] = {"name": rows["all"]["name"], "team": rows["all"]["team"], "pos": rows["all"]["position"],
                        "gp": gp, "gs": game_score(rows["all"], rows["5on5"])}
    return out


def fetch_csv(url, year):
    response = requests.get(url.format(year=year), headers=MONEYPUCK_HEADERS, timeout=30)
    response.raise_for_status()
    return response.text


def player_values(current, previous, rosters=None):
    """
    {player_id: {"name", "team", "pos", "gp", "value"}}: goals/game over
    replacement, from this season's and last season's season_game_scores().
    `rosters` ({player_id: team}) overrides MoneyPuck's team, which is stale
    for a player who moved in the offseason and hasn't played yet.
    """
    out = {}
    for pid in set(current) | set(previous):
        cur, prev = current.get(pid), previous.get(pid)
        latest = cur or prev
        team = (rosters or {}).get(pid, latest["team"])
        if rosters is not None and pid not in rosters:
            continue  # not on an NHL roster now (retired, unsigned, in the minors)
        repl = REPLACEMENT_GS[position_group(latest["pos"])]
        gs = (cur or {}).get("gs", 0) + (prev or {}).get("gs", 0)
        gp = (cur or {}).get("gp", 0) + (prev or {}).get("gp", 0)
        per_game = (gs + SHRINK_GAMES * repl) / (gp + SHRINK_GAMES)
        out[pid] = {
            "name": latest["name"], "team": team, "pos": latest["pos"],
            "gp": (cur or {}).get("gp", 0), "gp_last_season": (prev or {}).get("gp", 0),
            "value": round(GS_TO_GOALS * (per_game - repl), 4),
        }
    return out


def calibrate(years):
    """Refit GS_TO_GOALS (team GD/game on team Game Score/game) and the replacement levels."""
    xs, ys, fringe = [], [], defaultdict(lambda: [0.0, 0])
    for year in years:
        players = season_game_scores(fetch_csv(MONEYPUCK_SKATERS_URL, year))
        team_gs = defaultdict(float)
        for p in players.values():
            team_gs[p["team"]] += p["gs"]
            if FRINGE_GP[0] <= p["gp"] < FRINGE_GP[1]:
                group = fringe[position_group(p["pos"])]
                group[0] += p["gs"]
                group[1] += p["gp"]
        for row in csv.DictReader(io.StringIO(fetch_csv(MONEYPUCK_TEAMS_URL, year))):
            if row["situation"] == "all":
                gp = _f(row, "games_played")
                xs.append(team_gs[row["team"]] / gp)
                ys.append((_f(row, "goalsFor") - _f(row, "goalsAgainst")) / gp)
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    syy = sum((y - my) ** 2 for y in ys)
    return {
        "team_seasons": n,
        "gs_to_goals": round(sxy / sxx, 3),
        "r": round(sxy / (sxx * syy) ** 0.5, 2),
        "replacement_gs": {k: round(gs / gp, 3) for k, (gs, gp) in fringe.items()},
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--calibrate", action="store_true")
    parser.add_argument("--top", type=int, default=0)
    parser.add_argument("--season-start", type=int, default=None, help="e.g. 2026 for 2026-27 (default: current)")
    args = parser.parse_args()
    from simulate_playoff_odds import current_season_id

    start = args.season_start or current_season_id() // 10000
    if args.calibrate:
        print(calibrate([start - 3, start - 2, start - 1]))
    if args.top:
        values = player_values(season_game_scores(fetch_csv(MONEYPUCK_SKATERS_URL, start)),
                               season_game_scores(fetch_csv(MONEYPUCK_SKATERS_URL, start - 1)))
        for pid, v in sorted(values.items(), key=lambda kv: -kv[1]["value"])[: args.top]:
            print(f"{v['name']:24} {v['team']} {v['pos']}  {v['value']:+.3f} goals/game")


if __name__ == "__main__":
    main()
