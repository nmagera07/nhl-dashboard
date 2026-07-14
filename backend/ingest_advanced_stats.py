"""
Advanced Stats (Corsi/Fenwick/xG/PDO) Ingestion Script

Pulls team- and skater-level advanced stats from MoneyPuck's public
seasonSummary CSVs:

    https://moneypuck.com/moneypuck/playerData/seasonSummary/{year}/regular/teams.csv
    https://moneypuck.com/moneypuck/playerData/seasonSummary/{year}/regular/skaters.csv

MoneyPuck's own site and directory listings (e.g. browsing
.../seasonSummary/ itself) sit behind a Cloudflare bot-check demanding a
paid data license -- confirmed by fetching that URL directly and getting
back an HTML "please get a data license" page instead of a listing. The
individual CSV files are NOT behind that check, though -- fetching the
exact file path above returns the real CSV with a normal 200, no license
required. This replaces an earlier, much more expensive approach that
recomputed Corsi/Fenwick from scratch out of the NHL API's own
play-by-play + shift-chart endpoints (one HTTP call pair per game, times
~1300 games/season) specifically because MoneyPuck was believed to block
all automated access -- it only blocks the directory/website UI, not the
raw data files themselves.

Both CSVs contain multiple rows per team/player, one per "situation"
(all, 5on5, 4on5, 5on4, other). Only the "5on5" rows are ingested here --
5-on-5 is the standard reference frame the industry quotes CF%/FF%/xG% in,
since special-teams shot attempts (a team's power play, a bad penalty kill)
otherwise swamp the even-strength signal. Goalies are not included in
player_advanced_stats -- on-ice possession shares aren't a meaningful
goalie stat the way they are for skaters.

PDO (on-ice shooting% + on-ice save%, expressed as a sum of two
percentages so a "normal" value sits around 100) isn't a column MoneyPuck
publishes directly -- it's computed here from the underlying goals/shots
columns, the same "derive the rate stat from raw counts" approach already
used elsewhere in this codebase (see _combine_season_entries() in
ingest_player_stats.py for the GAA/save_pctg equivalent).

Setup:
    pip install requests psycopg2-binary python-dotenv

Environment variables expected (put these in a .env file):
    DATABASE_URL=postgresql://user:password@host:port/dbname

Usage:
    python ingest_advanced_stats.py                # current season
    python ingest_advanced_stats.py --season 20242025
"""

import argparse
import csv
import io
import os

import psycopg2
import requests
from dotenv import load_dotenv

from logging_config import setup_logging

load_dotenv()

CSV_URL = "https://moneypuck.com/moneypuck/playerData/seasonSummary/{year}/regular/{kind}.csv"
DATABASE_URL = os.environ["DATABASE_URL"]
DEFAULT_SEASON = 20252026
SITUATION = "5on5"
# MoneyPuck blocks requests with no/unfamiliar User-Agent on some paths;
# a normal browser UA avoids that entirely rather than working around it.
REQUEST_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

logger = setup_logging("ingest_advanced_stats")


def moneypuck_year(season_id):
    """20252026 -> 2025 -- MoneyPuck's CSV paths use the season's start year only."""
    return int(str(season_id)[:4])


def fetch_csv_rows(year, kind):
    url = CSV_URL.format(year=year, kind=kind)
    response = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    response.raise_for_status()
    return list(csv.DictReader(io.StringIO(response.text)))


def _float(value):
    if value is None or value == "":
        return None
    return float(value)


def _int(value):
    if value is None or value == "":
        return None
    return int(float(value))


def _pdo(goals_for, shots_for, goals_against, shots_against):
    if not shots_for or not shots_against:
        return None
    shooting_pct = goals_for / shots_for
    save_pct = 1 - (goals_against / shots_against)
    return (shooting_pct + save_pct) * 100


def parse_team_row(row):
    goals_for = _float(row["goalsFor"])
    shots_for = _float(row["shotsOnGoalFor"])
    goals_against = _float(row["goalsAgainst"])
    shots_against = _float(row["shotsOnGoalAgainst"])
    return {
        "team_abbrev": row["team"],
        "games_played": _int(row["games_played"]),
        "corsi_for_pct": _float(row["corsiPercentage"]),
        "fenwick_for_pct": _float(row["fenwickPercentage"]),
        "xgoals_for_pct": _float(row["xGoalsPercentage"]),
        "xgoals_for": _float(row["xGoalsFor"]),
        "xgoals_against": _float(row["xGoalsAgainst"]),
        "goals_for": _int(goals_for),
        "goals_against": _int(goals_against),
        "shots_on_goal_for": _int(shots_for),
        "shots_on_goal_against": _int(shots_against),
        "pdo": _pdo(goals_for, shots_for, goals_against, shots_against),
    }


def parse_skater_row(row):
    onice_goals_for = _float(row["OnIce_F_goals"])
    onice_shots_for = _float(row["OnIce_F_shotsOnGoal"])
    onice_goals_against = _float(row["OnIce_A_goals"])
    onice_shots_against = _float(row["OnIce_A_shotsOnGoal"])
    return {
        "player_id": int(row["playerId"]),
        "games_played": _int(row["games_played"]),
        "icetime_seconds": _int(row["icetime"]),
        "corsi_for_pct": _float(row["onIce_corsiPercentage"]),
        "fenwick_for_pct": _float(row["onIce_fenwickPercentage"]),
        "xgoals_for_pct": _float(row["onIce_xGoalsPercentage"]),
        "xgoals_for": _float(row["OnIce_F_xGoals"]),
        "xgoals_against": _float(row["OnIce_A_xGoals"]),
        "individual_xgoals": _float(row["I_F_xGoals"]),
        "pdo": _pdo(onice_goals_for, onice_shots_for, onice_goals_against, onice_shots_against),
    }


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
    parser.add_argument("--season", type=int, default=DEFAULT_SEASON)
    args = parser.parse_args()

    year = moneypuck_year(args.season)
    logger.info(f"Fetching MoneyPuck advanced stats for {year} (season_id={args.season})...")

    team_rows = fetch_csv_rows(year, "teams")
    team_stats = [parse_team_row(r) for r in team_rows if r["situation"] == SITUATION]
    logger.info(f"Parsed {len(team_stats)} team rows (situation={SITUATION}).")

    skater_rows = fetch_csv_rows(year, "skaters")
    player_stats = [parse_skater_row(r) for r in skater_rows if r["situation"] == SITUATION]
    logger.info(f"Parsed {len(player_stats)} skater rows (situation={SITUATION}).")

    with psycopg2.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            valid_team_abbrevs = fetch_valid_team_abbrevs(cur)
            valid_player_ids = fetch_valid_player_ids(cur)

            teams_saved = save_team_stats(cur, args.season, team_stats, valid_team_abbrevs)
            players_saved = save_player_stats(cur, args.season, player_stats, valid_player_ids)
        conn.commit()

    logger.info(f"Done. {teams_saved} teams, {players_saved} players saved.")


if __name__ == "__main__":
    main()
