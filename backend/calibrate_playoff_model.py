"""
Calibrate the playoff odds model's game-level constants from real results.

simulate_playoff_odds.py turns two teams' strength ratings (goal
differential per game) into a home-win probability with a logistic curve:

    P(home wins) = 1 / (1 + exp(-(r_home - r_away + margin) / SCALE))
    margin = HOME_EDGE + HOME_B2B (home on a back-to-back) + AWAY_B2B (away on one)

This script fits HOME_EDGE, SCALE and the back-to-back terms (the second
night of back-to-back games, from each team's schedule) by maximum
likelihood (Newton's method on the logistic) on completed
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
from datetime import date, timedelta

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
    """Completed regular-season games as (home, away, home_won, last_period,
    home_b2b, away_b2b): b2b = the team also played the day before."""
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
                g["gameDate"],
                home["abbrev"],
                away["abbrev"],
                home["score"] > away["score"],
                (g.get("gameOutcome") or {}).get("lastPeriodType", "REG"),
            )
    played = {}
    for day, home, away, *_ in games.values():
        played.setdefault(home, set()).add(day)
        played.setdefault(away, set()).add(day)

    def b2b(team, day):
        return str(date.fromisoformat(day) - timedelta(days=1)) in played.get(team, ())

    return [(home, away, won, last, b2b(home, day), b2b(away, day)) for day, home, away, won, last in games.values()]


def _solve(a, b):
    """Gaussian elimination for the small Newton systems below."""
    n = len(b)
    a = [row[:] for row in a]
    b = b[:]
    for i in range(n):
        for j in range(i + 1, n):
            r = a[j][i] / a[i][i]
            a[j] = [x - r * y for x, y in zip(a[j], a[i])]
            b[j] -= r * b[i]
    out = [0.0] * n
    for i in reversed(range(n)):
        out[i] = (b[i] - sum(a[i][k] * out[k] for k in range(i + 1, n))) / a[i][i]
    return out


def fit(samples):
    """
    Maximum likelihood for logit(P home win) = w0 * diff + w1 + w2 * home_b2b
    + w3 * away_b2b, then back to goals/game: SCALE = 1/w0, and each other
    term times SCALE. samples: [(rating diff, home_won, home_b2b, away_b2b)].
    Returns (mean log likelihood, HOME_EDGE, SCALE, HOME_B2B, AWAY_B2B).
    """
    w = [0.0, 0.0, 0.0, 0.0]
    rows = [([diff, 1.0, float(hb), float(ab)], 1.0 if won else 0.0) for diff, won, hb, ab in samples]
    for _ in range(50):
        grad = [0.0] * 4
        hess = [[0.0] * 4 for _ in range(4)]
        for x, y in rows:
            p = 1 / (1 + math.exp(-sum(wi * xi for wi, xi in zip(w, x))))
            for i in range(4):
                grad[i] += (p - y) * x[i]
                for j in range(4):
                    hess[i][j] += p * (1 - p) * x[i] * x[j]
        step = _solve(hess, grad)
        w = [wi - si for wi, si in zip(w, step)]
        if max(abs(s) for s in step) < 1e-10:
            break
    ll = 0.0
    for x, y in rows:
        p = min(max(1 / (1 + math.exp(-sum(wi * xi for wi, xi in zip(w, x)))), 1e-12), 1 - 1e-12)
        ll += math.log(p if y else 1 - p)
    scale = 1 / w[0]
    return ll / len(rows), w[1] * scale, scale, w[2] * scale, w[3] * scale


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seasons", type=int, nargs="+", default=[20222023, 20232024, 20242025, 20252026])
    args = parser.parse_args()

    samples, ot, shootouts, total = [], 0, 0, 0
    with psycopg2.connect(os.environ.get("API_DATABASE_URL") or os.environ["DATABASE_URL"]) as conn:
        with conn.cursor() as cur:
            for season_id in args.seasons:
                ratings = final_ratings(cur, season_id)
                games = season_games(sorted(ratings), season_id)
                for home, away, home_won, last_period, home_b2b, away_b2b in games:
                    if home in ratings and away in ratings:
                        samples.append((ratings[home] - ratings[away], home_won, home_b2b, away_b2b))
                    total += 1
                    ot += last_period in ("OT", "SO")
                    shootouts += last_period == "SO"
                print(f"{season_id}: {len(games)} games")

    ll, home_edge, scale, home_b2b, away_b2b = fit(samples)
    home_win_rate = sum(won for _, won, *_ in samples) / len(samples)
    print(f"\n{len(samples)} games, mean log likelihood {ll:.5f}")
    print(f"Home teams won {home_win_rate:.1%}")
    print(f"HOME_EDGE = {home_edge:.3f}   # goals/game")
    print(f"SCALE     = {scale:.3f}")
    print(f"HOME_B2B  = {home_b2b:+.3f}   # home team on the 2nd night of a back-to-back")
    print(f"AWAY_B2B  = {away_b2b:+.3f}   # away team on the 2nd night (helps the home team)")
    print(f"  equal teams -> home wins {1 / (1 + math.exp(-home_edge / scale)):.1%}")
    print(f"  +1.0 vs -1.0 GD/game at home -> {1 / (1 + math.exp(-(2 + home_edge) / scale)):.1%}")
    print(f"OT_PROBABILITY = {ot / total:.3f}")
    print(f"SHOOTOUT_SHARE_OF_OT = {shootouts / max(ot, 1):.3f}")


if __name__ == "__main__":
    main()
