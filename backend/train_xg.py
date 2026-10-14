"""
Train and grade PuckPulse xG (xg_model.py) from cached NHL play-by-play.

Fits a logistic regression on the training seasons (Newton's method with a
small L2 penalty; numpy, a dev-only dependency) and writes the coefficients
to xg_model.json. Then grades it on held-out seasons:
  - log loss (lower is better) and AUC (how well it ranks goals above
    non-goals; 0.5 = coin flip)
  - calibration: predicted vs. actual goal rate by bucket
  - --compare: the same metrics for MoneyPuck's xG on the same shots
    (matched by game, period, time and shooter), and how closely the two
    agree per team

Play-by-play is cached as {cache}/{season}/{game_id}.json.gz (one file per
game from api-web.nhle.com/v1/gamecenter/{id}/play-by-play). MoneyPuck's
shot files (moneypuck.com/data.htm, free for non-commercial use with
credit) are shots_{year}.zip.

Usage:
    python train_xg.py --train 20222023 20232024 20242025 --test 20252026 --compare
"""

import argparse
import csv
import glob
import gzip
import io
import json
import math
import os
import zipfile
from collections import defaultdict

import numpy as np

import xg_model as xm

DEFAULT_CACHE = os.path.expanduser("~/.cache/puckpulse/pbp")
DEFAULT_MP = os.path.expanduser("~/.cache/puckpulse/moneypuck_shots")
L2 = 1.0


def load_shots(cache, season):
    shots = []
    for path in sorted(glob.glob(os.path.join(cache, str(season), "*.json.gz"))):
        with gzip.open(path) as f:
            shots += xm.shots_from_game(json.load(f))
    return shots


def matrix(shots):
    return np.array([xm.feature_vector(s) for s in shots]), np.array([s["goal"] for s in shots], dtype=float)


def fit(x, y, l2=L2, iterations=30):
    """Logistic regression by Newton's method; the intercept isn't penalized."""
    w = np.zeros(x.shape[1])
    penalty = np.full(x.shape[1], l2)
    penalty[0] = 0.0
    for _ in range(iterations):
        p = 1 / (1 + np.exp(-(x @ w)))
        gradient = x.T @ (p - y) + penalty * w
        hessian = (x * (p * (1 - p))[:, None]).T @ x + np.diag(penalty)
        step = np.linalg.solve(hessian, gradient)
        w -= step
        if np.max(np.abs(step)) < 1e-8:
            break
    return w


def log_loss(p, y):
    p = np.clip(p, 1e-9, 1 - 1e-9)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def auc(p, y):
    """Probability a random goal gets a higher xG than a random non-goal."""
    order = np.argsort(p)
    ranks = np.empty(len(p))
    ranks[order] = np.arange(1, len(p) + 1)
    goals = y == 1
    n_goal, n_miss = goals.sum(), (~goals).sum()
    return float((ranks[goals].sum() - n_goal * (n_goal + 1) / 2) / (n_goal * n_miss))


def calibration(p, y, edges=(0, 0.02, 0.05, 0.1, 0.2, 0.4, 1.0)):
    rows = []
    for lo, hi in zip(edges, edges[1:]):
        inside = (p >= lo) & (p < hi) if hi < 1 else (p >= lo)
        if inside.any():
            rows.append((f"{lo:.0%}-{hi:.0%}", int(inside.sum()), float(p[inside].mean()), float(y[inside].mean())))
    return rows


def moneypuck_xg(mp_dir, season):
    """{(game number, period, seconds into period, shooter id): MoneyPuck xG} for unblocked shots."""
    path = os.path.join(mp_dir, f"shots_{str(season)[:4]}.zip")
    out = {}
    with zipfile.ZipFile(path) as z, z.open(z.namelist()[0]) as f:
        for r in csv.DictReader(io.TextIOWrapper(f)):
            if r["event"] not in ("SHOT", "MISS", "GOAL") or not r.get("shooterPlayerId"):
                continue
            period = int(float(r["period"]))
            in_period = int(float(r["time"])) - (period - 1) * 1200
            out[(int(r["game_id"]), period, in_period, int(float(r["shooterPlayerId"])))] = float(r["xGoal"])
    return out


def report(name, p, y):
    print(f"  {name:<22} log loss {log_loss(p, y):.4f}   AUC {auc(p, y):.4f}   total xG {p.sum():8.1f} vs goals {int(y.sum())}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--train", nargs="+", required=True)
    parser.add_argument("--test", nargs="+", required=True)
    parser.add_argument("--cache", default=DEFAULT_CACHE)
    parser.add_argument("--moneypuck-dir", default=DEFAULT_MP)
    parser.add_argument("--compare", action="store_true")
    parser.add_argument("--save", default=xm.MODEL_PATH)
    args = parser.parse_args()

    train = [s for season in args.train for s in load_shots(args.cache, season)]
    x, y = matrix(train)
    print(f"Training on {len(train):,} shots ({int(y.sum()):,} goals) from {', '.join(args.train)}")
    w = fit(x, y)
    for name, coef in zip(xm.FEATURE_NAMES, w):
        print(f"  {name:<28} {coef:+.4f}")
    model = {"version": 1, "features": xm.FEATURE_NAMES, "coefficients": [round(float(c), 6) for c in w],
             "trained_on": args.train, "shots": len(train), "goals": int(y.sum())}

    for season in args.test:
        shots = load_shots(args.cache, season)
        xt, yt = matrix(shots)
        p = 1 / (1 + np.exp(-(xt @ w)))
        print(f"\nHeld-out {season}: {len(shots):,} shots, {int(yt.sum()):,} goals")
        report("PuckPulse xG", p, yt)
        report("constant (goal rate)", np.full(len(yt), y.mean()), yt)
        print("  calibration (predicted vs. actual goal rate):")
        for bucket, n, pred, obs in calibration(p, yt):
            print(f"    {bucket:<9} {n:>7,} shots   {pred:.3f} predicted   {obs:.3f} actual")
        if args.compare:
            mp = moneypuck_xg(args.moneypuck_dir, season)
            keys = [(int(str(s["game_id"])[-5:]), s["period"], s["time"], s["shooter"]) for s in shots]
            matched = [i for i, k in enumerate(keys) if k in mp]
            print(f"  matched {len(matched):,} of {len(shots):,} shots to MoneyPuck")
            idx = np.array(matched)
            mp_p = np.array([mp[keys[i]] for i in matched])
            report("PuckPulse (matched)", p[idx], yt[idx])
            report("MoneyPuck (matched)", mp_p, yt[idx])
            per_team = defaultdict(lambda: [0.0, 0.0])
            for i in matched:
                s = shots[i]
                team = (s["game_id"], s["team_is_home"])
                per_team[team][0] += p[i]
                per_team[team][1] += mp[keys[i]]
            ours, theirs = np.array(list(per_team.values())).T
            print(f"  per team-game xG, ours vs MoneyPuck: r = {np.corrcoef(ours, theirs)[0, 1]:.3f}")

    with open(args.save, "w") as f:
        json.dump(model, f, indent=1)
    print(f"\nSaved {args.save}")


if __name__ == "__main__":
    main()
