"""
Playoff Odds Simulator

Monte Carlo simulation of the rest of the season to estimate each team's
probability of making the playoffs. A full Elo rating system would need
every historical game reprocessed to build ratings; instead this uses a
simpler team-strength proxy (current point percentage) run through a
logistic win-probability formula. Less accurate than a proper Elo model,
much less to build and maintain for a fun dashboard feature.

How it works:
  1. Take each team's points/games played as of a given date.
  2. Pull the remaining regular-season schedule (games after that date)
     from the NHL API.
  3. Run N simulated seasons: for each remaining game, pick a winner via
     the win-probability model (with a home-ice bump), and separately
     decide whether it went to overtime/shootout (~23% of NHL games
     historically) -- if so, the loser still banks a point.
  4. After all remaining games are simulated, work out that trial's 16
     playoff teams (top 3 per division, next 2 per conference by points,
     ties broken by wins).
  5. Playoff odds = fraction of trials a team made the 16.

The as-of standings come straight from the NHL's historical
/v1/standings/{date} endpoint rather than our own standings_snapshots
table, since daily ingestion here only started this week -- we don't have
snapshots for arbitrary past dates to backtest against. Once the new
season is underway, running this with no --as-of gives live in-season odds.

Setup:
    pip install requests psycopg2-binary python-dotenv

Environment variables expected (put these in a .env file):
    DATABASE_URL=postgresql://user:password@host:port/dbname

Usage:
    python simulate_playoff_odds.py --as-of 2026-02-01  # backtest a past date
    python simulate_playoff_odds.py  # live: today's date, current season

--season defaults to whichever season --as-of falls in, so it rarely needs
to be passed explicitly -- see current_season_id().

Scheduled via Windows Task Scheduler ("NHL Playoff Odds Simulation", daily
6:10am, mirroring the existing "NHL Standings Ingestion" task). It's a
no-op during the off-season (the NHL API returns no standings for a date
outside any season's window), and needs no changes to keep working once
the next season starts.
"""

import argparse
import os
import random
from collections import defaultdict
from datetime import date

import psycopg2
import psycopg2.extras
import requests
from dotenv import load_dotenv

from logging_config import setup_logging

load_dotenv()

DATABASE_URL = os.environ["DATABASE_URL"]

logger = setup_logging("simulate_playoff_odds")
STANDINGS_URL = "https://api-web.nhle.com/v1/standings/{date}"
SCHEDULE_URL = "https://api-web.nhle.com/v1/club-schedule-season/{team}/{season}"

HOME_ICE_BUMP = 0.02   # added to the home team's effective point pctg
OT_PROBABILITY = 0.23  # league-average share of games going to OT/SO
WIN_PROB_SCALE = 2.0   # logistic steepness
DEFAULT_TRIALS = 10000


def current_season_id(today=None):
    """
    NHL seasons start in Oct and end the following spring, so derive the
    season id from today's date rather than hardcoding it -- otherwise a
    scheduled run in a future season would keep pulling the wrong season's
    schedule. Jul-Dec -> season starts this year; Jan-Jun -> it started
    last year.
    """
    today = today or date.today()
    start_year = today.year if today.month >= 7 else today.year - 1
    return int(f"{start_year}{start_year + 1}")


def win_probability(home_pctg, away_pctg):
    diff = (home_pctg + HOME_ICE_BUMP) - away_pctg
    return 1 / (1 + 10 ** (-diff * WIN_PROB_SCALE))


def fetch_standings_as_of(as_of_date):
    url = STANDINGS_URL.format(date=as_of_date)
    response = requests.get(url, timeout=15)
    response.raise_for_status()
    standings = {}
    for team in response.json()["standings"]:
        games_played = team["gamesPlayed"] or 1  # avoid div-by-zero on day 1
        standings[team["teamAbbrev"]["default"]] = {
            "points": team["points"],
            "games_played": games_played,
            "wins": team["wins"],
            "point_pctg": team["points"] / (games_played * 2),
            "division": team["divisionName"],
            "conference": team["conferenceName"],
        }
    return standings


