"""
Grade (and fit) the in-game win probability model (win_probability.py).

For every regular-season game of 2023-24 to 2025-26 in the play-by-play
cache: its pregame expected goals, walk-forward and held out like
backtest_goal_model.py (no game sees its own season's later results), then
the model's chance for the home team at checkpoints from puck drop to the
last 30 seconds, against who won.

The bar to clear: a lookup table of how often a team with a given lead at
a given time went on to win, built from the *other* seasons (no team
strength). The model should beat it once the pregame strength matters,
and match it late, when the lead is all that matters.

Usage:
    python backtest_win_probability.py           # grade the constants in win_probability.py
    python backtest_win_probability.py --fit     # grid-search the late-game constants
"""

import argparse
import gzip
import itertools
import json
import multiprocessing
import os
from collections import defaultdict

import backtest_goal_model as bgm
import goal_model as gm
import win_probability as wp

CHECKPOINTS = (0, 600, 1200, 1800, 2400, 3000, 3300, 3420, 3480, 3540, 3570)
TESTED = bgm.SEASONS[1:]


def pregame(data):
    """{game id: (home_mu, away_mu)} held out by season, like backtest_goal_model.py's production fit."""
    w, k, c = 0.5, 40, 0.7
    rows = {s: bgm.walk_forward(data[s], data[bgm.SEASONS[bgm.SEASONS.index(s) - 1]], w, k, c) for s in TESTED}
    out = {}
    for held in TESTED:
        train = [r for s in TESTED if s != held for r in rows[s]]
        beta = bgm.fit_poisson(*bgm.design(train))
        total_shrink, _ = bgm.shrink_fit(train, *bgm.expected_goals(train, beta))
        train_games = [g for s in TESTED if s != held for g in data[s]]
        league = sum(g["reg_h"] + g["reg_a"] for g in train_games) / len(train_games)
        home_mu, away_mu = bgm.adjust(*bgm.expected_goals(rows[held], beta), league, total_shrink, 1.0)
        for (g, *_), h, a in zip(rows[held], home_mu, away_mu):
            out[g["id"]] = (float(h), float(a))
    return out


def compact(pbp):
    """Just what the replay needs (goals, penalties, period ends), to keep ~3,900 games in memory."""
    plays = [p for p in pbp["plays"] if p.get("typeDescKey") in ("goal", "penalty", "period-end")]
    return {"gameType": pbp.get("gameType"), "gameState": pbp.get("gameState"), "plays": plays,
            "homeTeam": {k: pbp["homeTeam"][k] for k in ("id", "abbrev", "score")},
            "awayTeam": {k: pbp["awayTeam"][k] for k in ("id", "abbrev", "score")}}


def load(season_games):
    games = {}
    for season, rows in season_games.items():
        for g in rows:
            path = os.path.join(bgm.CACHE, "pbp", str(season), f"{g['id']}.json.gz")
            with gzip.open(path) as f:
                games[g["id"]] = (season, compact(json.load(f)))
    return games


def lead_at(pbp, second):
    """The home lead just before `second`."""
    lead = 0
    for p in pbp["plays"]:
        period = p.get("periodDescriptor") or {}
        if p.get("typeDescKey") != "goal" or period.get("periodType") == "SO":
            continue
        if wp._elapsed(period, False) + wp._clock(p["timeInPeriod"]) >= second:
            break
        lead += 1 if p["details"].get("eventOwnerTeamId") == pbp["homeTeam"]["id"] else -1
    return lead


def predictions(games, mus):
    """[(season, checkpoint, lead, p, home won)] with the constants as they are now."""
    out = []
    for game_id, (season, pbp) in games.items():
        if game_id not in mus:
            continue
        h, a = mus[game_id]
        pre = gm.home_win(gm.final_scores(h, a))
        h, a = wp.anchor(h, a, pre)
        won = pbp["homeTeam"]["score"] > pbp["awayTeam"]["score"]
        probs = dict(wp.series(pbp, h, a, playoff=False, at=CHECKPOINTS)["points"])
        for cp in CHECKPOINTS:
            if cp in probs:
                out.append((season, cp, lead_at(pbp, cp), probs[cp], won))
    return out


