"""
Build and grade the goal model (goal_model.py) on past seasons.

Data: every regular-season game from the cached play-by-play
(~/.cache/puckpulse/pbp/{season}/{game_id}.json.gz, the same cache the xG
model was trained on) and the playoff backtest's per-season game lists
(back-to-back flags). For each game: the final score as the NHL reports it
(a shootout counts as one goal for the winner, which is also how
sportsbooks settle puck lines and totals), how it ended, regulation goals
with empty-netters split out, and both teams' xG.

Grading is walk-forward: each game is predicted only from games before it
that season, plus a prior from the season before. The model's few
constants (how much xG vs. goals, how fast to trust this season, home ice,
back-to-backs) are fit on the other seasons and tested on the held-out one.

Usage:
    python backtest_goal_model.py               # build (cached) and grade
    python backtest_goal_model.py --rebuild     # re-read the play-by-play
"""

import argparse
import glob
import gzip
import json
import math
import os
from collections import defaultdict

import numpy as np

import goal_model as gm
import ingest_xg
import xg_model

CACHE = os.path.expanduser("~/.cache/puckpulse")
SEASONS = (20222023, 20232024, 20242025, 20252026)


def is_empty_net(situation_code, scored_by_home):
    """situationCode digits: away goalie, away skaters, home skaters, home goalie (1 in net, 0 pulled)."""
    code = str(situation_code or "").zfill(4)
    return code[0] == "0" if scored_by_home else code[3] == "0"


def game_row(pbp, model):
    home_id = pbp["homeTeam"]["id"]
    row = {"id": pbp["id"], "date": pbp["gameDate"], "home": pbp["homeTeam"]["abbrev"], "away": pbp["awayTeam"]["abbrev"],
           "hs": pbp["homeTeam"]["score"], "as": pbp["awayTeam"]["score"],
           "last": (pbp.get("gameOutcome") or {}).get("lastPeriodType", "REG"),
           "reg_h": 0, "reg_a": 0, "en_h": 0, "en_a": 0}
    for play in pbp["plays"]:
        if play["typeDescKey"] != "goal" or play["periodDescriptor"].get("periodType") != "REG":
            continue
        home = play["details"].get("eventOwnerTeamId") == home_id
        side = "h" if home else "a"
        if is_empty_net(play.get("situationCode"), home):
            row[f"en_{side}"] += 1
        else:
            row[f"reg_{side}"] += 1
    totals = {t["is_home"]: t for t in ingest_xg.game_totals(pbp, model)}
    row["xg_h"], row["xg_a"] = totals[True]["xg_for"], totals[False]["xg_for"]
    return row


def build(season, rebuild=False):
    """The season's games, oldest first (cached as JSON)."""
    path = os.path.join(CACHE, "backtest", f"goal_games_{season}.json")
    if os.path.exists(path) and not rebuild:
        with open(path) as f:
            return json.load(f)
    model = xg_model.load_model()
    rows = []
    for file in sorted(glob.glob(os.path.join(CACHE, "pbp", str(season), "*.json.gz"))):
        with gzip.open(file) as f:
            pbp = json.load(f)
        if pbp.get("gameType") == 2 and pbp.get("gameState") in ("OFF", "FINAL"):
            rows.append(game_row(pbp, model))
    with open(os.path.join(CACHE, "backtest", f"season_{season}_v2.json")) as f:
        b2b = {(g["date"], g["home"], g["away"]): (g["home_b2b"], g["away_b2b"]) for g in json.load(f)["games"]}
    for row in rows:
        row["home_b2b"], row["away_b2b"] = b2b.get((row["date"], row["home"], row["away"]), (False, False))
    rows.sort(key=lambda r: (r["date"], r["id"]))
    with open(path, "w") as f:
        json.dump(rows, f)
    return rows


