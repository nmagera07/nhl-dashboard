"""
NHL Standings Ingestion Script

Pulls current standings from the NHL's public API and stores a daily
snapshot in Postgres. Run this once a day (via cron, a scheduled Lambda,
or manually) to build up a history you can chart trends from.

Setup:
    pip install requests psycopg2-binary python-dotenv

Environment variables expected (put these in a .env file):
    DATABASE_URL=postgresql://user:password@host:port/dbname
"""

import os
import requests
import psycopg2
from datetime import date
from dotenv import load_dotenv

load_dotenv()

NHL_STANDINGS_URL = "https://api-web.nhle.com/v1/standings/now"
DATABASE_URL = os.environ["DATABASE_URL"]


def fetch_standings():
    """Pull the current standings from the NHL API."""
    response = requests.get(NHL_STANDINGS_URL, timeout=15)
    response.raise_for_status()
    return response.json()


def upsert_team(cur, team):
    """Insert or update a team's static info."""
    cur.execute(
        """
        INSERT INTO teams (team_abbrev, team_name, common_name, place_name,
                            conference, division, logo_url)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (team_abbrev) DO UPDATE SET
            team_name = EXCLUDED.team_name,
            common_name = EXCLUDED.common_name,
            place_name = EXCLUDED.place_name,
            conference = EXCLUDED.conference,
            division = EXCLUDED.division,
            logo_url = EXCLUDED.logo_url
        """,
        (
            team["teamAbbrev"]["default"],
            team["teamName"]["default"],
            team["teamCommonName"]["default"],
            team["placeName"]["default"],
            team["conferenceName"],
            team["divisionName"],
            team["teamLogo"],
        ),
    )


def insert_snapshot(cur, snapshot_date, team):
    """Insert today's standings row for one team."""
    cur.execute(
        """
        INSERT INTO standings_snapshots (
            snapshot_date, team_abbrev, season_id, games_played,
            wins, losses, ot_losses, points, point_pctg,
            goal_for, goal_against, goal_differential,
            home_wins, home_losses, road_wins, road_losses,
            l10_wins, l10_losses, l10_ot_losses,
            streak_code, streak_count,
            division_sequence, conference_sequence, league_sequence,
            wildcard_sequence
        ) VALUES (
            %s, %s, %s, %s,
            %s, %s, %s, %s, %s,
            %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s, %s,
            %s, %s,
            %s, %s, %s,
            %s
        )
        ON CONFLICT (snapshot_date, team_abbrev) DO NOTHING
        """,
        (
            snapshot_date,
            team["teamAbbrev"]["default"],
            team["seasonId"],
            team["gamesPlayed"],
            team["wins"],
            team["losses"],
            team["otLosses"],
            team["points"],
            team["pointPctg"],
            team["goalFor"],
            team["goalAgainst"],
            team["goalDifferential"],
            team["homeWins"],
            team["homeLosses"],
            team["roadWins"],
            team["roadLosses"],
            team["l10Wins"],
            team["l10Losses"],
            team["l10OtLosses"],
            team["streakCode"],
            team["streakCount"],
            team["divisionSequence"],
            team["conferenceSequence"],
            team["leagueSequence"],
            team["wildcardSequence"],
        ),
    )


def main():
    data = fetch_standings()
    teams = data["standings"]
    today = date.today()

    conn = psycopg2.connect(DATABASE_URL)
    try:
        with conn:
            with conn.cursor() as cur:
                for team in teams:
                    upsert_team(cur, team)
                    insert_snapshot(cur, today, team)
        print(f"Ingested {len(teams)} team standings for {today}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
