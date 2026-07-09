"""
Player Roster & Season Stats Ingestion Script

Pulls the current roster for all 32 teams and each player's season-to-date
stats from the NHL's public API, storing them in Postgres. Unlike the daily
standings ingestion, this doesn't need to run every day -- player stats are
already season totals in one API call, so a weekly run is plenty during the
season (and none needed in the off-season).

Setup:
    pip install requests psycopg2-binary python-dotenv

Environment variables expected (put these in a .env file):
    DATABASE_URL=postgresql://user:password@host:port/dbname

Usage:
    python ingest_player_stats.py
"""

import os
import time

import psycopg2
import requests
from dotenv import load_dotenv

load_dotenv()

ROSTER_URL = "https://api-web.nhle.com/v1/roster/{team}/current"
PLAYER_LANDING_URL = "https://api-web.nhle.com/v1/player/{player_id}/landing"
DATABASE_URL = os.environ["DATABASE_URL"]

# Be polite to a free public API with no documented rate limit.
REQUEST_DELAY_SECONDS = 0.15


def fetch_team_abbrevs(cur):
    cur.execute("SELECT team_abbrev FROM teams ORDER BY team_abbrev")
    return [row[0] for row in cur.fetchall()]


def fetch_roster(team_abbrev):
    url = ROSTER_URL.format(team=team_abbrev)
    response = requests.get(url, timeout=15)
    response.raise_for_status()
    data = response.json()
    return data["forwards"] + data["defensemen"] + data["goalies"]


def fetch_player_landing(player_id):
    url = PLAYER_LANDING_URL.format(player_id=player_id)
    response = requests.get(url, timeout=15)
    response.raise_for_status()
    return response.json()


def upsert_player(cur, team_abbrev, player):
    cur.execute(
        """
        INSERT INTO players (
            player_id, team_abbrev, first_name, last_name, position_code,
            sweater_number, shoots_catches, height_in_inches, weight_in_pounds,
            birth_date, birth_city, birth_country, headshot_url, updated_at
        ) VALUES (
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s, %s, %s, NOW()
        )
        ON CONFLICT (player_id) DO UPDATE SET
            team_abbrev = EXCLUDED.team_abbrev,
            first_name = EXCLUDED.first_name,
            last_name = EXCLUDED.last_name,
            position_code = EXCLUDED.position_code,
            sweater_number = EXCLUDED.sweater_number,
            shoots_catches = EXCLUDED.shoots_catches,
            height_in_inches = EXCLUDED.height_in_inches,
            weight_in_pounds = EXCLUDED.weight_in_pounds,
            birth_date = EXCLUDED.birth_date,
            birth_city = EXCLUDED.birth_city,
            birth_country = EXCLUDED.birth_country,
            headshot_url = EXCLUDED.headshot_url,
            updated_at = NOW()
        """,
        (
            player["id"],
            team_abbrev,
            player["firstName"]["default"],
            player["lastName"]["default"],
            player["positionCode"],
            player.get("sweaterNumber"),
            player.get("shootsCatches"),
            player.get("heightInInches"),
            player.get("weightInPounds"),
            player.get("birthDate"),
            player.get("birthCity", {}).get("default"),
            player.get("birthCountry"),
            player.get("headshot"),
        ),
    )


def upsert_season_stats(cur, player_id, landing):
    featured = landing.get("featuredStats")
    if not featured or featured.get("season") is None:
        return False

    sub_season = featured.get("regularSeason", {}).get("subSeason")
    if not sub_season:
        return False

    cur.execute(
        """
        INSERT INTO player_season_stats (
            player_id, season_id, games_played,
            goals, assists, points, plus_minus, pim, shots, shooting_pctg,
            power_play_goals, power_play_points, shorthanded_goals,
            shorthanded_points, game_winning_goals, ot_goals,
            wins, losses, ot_losses, goals_against_avg, save_pctg, shutouts,
            updated_at
        ) VALUES (
            %s, %s, %s,
            %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s,
            %s, %s, %s,
            %s, %s, %s, %s, %s, %s,
            NOW()
        )
        ON CONFLICT (season_id, player_id) DO UPDATE SET
            games_played = EXCLUDED.games_played,
            goals = EXCLUDED.goals,
            assists = EXCLUDED.assists,
            points = EXCLUDED.points,
            plus_minus = EXCLUDED.plus_minus,
            pim = EXCLUDED.pim,
            shots = EXCLUDED.shots,
            shooting_pctg = EXCLUDED.shooting_pctg,
            power_play_goals = EXCLUDED.power_play_goals,
            power_play_points = EXCLUDED.power_play_points,
            shorthanded_goals = EXCLUDED.shorthanded_goals,
            shorthanded_points = EXCLUDED.shorthanded_points,
            game_winning_goals = EXCLUDED.game_winning_goals,
            ot_goals = EXCLUDED.ot_goals,
            wins = EXCLUDED.wins,
            losses = EXCLUDED.losses,
            ot_losses = EXCLUDED.ot_losses,
            goals_against_avg = EXCLUDED.goals_against_avg,
            save_pctg = EXCLUDED.save_pctg,
            shutouts = EXCLUDED.shutouts,
            updated_at = NOW()
        """,
        (
            player_id,
            featured["season"],
            sub_season.get("gamesPlayed"),
            sub_season.get("goals"),
            sub_season.get("assists"),
            sub_season.get("points"),
            sub_season.get("plusMinus"),
            sub_season.get("pim"),
            sub_season.get("shots"),
            sub_season.get("shootingPctg"),
            sub_season.get("powerPlayGoals"),
            sub_season.get("powerPlayPoints"),
            sub_season.get("shorthandedGoals"),
            sub_season.get("shorthandedPoints"),
            sub_season.get("gameWinningGoals"),
            sub_season.get("otGoals"),
            sub_season.get("wins"),
            sub_season.get("losses"),
            sub_season.get("otLosses"),
            sub_season.get("goalsAgainstAvg"),
            sub_season.get("savePctg"),
            sub_season.get("shutouts"),
        ),
    )
    return True


def main():
    # Neon's serverless Postgres will drop an idle connection, and a full
    # run takes several minutes of mostly-HTTP time -- so open a fresh
    # connection per team rather than holding one open for the whole run.
    # That also means a dropped connection only costs one team's progress,
    # not the whole run (re-running is safe either way, it's all upserts).
    with psycopg2.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            team_abbrevs = fetch_team_abbrevs(cur)

    total_players = 0
    total_with_stats = 0
    for team_abbrev in team_abbrevs:
        roster = fetch_roster(team_abbrev)
        time.sleep(REQUEST_DELAY_SECONDS)

        landings = []
        for player in roster:
            landings.append((player, fetch_player_landing(player["id"])))
            time.sleep(REQUEST_DELAY_SECONDS)

        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor() as cur:
                for player in roster:
                    upsert_player(cur, team_abbrev, player)
                for player, landing in landings:
                    if upsert_season_stats(cur, player["id"], landing):
                        total_with_stats += 1

        total_players += len(roster)
        print(f"{team_abbrev}: ingested {len(roster)} players")

    print(f"Done. {total_players} players total, {total_with_stats} with season stats.")


if __name__ == "__main__":
    main()