def describe(games):
    """What the data says before any model: averages, overtime, empty-netters by late margin."""
    n = len(games)
    reg = [g["reg_h"] + g["reg_a"] for g in games]
    print(f"  {n} games: final total {sum(g['hs'] + g['as'] for g in games) / n:.2f}, "
          f"regulation non-EN goals {sum(reg) / n:.2f} (home {sum(g['reg_h'] for g in games) / n:.2f}, "
          f"away {sum(g['reg_a'] for g in games) / n:.2f}), variance {np.var(reg):.2f}")
    ties = [g for g in games if g["reg_h"] + g["en_h"] == g["reg_a"] + g["en_a"]]
    print(f"  overtime {len(ties) / n:.1%}, shootout share of OT {sum(g['last'] == 'SO' for g in ties) / max(len(ties), 1):.1%}, "
          f"home wins OT/SO {sum(g['hs'] > g['as'] for g in ties) / max(len(ties), 1):.1%}")
    by_margin = defaultdict(lambda: [0, 0, 0])
    for g in games:
        margin = abs(g["reg_h"] - g["reg_a"])
        leader_en = g["en_h"] if g["reg_h"] > g["reg_a"] else g["en_a"] if g["reg_a"] > g["reg_h"] else 0
        by_margin[min(margin, 3)][0] += 1
        by_margin[min(margin, 3)][1] += leader_en > 0
        by_margin[min(margin, 3)][2] += leader_en
    for margin, (count, any_en, en) in sorted(by_margin.items()):
        print(f"  non-EN margin {margin}{'+' if margin == 3 else ''}: {count} games, leader scored an EN goal in "
              f"{any_en / count:.1%} ({en / count:.2f} per game)")


def league_rates(games):
    """Per team-game: non-EN regulation goals and xG (home and away together)."""
    n = 2 * len(games)
    return (sum(g["reg_h"] + g["reg_a"] for g in games) / n, sum(g["xg_h"] + g["xg_a"] for g in games) / n)


def season_priors(prev_games, carryover):
    """Each team's starting offense/defense: last season's rates (goals and xG
    per game), pulled toward the league average by 1 - carryover."""
    if not prev_games:
        return {}, None
    league_goals, league_xg = league_rates(prev_games)
    sums = defaultdict(lambda: [0, 0.0, 0.0, 0.0, 0.0])  # games, GF, GA, xGF, xGA
    for g in prev_games:
        for team, gf, ga, xf, xa in ((g["home"], g["reg_h"], g["reg_a"], g["xg_h"], g["xg_a"]),
                                     (g["away"], g["reg_a"], g["reg_h"], g["xg_a"], g["xg_h"])):
            s = sums[team]
            s[0] += 1
            s[1] += gf
            s[2] += ga
            s[3] += xf
            s[4] += xa
    priors = {}
    for team, (n, gf, ga, xf, xa) in sums.items():
        priors[team] = {
            "for": league_goals + carryover * (gf / n - league_goals),
            "against": league_goals + carryover * (ga / n - league_goals),
            "xfor": league_xg + carryover * (xf / n - league_xg),
            "xagainst": league_xg + carryover * (xa / n - league_xg),
        }
    return priors, (league_goals, league_xg)


def walk_forward(games, prev_games, xg_weight, prior_games, carryover):
    """
    For each game, from games before it this season: both teams' offense
    and defense (non-EN goals per game expected), each a blend of goals and
    xG shrunk toward the prior with prior_games pseudo-games. Rows of
    (game, home offense, home defense, away offense, away defense, league).
    """
    priors, league = season_priors(prev_games, carryover)
    league_goals, league_xg = league or league_rates(games)
    xg_scale = league_goals / league_xg  # xG per game is on its own scale; put it in goals
    blank = {"for": league_goals, "against": league_goals, "xfor": league_xg, "xagainst": league_xg}
    totals = defaultdict(lambda: [0, 0.0, 0.0, 0.0, 0.0])

    def rating(team):
        n, gf, ga, xf, xa = totals[team]
        p = priors.get(team, blank)
        prior_for = (1 - xg_weight) * p["for"] + xg_weight * p["xfor"] * xg_scale
        prior_against = (1 - xg_weight) * p["against"] + xg_weight * p["xagainst"] * xg_scale
        seen_for = (1 - xg_weight) * gf + xg_weight * xf * xg_scale
        seen_against = (1 - xg_weight) * ga + xg_weight * xa * xg_scale
        return ((seen_for + prior_games * prior_for) / (n + prior_games),
                (seen_against + prior_games * prior_against) / (n + prior_games))

    rows, day, pending = [], None, []
    for g in games:
        if g["date"] != day:  # same-day games don't see each other
            for done in pending:
                for team, gf, ga, xf, xa in ((done["home"], done["reg_h"], done["reg_a"], done["xg_h"], done["xg_a"]),
                                             (done["away"], done["reg_a"], done["reg_h"], done["xg_a"], done["xg_h"])):
                    t = totals[team]
                    t[0] += 1
                    t[1] += gf
                    t[2] += ga
                    t[3] += xf
                    t[4] += xa
            day, pending = g["date"], []
        (ho, hd), (ao, ad) = rating(g["home"]), rating(g["away"])
        rows.append((g, ho, hd, ao, ad, league_goals))
        pending.append(g)
    return rows


