"""
Advanced stats (Corsi/Fenwick/xG/PDO, goalie GSAx) for the Standings page
and player cards, from PuckPulse's own xG and the NHL's stats API.

  - Teams, 5-on-5: sums of team_game_5v5 (ingest_xg.py, from play-by-play):
    shot attempts, unblocked attempts, shots, goals, and our xG.
  - Skaters, 5-on-5: Corsi/Fenwick, PDO, and ice time from the NHL stats
    API (skater/summaryshooting and skater/percentages); his own xG and
    on-ice xG from player_game_5v5 (our xG, on-ice from shift charts).
  - Goalies, all situations: xG and goals against, and high-danger shots
    (xG of 0.20 or more), from goalie_game_xg; games, ice time, and shots
    on goal faced from the NHL's goalie summary.

Replaced MoneyPuck's season files (free for non-commercial use only) in
2026-10. Checked against them on 2025-26: team shot, goal, and attempt
counts match exactly; xG% correlates at r = 0.978 (team) and 0.961
(skater, on-ice), since the xG model is ours.

Runs after ingest_xg.py, which stores the per-game rows. A table whose
games aren't nearly all stored yet (MIN_COVERAGE) is left as it was, so a
backfill in progress never shows partial seasons.

Usage:
    python ingest_advanced_stats.py                # current season
    python ingest_advanced_stats.py --season 20252026
"""

import argparse
import os
from collections import defaultdict

import psycopg2
import requests
from dotenv import load_dotenv

import player_values as pv
from logging_config import setup_logging
from seasons import current_season_id

load_dotenv()

DATABASE_URL = os.environ["DATABASE_URL"]
MIN_COVERAGE = 0.95  # share of the season's games (team_game_xg) with 5-on-5 rows before a table is rebuilt
NHL_SKATER_5V5_REPORTS = ("summaryshooting", "percentages")

logger = setup_logging("ingest_advanced_stats")


def _pdo(goals_for, shots_for, goals_against, shots_against):
    if not shots_for or not shots_against:
        return None
    shooting_pct = goals_for / shots_for
    save_pct = 1 - (goals_against / shots_against)
    return (shooting_pct + save_pct) * 100


def _pct(for_, against):
    return for_ / (for_ + against) if (for_ or 0) + (against or 0) else None


def coverage(cur, season_id):
    """Share of the season's scored regular-season games (team_game_xg) that have 5-on-5 rows."""
    cur.execute("SELECT COUNT(DISTINCT game_id) FROM team_game_xg WHERE season_id = %s AND game_type = 2", (season_id,))
    games = cur.fetchone()[0]
    cur.execute("SELECT COUNT(DISTINCT game_id) FROM team_game_5v5 WHERE season_id = %s AND game_type = 2", (season_id,))
    return cur.fetchone()[0] / games if games else 0.0


def team_stats(rows):
    """team_advanced_stats rows from [(team, games, cf, ca, ff, fa, sf, sa, gf, ga, xgf, xga)] season sums."""
    out = []
    for team, games, cf, ca, ff, fa, sf, sa, gf, ga, xgf, xga in rows:
        xgf, xga = float(xgf), float(xga)
        out.append({
            "team_abbrev": team, "games_played": games,
            "corsi_for_pct": _pct(cf, ca), "fenwick_for_pct": _pct(ff, fa), "xgoals_for_pct": _pct(xgf, xga),
            "xgoals_for": round(xgf, 3), "xgoals_against": round(xga, 3),
            "goals_for": gf, "goals_against": ga, "shots_on_goal_for": sf, "shots_on_goal_against": sa,
            "pdo": _pdo(gf, sf, ga, sa),
        })
    return out


def fetch_nhl_skaters_5v5(year):
    """{player_id: row}: the NHL's 5-on-5 shot-attempt and percentage reports, merged."""
    merged = defaultdict(dict)
    for report in NHL_SKATER_5V5_REPORTS:
        response = requests.get(pv.NHL_SKATER_URL.format(report=report, season=f"{year}{year + 1}"), timeout=60)
        response.raise_for_status()
        for row in response.json()["data"]:
            merged[row["playerId"]].update(row)
    return merged