def fetch_remaining_games(team_abbrev, season_id, as_of_date):
    url = SCHEDULE_URL.format(team=team_abbrev, season=season_id)
    response = requests.get(url, timeout=15)
    response.raise_for_status()
    games = response.json()["games"]
    return [g for g in games if g["gameType"] == 2 and g["gameDate"] > str(as_of_date)]


def build_schedule(team_abbrevs, season_id, as_of_date):
    """Unique remaining regular-season games as (home, away) pairs."""
    seen = {}
    for team in team_abbrevs:
        for g in fetch_remaining_games(team, season_id, as_of_date):
            seen[g["id"]] = (g["homeTeam"]["abbrev"], g["awayTeam"]["abbrev"])
    return list(seen.values())


def determine_playoff_teams(trial_standings, divisions, conferences):
    """trial_standings: {team_abbrev: {'points', 'wins'}}. Returns a set of 16 abbrevs."""
    playoff_teams = set()
    conference_leftovers = defaultdict(list)

    for division_teams in divisions.values():
        ranked = sorted(
            division_teams, key=lambda a: (-trial_standings[a]["points"], -trial_standings[a]["wins"])
        )
        playoff_teams.update(ranked[:3])
        conference = conferences[ranked[0]]
        conference_leftovers[conference].extend(ranked[3:])

    for teams in conference_leftovers.values():
        ranked = sorted(
            teams, key=lambda a: (-trial_standings[a]["points"], -trial_standings[a]["wins"])
        )
        playoff_teams.update(ranked[:2])

    return playoff_teams


def simulate(standings, schedule, trials):
    divisions = defaultdict(list)
    conferences = {}
    for abbrev, s in standings.items():
        divisions[s["division"]].append(abbrev)
        conferences[abbrev] = s["conference"]

    made_playoffs = defaultdict(int)

    for _ in range(trials):
        trial = {abbrev: {"points": s["points"], "wins": s["wins"]} for abbrev, s in standings.items()}

        for home, away in schedule:
            p_home = win_probability(standings[home]["point_pctg"], standings[away]["point_pctg"])
            home_wins = random.random() < p_home
            went_ot = random.random() < OT_PROBABILITY

            winner, loser = (home, away) if home_wins else (away, home)
            trial[winner]["points"] += 2
            trial[winner]["wins"] += 1
            if went_ot:
                trial[loser]["points"] += 1

        for team in determine_playoff_teams(trial, divisions, conferences):
            made_playoffs[team] += 1

    return {team: made_playoffs[team] / trials for team in standings}


def save_odds(odds, season_id, as_of_date, trials):
    with psycopg2.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            for team_abbrev, pct in odds.items():
                cur.execute(
                    """
                    INSERT INTO playoff_odds (season_id, as_of_date, team_abbrev, playoff_pct, trials, computed_at)
                    VALUES (%s, %s, %s, %s, %s, NOW())
                    ON CONFLICT (season_id, as_of_date, team_abbrev) DO UPDATE SET
                        playoff_pct = EXCLUDED.playoff_pct,
                        trials = EXCLUDED.trials,
                        computed_at = NOW()
                    """,
                    (season_id, as_of_date, team_abbrev, pct, trials),
                )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int, default=None, help="Defaults to the season --as-of falls in")
    parser.add_argument("--as-of", type=str, default=str(date.today()))
    parser.add_argument("--trials", type=int, default=DEFAULT_TRIALS)
    parser.add_argument("--no-save", action="store_true", help="Print results without writing to the DB")
    args = parser.parse_args()

    if args.season is None:
        as_of_parsed = date.fromisoformat(args.as_of)
        args.season = current_season_id(as_of_parsed)

    standings = fetch_standings_as_of(args.as_of)
    logger.info(f"Loaded standings for {len(standings)} teams as of {args.as_of}")

    schedule = build_schedule(list(standings.keys()), args.season, args.as_of)
    logger.info(f"{len(schedule)} remaining games to simulate across {args.trials} trials")

    odds = simulate(standings, schedule, args.trials)

    if not args.no_save:
        save_odds(odds, args.season, args.as_of, args.trials)

    for team, pct in sorted(odds.items(), key=lambda x: -x[1]):
        logger.info(f"{team}: {pct * 100:.1f}%")


if __name__ == "__main__":
    main()