def design(rows):
    """Stacked Poisson rows, one per team-game: [home, away, log off, log def of opponent, own b2b, opp b2b] -> goals."""
    x, y = [], []
    for g, ho, hd, ao, ad, league in rows:
        x.append([1, 0, math.log(ho / league), math.log(ad / league), g["home_b2b"], g["away_b2b"]])
        y.append(g["reg_h"])
        x.append([0, 1, math.log(ao / league), math.log(hd / league), g["away_b2b"], g["home_b2b"]])
        y.append(g["reg_a"])
    return np.array(x, dtype=float), np.array(y, dtype=float)


def fit_poisson(x, y, iterations=25):
    """Poisson regression (log link) by Newton's method."""
    beta = np.zeros(x.shape[1])
    beta[:2] = math.log(y.mean())
    for _ in range(iterations):
        mu = np.exp(x @ beta)
        step = np.linalg.solve(x.T @ (x * mu[:, None]), x.T @ (y - mu))
        beta += step
        if np.abs(step).max() < 1e-9:
            break
    return beta


def expected_goals(rows, beta):
    x, _ = design(rows)
    mu = np.exp(x @ beta)
    return mu[0::2], mu[1::2]


def brier(pairs):
    return sum((p - y) ** 2 for p, y in pairs) / len(pairs)


def grade(rows, home_mu, away_mu, en_goals, ot_home, nu=1.0, shared=0.0, weights=(1.0, 1.0)):
    """Brier on the bets that matter, plus each one's base rate (always guessing the average)."""
    out = defaultdict(list)
    for (g, *_), lh, la in zip(rows, home_mu, away_mu):
        scores = gm.final_scores(lh, la, en_goals, ot_home, nu, shared, weights)
        fav_home = gm.home_win(scores) >= 0.5
        cover = gm.home_covers(scores, -1.5) if fav_home else 1 - gm.home_covers(scores, 1.5)
        out["home win"].append((gm.home_win(scores), g["hs"] > g["as"]))
        out["favorite -1.5"].append((cover, (g["hs"] - g["as"] >= 2) if fav_home else (g["as"] - g["hs"] >= 2)))
        for line in (5.5, 6.5):
            out[f"over {line}"].append((gm.over(scores, line), g["hs"] + g["as"] > line))
    return {k: (brier(v), brier([(sum(y for _, y in v) / len(v), y) for _, y in v]), v) for k, v in out.items()}


def empty_net_rates(games):
    """Empty-net goals per game by the leader's non-EN lead (0, 1, 2, 3+), and the OT home share."""
    counts, goals = [0] * 4, [0] * 4
    ot = [0, 0]
    for g in games:
        margin = g["reg_h"] - g["reg_a"]
        lead = min(abs(margin), 3)
        counts[lead] += 1
        goals[lead] += g["en_h"] + g["en_a"] if margin == 0 else g["en_h"] if margin > 0 else g["en_a"]
        if margin == 0 and g["en_h"] + g["en_a"] == 0:
            ot[0] += 1
            ot[1] += g["hs"] > g["as"]
    return tuple(round(e / n, 3) for e, n in zip(goals, counts)), ot[1] / ot[0]


def shrink_fit(rows, home_mu, away_mu):
    """Slopes of actual on predicted for the total and the margin (non-EN regulation goals)."""
    pred_total = home_mu + away_mu
    pred_margin = home_mu - away_mu
    actual_total = np.array([g["reg_h"] + g["reg_a"] for g, *_ in rows])
    actual_margin = np.array([g["reg_h"] - g["reg_a"] for g, *_ in rows])
    return float(np.polyfit(pred_total, actual_total, 1)[0]), float(np.polyfit(pred_margin, actual_margin, 1)[0])


