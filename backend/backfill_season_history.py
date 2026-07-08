"""
Season History Backfill — one-time script

Pulls final standings for each of the last N completed NHL seasons and
stores one row per team per season in season_final_standings. This is
separate from the daily standings_snapshots ingestion (ingest_standings.py)
and only needs to be run once (or again later to extend the range).

Setup:
    pip install requests psycopg2-binary python-dotenv

Environment variables expected (put these in a .env file):
    DATABASE_URL=postgresql://user:password@host:port/dbname

Usage:
    python backfill_season_history.py --years 5
"""

import argparse
import os
from datetime import date

import psycopg2
import requests
from dotenv import load_dotenv

load_dotenv()

STANDINGS_SEASON_URL = "https://api-web.nhle.com/v1/standings-season"
STANDINGS_BY_DATE_URL = "https://api-web.nhle.com/v1/standings/{date}"
DATABASE_URL = os.environ["DATABASE_URL"]

# clinchIndicator on the final day of a season: 'p' = Presidents' Trophy,
# 'z'/'y'/'x' = clinched a playoff spot (division/division-runner-up/wildcard),
# 'e' = eliminated. Absent shouldn't happen once a season is fully over.
PLAYOFF_CLINCH_CODES = {"p", "z", "y", "x"}


def fetch_recent_completed_seasons(n):
    """Return the last n completed seasons as (season_id, standings_end_date)."""
    response = requests.get(STANDINGS_SEASON_URL, timeout=15)
    response.raise_for_status()
    seasons = response.json()["seasons"]

    today = date.today().isoformat()
    completed = [s for s in seasons if s.get("standingsEnd") and s["standingsEnd"] < today]
    completed.sort(key=lambda s: s["id"])
    return [(s["id"], s["standingsEnd"]) for s in completed[-n:]]


def fetch_final_standings(standings_end_date):
    """Pull the standings as of a season's final date."""
    url = STANDINGS_BY_DATE_URL.format(date=standings_end_date)
    response = requests.get(url, timeout=15)
    response.raise_for_status()
    return response.json()["standings"]


def upsert_season_row(cur, season_id, team):
    cur.execute(
        """
        INSERT INTO season_final_standings (
            season_id, team_abbrev, games_played, wins, losses, ot_losses,
            points, point_pctg, goal_for, goal_against, goal_differential,
            division_sequence, conference_sequence, league_sequence,
            made_playoffs
        ) VALUES (
            %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s,
            %s, %s, %s,
            %s
        )
        ON CONFLICT (season_id, team_abbrev) DO UPDATE SET
            games_played = EXCLUDED.games_played,
            wins = EXCLUDED.wins,
            losses = EXCLUDED.losses,
            ot_losses = EXCLUDED.ot_losses,
            points = EXCLUDED.points,
            point_pctg = EXCLUDED.point_pctg,
            goal_for = EXCLUDED.goal_for,
            goal_against = EXCLUDED.goal_against,
            goal_differential = EXCLUDED.goal_differential,
            division_sequence = EXCLUDED.division_sequence,
            conference_sequence = EXCLUDED.conference_sequence,
            league_sequence = EXCLUDED.league_sequence,
            made_playoffs = EXCLUDED.made_playoffs
        """,
        (
            season_id,
            team["teamAbbrev"]["default"],
            team["gamesPlayed"],
            team["wins"],
            team["losses"],
            team["otLosses"],
            team["points"],
            team["pointPctg"],
            team["goalFor"],
            team["goalAgainst"],
            team["goalDifferential"],
            team["divisionSequence"],
            team["conferenceSequence"],
            team["leagueSequence"],
            team.get("clinchIndicator") in PLAYOFF_CLINCH_CODES,
        ),
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--years", type=int, default=5, help="How many completed seasons to backfill")
    args = parser.parse_args()

    seasons = fetch_recent_completed_seasons(args.years)

    conn = psycopg2.connect(DATABASE_URL)
    try:
        with conn:
            with conn.cursor() as cur:
                for season_id, standings_end in seasons:
                    teams = fetch_final_standings(standings_end)
                    for team in teams:
                        upsert_season_row(cur, season_id, team)
                    print(f"Backfilled {len(teams)} teams for season {season_id} (as of {standings_end})")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