def brier(pairs):
    return sum((p - y) ** 2 for p, y in pairs) / len(pairs)


def lookup_baseline(rows):
    """Each held-out season's P(home wins | checkpoint, lead) from the other seasons' games."""
    out = []
    for held in TESTED:
        counts = defaultdict(lambda: [0, 0])
        for season, cp, lead, _, won in rows:
            if season != held:
                c = counts[(cp, max(-3, min(3, lead)))]
                c[0] += won
                c[1] += 1
        for season, cp, lead, _, won in rows:
            if season == held:
                c = counts[(cp, max(-3, min(3, lead)))]
                out.append((cp, (c[0] + 0.5) / (c[1] + 1), won))
    return out


def report(rows):
    base = defaultdict(list)
    for cp, p, won in lookup_baseline(rows):
        base[cp].append((p, won))
    print(f"{'minute':>7} {'games':>6} {'model':>7} {'lead table':>10}   (Brier, lower is better)")
    for cp in CHECKPOINTS:
        ours = [(p, w) for _, c, _, p, w in rows if c == cp]
        print(f"{cp / 60:>7.1f} {len(ours):>6} {brier(ours):>7.4f} {brier(base[cp]):>10.4f}")
    print(f"{'all':>7} {len(rows):>6} {brier([(p, w) for *_, p, w in rows]):>7.4f} "
          f"{brier([pw for cp in CHECKPOINTS for pw in base[cp]]):>10.4f}")
    for name, chosen in (("all checkpoints", rows), ("last 5 minutes", [r for r in rows if r[1] >= 3300])):
        pairs = sorted((p, w) for *_, p, w in chosen)
        tenth = len(pairs) // 10
        cells = []
        for i in range(10):
            chunk = pairs[i * tenth:(i + 1) * tenth] if i < 9 else pairs[9 * tenth:]
            cells.append(f"{sum(p for p, _ in chunk) / len(chunk):.2f}>{sum(w for _, w in chunk) / len(chunk):.2f}")
        print(f"Calibration, {name} (predicted>actual by tenth): " + " ".join(cells))


GRID = {
    "SCORE_EFFECT": (0.0, 0.1, 0.2),
    "PULL_SECONDS": (90, 120, 150),
    "PULL_RATES": ((10.0, 20.0), (12.0, 24.0), (15.0, 30.0)),
}


_SHARED = {}  # games and pregame expectations, inherited by the fit's forked workers


def _score(combo):
    effect, pull, (trailer, leader) = combo
    wp.SCORE_EFFECT, wp.PULL_SECONDS = effect, pull
    wp.PULL_GOALS_PER_HOUR, wp.EMPTY_NET_GOALS_PER_HOUR = trailer, leader
    rows = predictions(_SHARED["games"], _SHARED["mus"])
    return brier([(p, w) for _, cp, _, p, w in rows if cp > 0]), effect, pull, trailer, leader


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fit", action="store_true")
    args = parser.parse_args()
    data = {s: bgm.build(s) for s in bgm.SEASONS}
    mus = pregame(data)
    games = load({s: data[s] for s in TESTED})
    print(f"{len(games)} games, {len(mus)} with held-out pregame expectations")
    if args.fit:
        _SHARED.update(games=games, mus=mus)
        with multiprocessing.get_context("fork").Pool(6) as pool:
            results = []
            for score, effect, pull, trailer, leader in pool.imap_unordered(_score, itertools.product(*GRID.values())):
                results.append((score, effect, pull, trailer, leader))
                print(f"  score effect {effect}, pull at {pull}s, 6v5 {trailer}/h, EN {leader}/h: {score:.5f}", flush=True)
        best = min(results)
        print(f"best: SCORE_EFFECT = {best[1]}, PULL_SECONDS = {best[2]}, PULL_GOALS_PER_HOUR = {best[3]}, "
              f"EMPTY_NET_GOALS_PER_HOUR = {best[4]}")
        _, wp.SCORE_EFFECT, wp.PULL_SECONDS, wp.PULL_GOALS_PER_HOUR, wp.EMPTY_NET_GOALS_PER_HOUR = best
    report(predictions(games, mus))


if __name__ == "__main__":
    main()