def residual_shape(rows, home_mu, away_mu):
    """Residual variance / mean (per team) and covariance between the two teams' goals."""
    sq = cov = mean = 0.0
    for (g, *_), lh, la in zip(rows, home_mu, away_mu):
        sq += (g["reg_h"] - lh) ** 2 + (g["reg_a"] - la) ** 2
        mean += lh + la
        cov += (g["reg_h"] - lh) * (g["reg_a"] - la)
    return sq / mean, cov / len(rows)


def nu_for(dispersion, shared, typical=2.8):
    """The COM-Poisson nu whose own part makes a team's total variance/mean match the data."""
    target = (dispersion * typical - shared) / (typical - shared)  # variance/mean of the non-shared part
    low, high = 0.5, 2.0
    for _ in range(40):
        nu = (low + high) / 2
        p = gm.com_poisson(typical - shared, nu)
        m = sum(k * q for k, q in enumerate(p))
        var = sum((k - m) ** 2 * q for k, q in enumerate(p))
        low, high = (nu, high) if var / m > target else (low, nu)
    return round((low + high) / 2, 3)


def margin_weights(rows, home_mu, away_mu, nu, shared, rounds=4):
    """Weights for tied and one-goal regulation scores (non-EN) so their frequency matches the data."""
    actual = [sum(abs(g["reg_h"] - g["reg_a"]) == m for g, *_ in rows) / len(rows) for m in (0, 1)]
    weights = [1.0, 1.0]
    for _ in range(rounds):
        predicted = [0.0, 0.0]
        for lh, la in zip(home_mu, away_mu):
            for (h, a), p in gm.regulation_scores(lh, la, nu, shared, tuple(weights)).items():
                if abs(h - a) < 2:
                    predicted[abs(h - a)] += p
        weights = [w * act / (pred / len(rows)) for w, act, pred in zip(weights, actual, predicted)]
    return tuple(round(w, 3) for w in weights)


def adjust(home_mu, away_mu, league_total, total_shrink, margin_scale):
    pairs = [gm.adjusted_goals(h, a, league_total, total_shrink, margin_scale) for h, a in zip(home_mu, away_mu)]
    return np.array([p[0] for p in pairs]), np.array([p[1] for p in pairs])


def fit_production(data, tested, w=0.5, k=40, c=0.7):
    """goal_model.py's constants, fit on every tested season (the total shrink out of sample)."""
    rows = {s: walk_forward(data[s], data[SEASONS[SEASONS.index(s) - 1]], w, k, c) for s in tested}
    held_out = [[], []]
    for held in tested:
        beta = fit_poisson(*design([r for s in tested if s != held for r in rows[s]]))
        mu = expected_goals(rows[held], beta)
        held_out[0].extend(mu[0] + mu[1])
        held_out[1].extend(g["reg_h"] + g["reg_a"] for g, *_ in rows[held])
    total_shrink = float(np.polyfit(held_out[0], held_out[1], 1)[0])
    all_rows = [r for s in tested for r in rows[s]]
    all_games = [g for s in tested for g in data[s]]
    beta = fit_poisson(*design(all_rows))
    mu = expected_goals(all_rows, beta)
    dispersion, shared = residual_shape(all_rows, *mu)
    nu = nu_for(dispersion, shared)
    en_goals, ot_home = empty_net_rates(all_games)
    league_total = sum(g["reg_h"] + g["reg_a"] for g in all_games) / len(all_games)
    weights = margin_weights(all_rows, *adjust(*mu, league_total, total_shrink, 1.0), nu, shared)
    print(f"EN_GOALS = {en_goals}\nOT_HOME = {ot_home:.3f}\nTOTAL_SHRINK = {total_shrink:.3f}  # out of sample")
    print(f"DISPERSION = {nu}\nSHARED_GOALS = {shared:.3f}\nMARGIN_WEIGHTS = {tuple(float(x) for x in weights)}")
    print(f"TEAM_COEFFICIENTS = {tuple(round(float(b), 4) for b in beta)}  # home, away, log offense, log defense, own b2b, opp b2b")
    print(f"LEAGUE_TOTAL = {league_total:.3f}  # non-EN regulation goals per game, 2023-26")


