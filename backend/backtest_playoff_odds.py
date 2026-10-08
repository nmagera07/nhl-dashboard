"""
Backtest the playoff odds model against past seasons.

For each season and checkpoint date, it rebuilds what the model would have
said that day (standings as of the date, the games still left) and scores
it against who actually made the playoffs (season_final_standings) with
the Brier score: mean squared error between predicted probability and
outcome. 0 is perfect; always saying 50% scores 0.25.

Compares the original v1 model (raw point % as strength) with v2 at a
grid of PRIOR_GAMES / TALENT_SD settings; used to choose those constants.

Usage:
    python backtest_playoff_odds.py
    python backtest_playoff_odds.py --seasons 20242025 --trials 2000
"""

import argparse
import random
import time
from collections import defaultdict
from datetime import date

import psycopg2

import simulate_playoff_odds as sim

CHECKPOINTS = ["11-01", "12-01", "01-01", "02-01", "03-01"]
GRID = [(k, sd) for k in (10, 20, 30, 45, 60) for sd in (0.2, 0.35, 0.5)]


def checkpoint_dates(season_id):
    start = season_id // 10000
    return [date.fromisoformat(f"{start if md >= '07' else start + 1}-{md}") for md in CHECKPOINTS]


def season_schedule(teams, season_id):
    """All regular-season games as (date, home, away)."""
    games = {}
    for team in teams:
        for g in sim.nhl_get(sim.SCHEDULE_URL.format(team=team, season=season_id))["games"]:
            if g["gameType"] == 2:
                games[g["id"]] = (g["gameDate"], g["homeTeam"]["abbrev"], g["awayTeam"]["abbrev"])
        time.sleep(0.25)
    return list(games.values())


def v1_simulate(standings, schedule, trials, rng):
    """The original model: strength = point %, fixed for the whole season."""
    def p_home(h, a):
        diff = (h + 0.02) - a
        return 1 / (1 + 10 ** (-diff * 2.0))

    pct = {t: s["points"] / (max(s["games_played"], 1) * 2) for t, s in standings.items()}
    divisions, conferences = defaultdict(list), {}
    for t, s in standings.items():
        divisions[s["division"]].append(t)
        conferences[t] = s["conference"]
    made = defaultdict(int)
    for _ in range(trials):
        trial = {t: {"points": s["points"], "wins": s["wins"]} for t, s in standings.items()}
        for home, away in schedule:
            home_wins = rng.random() < p_home(pct[home], pct[away])
            winner, loser = (home, away) if home_wins else (away, home)
            trial[winner]["points"] += 2
            trial[winner]["wins"] += 1
            if rng.random() < 0.23:
                trial[loser]["points"] += 1
        for t in sim.determine_playoff_teams(trial, divisions, conferences):
            made[t] += 1
    return {t: made[t] / trials for t in standings}


def brier(odds, actual):
    teams = [t for t in odds if t in actual]
    return sum((odds[t] - actual[t]) ** 2 for t in teams) / len(teams)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seasons", type=int, nargs="+", default=[20232024, 20242025, 20252026])
    parser.add_argument("--trials", type=int, default=1000)
    args = parser.parse_args()

    scores = defaultdict(list)          # model -> [brier per checkpoint]
    by_checkpoint = defaultdict(list)   # (model, checkpoint) -> [brier per season]

    with psycopg2.connect(sim.DATABASE_URL) as conn, conn.cursor() as cur:
        for season_id in args.seasons:
            cur.execute("SELECT team_abbrev, made_playoffs FROM season_final_standings WHERE season_id = %s", (season_id,))
            actual = {t: 1.0 if made else 0.0 for t, made in cur.fetchall()}
            cur.execute(
                "SELECT team_abbrev, goal_differential, games_played FROM season_final_standings WHERE season_id = %s",
                (sim.previous_season_id(season_id),),
            )
            prior_gd = {t: gd / gp for t, gd, gp in cur.fetchall() if gp}

            all_games = season_schedule(sorted(actual), season_id)
            print(f"{season_id}: {len(all_games)} games, {sum(actual.values()):.0f} playoff teams")

            for checkpoint in checkpoint_dates(season_id):
                standings = sim.fetch_standings_as_of(checkpoint)
                remaining = [(h, a) for d, h, a in all_games if d > str(checkpoint)]
                label = checkpoint.strftime("%b %d")

                rng = random.Random(1)
                b = brier(v1_simulate(standings, remaining, args.trials, rng), actual)
                scores["v1"].append(b)
                by_checkpoint[("v1", label)].append(b)

                priors = {t: sim.PRIOR_CARRYOVER * gd for t, gd in prior_gd.items()}
                for k, sd in GRID:
                    ratings = sim.team_ratings(standings, priors, prior_games=k, talent_sd=sd)
                    odds = sim.simulate(standings, remaining, args.trials, ratings, rng=random.Random(1))
                    name = f"v2 K={k} sd={sd}"
                    b = brier(odds, actual)
                    scores[name].append(b)
                    by_checkpoint[(name, label)].append(b)
                print(f"  {checkpoint}: {len(remaining)} games left")
                time.sleep(0.25)

    print("\nMean Brier score (lower is better), all seasons and checkpoints:")
    ranked = sorted(scores.items(), key=lambda kv: sum(kv[1]) / len(kv[1]))
    for name, values in ranked:
        print(f"  {name:<20} {sum(values) / len(values):.4f}")

    best = ranked[0][0]
    print(f"\nBy checkpoint (v1 vs best, {best}):")
    for md in CHECKPOINTS:
        label = date.fromisoformat(f"2000-{md}").strftime("%b %d")
        v1 = by_checkpoint[("v1", label)]
        v2 = by_checkpoint[(best, label)]
        print(f"  {label}:  v1 {sum(v1) / len(v1):.4f}   v2 {sum(v2) / len(v2):.4f}")


if __name__ == "__main__":
    main()