def skater_stats(nhl, ours):
    """
    player_advanced_stats rows: nhl from fetch_nhl_skaters_5v5(), ours
    {player_id: (ixg, on-ice xgf, on-ice xga)} season sums. A skater
    without our rows yet gets the NHL's numbers and no xG.
    """
    out = []
    for pid, r in nhl.items():
        gp = int(r.get("gamesPlayed") or 0)
        if not gp:
            continue
        ixg, xgf, xga = ours.get(pid, (None, None, None))
        pdo = r.get("skaterShootingPlusSavePct5v5")
        out.append({
            "player_id": pid, "games_played": gp,
            "icetime_seconds": round((r.get("timeOnIcePerGame5v5") or 0) * gp),
            "corsi_for_pct": _pct(r.get("satFor"), r.get("satAgainst")),
            "fenwick_for_pct": _pct(r.get("usatFor"), r.get("usatAgainst")),
            "xgoals_for_pct": _pct(xgf, xga) if xgf is not None else None,
            "xgoals_for": xgf, "xgoals_against": xga, "individual_xgoals": ixg,
            "pdo": round(pdo * 100, 2) if pdo is not None else None,
        })
    return out


def goalie_stats(nhl_rows, ours):
    """
    goalie_advanced_stats rows: nhl_rows the NHL's goalie summary, ours
    {player_id: (goals against, xg against, hd shots, hd goals, hd xg)}.
    """
    out = []
    for r in nhl_rows:
        pid = r["playerId"]
        if pid not in ours:
            continue
        ga, xga, hd_shots, hd_goals, hd_xg = ours[pid]
        out.append({
            "player_id": pid, "games_played": r.get("gamesPlayed"), "icetime_seconds": r.get("timeOnIce"),
            "shots_faced": r.get("shotsAgainst"), "goals_allowed": ga, "xgoals_against": xga,
            "high_danger_shots": hd_shots, "high_danger_goals": hd_goals, "high_danger_xgoals": hd_xg,
        })
    return out


def save_goalie_stats(cur, season_id, stats, valid_player_ids):
    saved = 0
    for stat in stats:
        if stat["player_id"] not in valid_player_ids:
            continue  # same FK reasoning as save_player_stats
        cur.execute(
            """
            INSERT INTO goalie_advanced_stats (
                player_id, season_id, games_played, icetime_seconds, shots_faced, goals_allowed,
                xgoals_against, high_danger_shots, high_danger_goals, high_danger_xgoals, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (season_id, player_id) DO UPDATE SET
                games_played = EXCLUDED.games_played,
                icetime_seconds = EXCLUDED.icetime_seconds,
                shots_faced = EXCLUDED.shots_faced,
                goals_allowed = EXCLUDED.goals_allowed,
                xgoals_against = EXCLUDED.xgoals_against,
                high_danger_shots = EXCLUDED.high_danger_shots,
                high_danger_goals = EXCLUDED.high_danger_goals,
                high_danger_xgoals = EXCLUDED.high_danger_xgoals,
                updated_at = NOW()
            """,
            (
                stat["player_id"], season_id, stat["games_played"], stat["icetime_seconds"], stat["shots_faced"],
                stat["goals_allowed"], stat["xgoals_against"], stat["high_danger_shots"],
                stat["high_danger_goals"], stat["high_danger_xgoals"],
            ),
        )
        saved += 1
    return saved


def fetch_valid_team_abbrevs(cur):
    cur.execute("SELECT team_abbrev FROM teams")
    return {r[0] for r in cur.fetchall()}


def fetch_valid_player_ids(cur):
    cur.execute("SELECT player_id FROM players")
    return {r[0] for r in cur.fetchall()}


def save_team_stats(cur, season_id, stats, valid_team_abbrevs):
    saved = 0
    for stat in stats:
        if stat["team_abbrev"] not in valid_team_abbrevs:
            # Franchise relocation/rename mismatch between MoneyPuck and our
            # own teams table (shouldn't normally happen -- both use the
            # NHL's current abbreviations -- but skip rather than violate
            # the FK if it ever does).
            continue
        cur.execute(
            """
            INSERT INTO team_advanced_stats (
                team_abbrev, season_id, games_played, corsi_for_pct, fenwick_for_pct,
                xgoals_for_pct, xgoals_for, xgoals_against, goals_for, goals_against,
                shots_on_goal_for, shots_on_goal_against, pdo, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (season_id, team_abbrev) DO UPDATE SET
                games_played = EXCLUDED.games_played,
                corsi_for_pct = EXCLUDED.corsi_for_pct,
                fenwick_for_pct = EXCLUDED.fenwick_for_pct,
                xgoals_for_pct = EXCLUDED.xgoals_for_pct,
                xgoals_for = EXCLUDED.xgoals_for,
                xgoals_against = EXCLUDED.xgoals_against,
                goals_for = EXCLUDED.goals_for,
                goals_against = EXCLUDED.goals_against,
                shots_on_goal_for = EXCLUDED.shots_on_goal_for,
                shots_on_goal_against = EXCLUDED.shots_on_goal_against,
                pdo = EXCLUDED.pdo,
                updated_at = NOW()
            """,
            (
                stat["team_abbrev"], season_id, stat["games_played"], stat["corsi_for_pct"],
                stat["fenwick_for_pct"], stat["xgoals_for_pct"], stat["xgoals_for"],
                stat["xgoals_against"], stat["goals_for"], stat["goals_against"],
                stat["shots_on_goal_for"], stat["shots_on_goal_against"], stat["pdo"],
            ),
        )
        saved += 1
    return saved


