"""
Calibrate projected starting goalies (goalie_starts.py) on past seasons.

The starter for each team-game comes from the cached play-by-play: the
goalie in net for the first shot the team faced. For every game, the
projection only sees that team's earlier starters this season (plus last
season's split), and whether it played the night before and who started
then. Graded by how often the top projected goalie started, log loss, and
calibration.

Usage:
    python backtest_goalie_starts.py
"""

import glob
import gzip
import json
import math
import os
from collections import defaultdict
from datetime import date

import goalie_starts as gs

CACHE = os.path.expanduser("~/.cache/puckpulse")
SEASONS = (20222023, 20232024, 20242025, 20252026)


def season_starts(season):
    """[(date, team, starter id)] for the season's regular-season games, oldest first (cached)."""
    path = os.path.join(CACHE, "backtest", f"goalie_starts_{season}.json")
    if os.path.exists(path):
        with open(path) as f:
            return [tuple(r) for r in json.load(f)]
    rows = []
    for file in sorted(glob.glob(os.path.join(CACHE, "pbp", str(season), "*.json.gz"))):
        with gzip.open(file) as f:
            pbp = json.load(f)
        if pbp.get("gameType") != 2:
            continue
        for team, goalie in gs.starters(pbp).items():
            rows.append((pbp["gameDate"], team, goalie))
    rows.sort()
    with open(path, "w") as f:
        json.dump(rows, f)
    return rows


def grade(seasons):
    """Walk each season forward, projecting each team-game before it happens."""
    hits = n = 0
    log_loss = 0.0
    buckets = defaultdict(lambda: [0, 0.0, 0])  # (b2b) -> games, predicted top prob, top started
    calibration = defaultdict(lambda: [0, 0])    # prob decile -> [count, started]
    prior_split = {}
    for season in seasons:
        rows = season_starts(season)
        history = defaultdict(list)  # team -> [(date, goalie)]
        for day, team, goalie in rows:
            past = history[team]
            yesterday = past[-1] if past and (date.fromisoformat(day) - date.fromisoformat(past[-1][0])).days == 1 else None
            candidates = {g for _, g in past[-gs.RECENT_GAMES:]} | set(prior_split.get(team, {})) | {goalie}
            probs = gs.start_probabilities(candidates, [g for _, g in past], prior_split.get(team, {}),
                                           started_last_night=yesterday[1] if yesterday else None)
            if len(past) >= 3:  # skip each team's first few games: no history either way
                top = max(probs, key=probs.get)
                n += 1
                hits += top == goalie
                log_loss -= math.log(max(probs.get(goalie, 0), 1e-4))
                b = buckets[bool(yesterday)]
                b[0] += 1
                b[1] += probs[top]
                b[2] += top == goalie
                for g, p in probs.items():
                    cell = calibration[min(int(p * 10), 9)]
                    cell[0] += 1
                    cell[1] += g == goalie
            past.append((day, goalie))
        # Next season's prior: this season's share of starts by goalie, per team.
        prior_split = {}
        for team, past in history.items():
            counts = defaultdict(int)
            for _, g in past:
                counts[g] += 1
            prior_split[team] = {g: c / len(past) for g, c in counts.items()}
    return n, hits, log_loss, buckets, calibration


def main():
    n, hits, log_loss, buckets, calibration = grade(SEASONS)
    print(f"{n} team-games: top pick started {hits / n:.1%}, log loss {log_loss / n:.3f}")
    for b2b, (count, predicted, right) in sorted(buckets.items()):
        print(f"  {'2nd night of back-to-back' if b2b else 'normal night':26} {count:5} games: "
              f"top pick predicted {predicted / count:.1%}, started {right / count:.1%}")
    print("Calibration (predicted -> actual):")
    for decile in sorted(calibration):
        count, started = calibration[decile]
        print(f"  {decile * 10:3}-{decile * 10 + 10}%: {count:5} goalie-games, started {started / count:.1%}")


if __name__ == "__main__":
    main()
