"""
Calibrate the playoff odds model's game-level constants from real results.

simulate_playoff_odds.py turns two teams' strength ratings (goal
differential per game) into a home-win probability with a logistic curve:

    P(home wins) = 1 / (1 + exp(-(r_home - r_away + HOME_EDGE) / SCALE))

This script fits HOME_EDGE and SCALE by maximum likelihood on completed
regular-season games, rating each team by its full-season goal
differential per game (from season_final_standings). It also measures how
often games go to overtime and, of those, how many reach a shootout.

Run it occasionally (e.g. each offseason) and copy the printed constants
into simulate_playoff_odds.py. It only reads: the NHL API and the
season_final_standings table.

Usage:
    python calibrate_playoff_model.py                  # last 3 seasons
    python calibrate_playoff_model.py --seasons 20242025 20252026
"""

import argparse
import math
import os
import time

import psycopg2
import requests
from dotenv import load_dotenv

load_dotenv()

SCHEDULE_URL = "https://api-web.nhle.com/v1/club-schedule-season/{team}/{season}"


def final_ratings(cur, season_id):
    cur.execute(
        "SELECT team_abbrev, goal_differential, games_played FROM season_final_standings WHERE season_id = %s",
        (season_id,),
    )
    return {abbrev: gd / gp for abbrev, gd, gp in cur.fetchall() if gp}


def season_games(teams, season_id):
    """Completed regular-season games as (home, away, home_won, last_period)."""
    # One request at a time with a short pause: the NHL API rate-limits
    # bursts (HTTP 429). On a 429, wait (Retry-After if given) and retry.
    schedules = []
    for team in teams:
        for attempt in range(6):
            response = requests.get(SCHEDULE_URL.format(team=team, season=season_id), timeout=20)
            if response.status_code != 429:
                break
            time.sleep(int(response.headers.get("Retry-After", 0)) or 5 * (attempt + 1))
        response.raise_for_status()
        schedules.append(response.json()["games"])
        time.sleep(0.25)

    games = {}
    for schedule in schedules:
        for g in schedule:
            home, away = g["homeTeam"], g["awayTeam"]
            if g["gameType"] != 2 or g.get("gameState") not in ("OFF", "FINAL") or home.get("score") is None:
                continue
            games[g["id"]] = (
                home["abbrev"],
                away["abbrev"],
                home["score"] > away["score"],
                (g.get("gameOutcome") or {}).get("lastPeriodType", "REG"),
            )
    return list(games.values())


def log_likelihood(samples, home_edge, scale):
    total = 0.0
    for diff, home_won in samples:
        p = 1 / (1 + math.exp(-(diff + home_edge) / scale))
        p = min(max(p, 1e-12), 1 - 1e-12)
        total += math.log(p if home_won else 1 - p)
    return total


def fit(samples):
    """Coarse grid, then a finer grid around the best point."""
    best = None
    for edge_step, scale_step, edges, scales in (
        (0.02, 0.1, None, None),
        (0.002, 0.01, "fine", "fine"),
    ):
        if best is None:
            edge_values = [i * edge_step for i in range(0, 26)]          # 0.00 .. 0.50
            scale_values = [0.5 + i * scale_step for i in range(0, 46)]  # 0.5 .. 5.0
        else:
            _, e0, s0 = best
            edge_values = [e0 + (i - 10) * edge_step for i in range(21)]
            scale_values = [s0 + (i - 10) * scale_step for i in range(21) if s0 + (i - 10) * scale_step > 0]
        for e in edge_values:
            for s in scale_values:
                ll = log_likelihood(samples, e, s)
                if best is None or ll > best[0]:
                    best = (ll, e, s)
    return best


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seasons", type=int, nargs="+", default=[20232024, 20242025, 20252026])
    args = parser.parse_args()

    samples, ot, shootouts, total = [], 0, 0, 0
    with psycopg2.connect(os.environ.get("API_DATABASE_URL") or os.environ["DATABASE_URL"]) as conn:
        with conn.cursor() as cur:
            for season_id in args.seasons:
                ratings = final_ratings(cur, season_id)
                games = season_games(sorted(ratings), season_id)
                for home, away, home_won, last_period in games:
                    if home in ratings and away in ratings:
                        samples.append((ratings[home] - ratings[away], home_won))
                    total += 1
                    ot += last_period in ("OT", "SO")
                    shootouts += last_period == "SO"
                print(f"{season_id}: {len(games)} games")

    ll, home_edge, scale = fit(samples)
    home_win_rate = sum(won for _, won in samples) / len(samples)
    print(f"\n{len(samples)} games")
    print(f"Home teams won {home_win_rate:.1%}")
    print(f"HOME_EDGE = {home_edge:.3f}   # goals/game")
    print(f"SCALE     = {scale:.2f}")
    print(f"  equal teams -> home wins {1 / (1 + math.exp(-home_edge / scale)):.1%}")
    print(f"  +1.0 vs -1.0 GD/game at home -> {1 / (1 + math.exp(-(2 + home_edge) / scale)):.1%}")
    print(f"OT_PROBABILITY = {ot / total:.3f}")
    print(f"SHOOTOUT_SHARE_OF_OT = {shootouts / max(ot, 1):.3f}")


if __name__ == "__main__":
    main()