GRID = [(w, k, c) for w in (0.0, 0.5, 0.75) for k in (10, 20, 40) for c in (0.5, 0.7)]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rebuild", action="store_true")
    parser.add_argument("--describe", action="store_true")
    parser.add_argument("--raw", action="store_true", help="skip the total/margin adjustment")
    parser.add_argument("--poisson", action="store_true", help="plain independent Poisson goals")
    parser.add_argument("--fit", action="store_true", help="print production constants from every season")
    args = parser.parse_args()
    data = {season: build(season, args.rebuild) for season in SEASONS}
    if args.describe:
        for season, games in data.items():
            print(season)
            describe(games)
        return

    tested = SEASONS[1:]  # the first season is only a prior
    if args.fit:
        return fit_production(data, tested)
    results = {}
    for w, k, c in GRID:
        rows = {s: walk_forward(data[s], data[SEASONS[SEASONS.index(s) - 1]], w, k, c) for s in tested}
        loglik = 0.0
        for held in tested:
            train = [r for s in tested if s != held for r in rows[s]]
            beta = fit_poisson(*design(train))
            x, y = design(rows[held])
            mu = np.exp(x @ beta)
            loglik += float(np.sum(y * np.log(mu) - mu - np.array([math.lgamma(v + 1) for v in y])))
        results[(w, k, c)] = loglik
    best = max(results, key=results.get)
    print("Leave-one-season-out Poisson log-likelihood (higher is better), top 5:")
    for key in sorted(results, key=results.get, reverse=True)[:5]:
        print(f"  xG weight {key[0]}, prior games {key[1]}, carryover {key[2]}: {results[key]:.1f}")

    w, k, c = best
    rows = {s: walk_forward(data[s], data[SEASONS[SEASONS.index(s) - 1]], w, k, c) for s in tested}
    print(f"\nHeld-out grades with {best} (Brier; base rate = always guessing the average):")
    pooled = defaultdict(list)
    for held in tested:
        train_seasons = [s for s in tested if s != held]
        train_games = [g for s in train_seasons for g in data[s]]
        en_goals, ot_home = empty_net_rates(train_games)
        train_rows = [r for s in train_seasons for r in rows[s]]
        beta = fit_poisson(*design(train_rows))
        total_shrink, margin_scale = shrink_fit(train_rows, *expected_goals(train_rows, beta))
        league_total = sum(g["reg_h"] + g["reg_a"] for g in train_games) / len(train_games)
        dispersion, shared = residual_shape(train_rows, *expected_goals(train_rows, beta))
        nu = 1.0 if args.poisson else nu_for(dispersion, shared)
        shared = 0.0 if args.poisson else round(shared, 3)
        train_mu = expected_goals(train_rows, beta)
        if not args.raw:
            train_mu = adjust(*train_mu, league_total, total_shrink, margin_scale)
        weights = (1.0, 1.0) if args.poisson else margin_weights(train_rows, *train_mu, nu, shared)
        home_mu, away_mu = expected_goals(rows[held], beta)
        if not args.raw:
            home_mu, away_mu = adjust(home_mu, away_mu, league_total, total_shrink, margin_scale)
        graded = grade(rows[held], home_mu, away_mu, en_goals, ot_home, nu, shared, weights)
        print(f"  {held}: EN goals by lead {en_goals}, OT home {ot_home:.2f}, total shrink {total_shrink:.2f}, "
              f"margin scale {margin_scale:.2f}, nu {nu}, shared {shared}, margin weights {weights}, "
              f"beta {np.round(beta, 3).tolist()}")
        for name, (ours, base, pairs) in graded.items():
            print(f"    {name:14} {ours:.4f} vs {base:.4f}")
            pooled[name].extend(pairs)
    print("\nCalibration, all held-out games (predicted vs actual):")
    for name, pairs in pooled.items():
        pairs.sort()
        tenth = len(pairs) // 5
        cells = []
        for i in range(5):
            chunk = pairs[i * tenth:(i + 1) * tenth] if i < 4 else pairs[4 * tenth:]
            cells.append(f"{sum(p for p, _ in chunk) / len(chunk):.2f}->{sum(y for _, y in chunk) / len(chunk):.2f}")
        print(f"  {name:14} " + "  ".join(cells))


if __name__ == "__main__":
    main()
