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
import json
import os
import random
import time
from collections import defaultdict
from datetime import date

import psycopg2

import simulate_playoff_odds as sim

CHECKPOINTS = ["11-01", "12-01", "01-01", "02-01", "03-01"]


def checkpoint_dates(season_id):
    start = season_id // 10000
    return [date.fromisoformat(f"{start if md >= '07' else start + 1}-{md}") for md in CHECKPOINTS]


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


CARRYOVERS = (0.3, 0.5, 0.7)
GRID = [(c, k, sd) for c in CARRYOVERS for k in (20, 30, 45, 60) for sd in (0.25, 0.35, 0.5)]
PRODUCTION = (sim.PRIOR_CARRYOVER, sim.PRIOR_GAMES, sim.TALENT_SD)


def v2_name(c, k, sd):
    return f"v2 c={c} K={k} sd={sd}"


def load_season(cur, season_id, cache_dir):
    """Actual playoff teams, last season's GD/game, and each checkpoint's
    standings + remaining games. Cached as JSON so reruns skip the NHL API."""
    cache = os.path.join(cache_dir, f"season_{season_id}_v2.json") if cache_dir else None
    if cache and os.path.exists(cache):
        with open(cache) as f:
            return json.load(f)

    cur.execute("SELECT team_abbrev, made_playoffs FROM season_final_standings WHERE season_id = %s", (season_id,))
    actual = {t: 1.0 if made else 0.0 for t, made in cur.fetchall()}
    cur.execute(
        "SELECT team_abbrev, goal_differential, games_played FROM season_final_standings WHERE season_id = %s",
        (sim.previous_season_id(season_id),),
    )
    prior_gd = {t: gd / gp for t, gd, gp in cur.fetchall() if gp}
    games = sim.fetch_season_games(sorted(actual), season_id)  # includes final scores
    checkpoints = []
    for checkpoint in checkpoint_dates(season_id):
        checkpoints.append({"date": str(checkpoint), "standings": sim.fetch_standings_as_of(checkpoint)})
        time.sleep(0.25)
    data = {"actual": actual, "prior_gd": prior_gd, "games": games, "checkpoints": checkpoints}
    if cache:
        os.makedirs(cache_dir, exist_ok=True)
        with open(cache, "w") as f:
            json.dump(data, f)
    return data


def calibration_table(pairs, buckets=10):
    """pairs: [(predicted, actual)]. Rows: bucket, n, mean predicted, observed rate."""
    rows = []
    for b in range(buckets):
        lo, hi = b / buckets, (b + 1) / buckets
        inside = [(p, a) for p, a in pairs if lo <= p < hi or (b == buckets - 1 and p == 1.0)]
        if inside:
            rows.append((f"{lo:.0%}-{hi:.0%}", len(inside),
                         sum(p for p, _ in inside) / len(inside), sum(a for _, a in inside) / len(inside)))
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seasons", type=int, nargs="+", default=[20222023, 20232024, 20242025, 20252026])
    parser.add_argument("--trials", type=int, default=1000)
    parser.add_argument("--cache-dir", default=None, help="Cache NHL data here between runs")
    parser.add_argument("--sos", action="store_true", help="Also score strength-of-schedule ratings")
    args = parser.parse_args()

    brier_by = defaultdict(dict)    # model -> {(season, checkpoint date): brier}
    pairs_by = defaultdict(list)    # model -> [(predicted, actual)] for calibration

    with psycopg2.connect(sim.DATABASE_URL) as conn, conn.cursor() as cur:
        for season_id in args.seasons:
            data = load_season(cur, season_id, args.cache_dir)
            actual = data["actual"]
            print(f"{season_id}: {sum(actual.values()):.0f} playoff teams, {len(data['checkpoints'])} checkpoints", flush=True)
            for cp in data["checkpoints"]:
                standings = cp["standings"]
                completed, remaining = sim.split_games(data["games"], cp["date"])
                key = (season_id, cp["date"])
                runs = {"v1": v1_simulate(standings, remaining, args.trials, random.Random(1))}
                for c, k, sd in GRID:
                    priors = {t: c * gd for t, gd in data["prior_gd"].items()}
                    ratings = sim.team_ratings(standings, priors, prior_games=k, talent_sd=sd)
                    runs[v2_name(c, k, sd)] = sim.simulate(standings, remaining, args.trials, ratings, rng=random.Random(1))
                    if args.sos:
                        sos = sim.adjusted_ratings(list(standings), completed, priors, prior_games=k, talent_sd=sd)
                        runs["sos " + v2_name(c, k, sd)] = sim.simulate(standings, remaining, args.trials, sos, rng=random.Random(1))
                for name, odds in runs.items():
                    brier_by[name][key] = brier(odds, actual)
                    pairs_by[name].extend((odds[t], actual[t]) for t in odds if t in actual)

    def mean(model, seasons=None):
        vals = [b for (s, _), b in brier_by[model].items() if seasons is None or s in seasons]
        return sum(vals) / len(vals)

    v2_models = [v2_name(*g) for g in GRID]
    sos_models = ["sos " + m for m in v2_models] if args.sos else []
    prod = v2_name(*PRODUCTION)

    print("\nTop settings (mean Brier, all seasons x checkpoints; lower is better):")
    for name in sorted(v2_models, key=mean)[:8]:
        print(f"  {name:<26} {mean(name):.4f}")
    print(f"  {'production ' + prod:<26} {mean(prod):.4f}")
    print(f"  {'v1':<26} {mean('v1'):.4f}")
    if sos_models:
        print("\nWith strength of schedule (top settings):")
        for name in sorted(sos_models, key=mean)[:5]:
            print(f"  {name:<30} {mean(name):.4f}")

    print("\nLeave-one-season-out (tune on the other seasons, score the held-out one):")
    avg = lambda xs: sum(xs) / len(xs)
    families = [("v2", v2_models)] + ([("sos", sos_models)] if sos_models else [])
    for family, models in families:
        held_out_scores, prod_scores, v1_scores = [], [], []
        for held in args.seasons:
            others = [s for s in args.seasons if s != held]
            best = min(models, key=lambda m: mean(m, others))
            held_out_scores.append(mean(best, [held]))
            prod_scores.append(mean(prod, [held]))
            v1_scores.append(mean("v1", [held]))
            print(f"  [{family}] {held}: picked {best:<30} held-out {mean(best, [held]):.4f}   production {mean(prod, [held]):.4f}   v1 {mean('v1', [held]):.4f}")
        print(f"  [{family}] average:  tuned {avg(held_out_scores):.4f}   production {avg(prod_scores):.4f}   v1 {avg(v1_scores):.4f}")

    for name in ("v1", prod):
        print(f"\nCalibration, {name} (when the model says X%, how often did teams make it?):")
        print(f"  {'bucket':<9} {'teams':>5} {'predicted':>10} {'actual':>8}")
        for bucket, n, pred, obs in calibration_table(pairs_by[name]):
            flag = "  <- overconfident" if (pred > 0.5 and obs < pred - 0.1) or (pred < 0.5 and obs > pred + 0.1) else ""
            print(f"  {bucket:<9} {n:>5} {pred:>10.1%} {obs:>8.1%}{flag}")


if __name__ == "__main__":
    main()