def save_player_stats(cur, season_id, stats, valid_player_ids):
    saved = 0
    for stat in stats:
        if stat["player_id"] not in valid_player_ids:
            # Not on a current roster (waived/demoted/retired since our
            # roster snapshot, or a call-up who's since been sent down) --
            # not shown anywhere in the app, so skip rather than violate
            # the FK on players.
            continue
        cur.execute(
            """
            INSERT INTO player_advanced_stats (
                player_id, season_id, games_played, icetime_seconds, corsi_for_pct,
                fenwick_for_pct, xgoals_for_pct, xgoals_for, xgoals_against,
                individual_xgoals, pdo, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (season_id, player_id) DO UPDATE SET
                games_played = EXCLUDED.games_played,
                icetime_seconds = EXCLUDED.icetime_seconds,
                corsi_for_pct = EXCLUDED.corsi_for_pct,
                fenwick_for_pct = EXCLUDED.fenwick_for_pct,
                xgoals_for_pct = EXCLUDED.xgoals_for_pct,
                xgoals_for = EXCLUDED.xgoals_for,
                xgoals_against = EXCLUDED.xgoals_against,
                individual_xgoals = EXCLUDED.individual_xgoals,
                pdo = EXCLUDED.pdo,
                updated_at = NOW()
            """,
            (
                stat["player_id"], season_id, stat["games_played"], stat["icetime_seconds"],
                stat["corsi_for_pct"], stat["fenwick_for_pct"], stat["xgoals_for_pct"],
                stat["xgoals_for"], stat["xgoals_against"], stat["individual_xgoals"], stat["pdo"],
            ),
        )
        saved += 1
    return saved


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int, default=None, help="Defaults to the current season")
    args = parser.parse_args()
    season_id = args.season or current_season_id()
    year = season_id // 10000

    nhl_skaters = fetch_nhl_skaters_5v5(year)
    nhl_goalies = pv.fetch_nhl_goalies(year)
    with psycopg2.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            share = coverage(cur, season_id)
            if share < MIN_COVERAGE:
                logger.warning(f"Only {share:.0%} of {season_id}'s games have 5-on-5 rows; keeping yesterday's advanced stats")
                return
            cur.execute(
                """
                SELECT team_abbrev, COUNT(*), SUM(cf), SUM(ca), SUM(ff), SUM(fa), SUM(sf), SUM(sa), SUM(gf), SUM(ga),
                       SUM(xgf), SUM(xga)
                FROM team_game_5v5 WHERE season_id = %s AND game_type = 2 GROUP BY team_abbrev
                """,
                (season_id,),
            )
            teams = team_stats(cur.fetchall())
            cur.execute(
                """
                SELECT player_id, SUM(ixg), SUM(onice_xgf), SUM(onice_xga)
                FROM player_game_5v5 WHERE season_id = %s AND game_type = 2 GROUP BY player_id
                """,
                (season_id,),
            )
            # SUM skips games without a shift chart: on-ice xG covers the games that have one.
            ours = {r[0]: tuple(round(float(v), 3) if v is not None else None for v in r[1:]) for r in cur.fetchall()}
            cur.execute(
                """
                SELECT goalie_id, SUM(goals_against), SUM(xg_against), SUM(hd_shots), SUM(hd_goals), SUM(hd_xg)
                FROM goalie_game_xg WHERE season_id = %s AND game_type = 2 GROUP BY goalie_id
                """,
                (season_id,),
            )
            goalies = {r[0]: (int(r[1]), round(float(r[2]), 3), r[3], r[4], round(float(r[5]), 3) if r[5] is not None else None)
                       for r in cur.fetchall()}

            valid_players = fetch_valid_player_ids(cur)
            teams_saved = save_team_stats(cur, season_id, teams, fetch_valid_team_abbrevs(cur))
            players_saved = save_player_stats(cur, season_id, skater_stats(nhl_skaters, ours), valid_players)
            goalies_saved = save_goalie_stats(cur, season_id, goalie_stats(nhl_goalies, goalies), valid_players)
        conn.commit()
    logger.info(f"Advanced stats for {season_id}: {teams_saved} teams, {players_saved} skaters, {goalies_saved} goalies")


if __name__ == "__main__":
    main()
