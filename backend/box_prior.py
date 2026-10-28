"""
A box-score prior for RAPM (WAR v2): where each player's ratings start
before his on-ice results move them.

rapm.chain starts each season from the player's ratings the season before
(a new player starts at league average, 0). That ignores what his own
numbers say: a rookie who shoots and sets up a lot is probably above
average. Box-score stats also carry over from one season to the next better
than on-ice results, which is why WAR v1 (Game Score) predicts next season
better than RAPM alone.

So, the way public models (Evolving-Hockey, TopDownHockey) do it:
  1. box stats per 60 at 5v5 for each player-season: individual xG, shot
     attempts, primary and secondary assists, blocks, takeaways,
     giveaways, hits (from cached play-by-play; ice time from the stints)
  2. an SPM ("statistical plus-minus"): a weighted least-squares fit from
     those stats to RAPM offense and defense, separately for forwards and
     defensemen, fit on other seasons than the one it's used for
  3. the prior for a season: ALPHA x last season's rating + (1 - ALPHA) x
     this season's box estimate (the box estimate alone for a new player),
     with the box estimate pulled toward 0 for players with little ice time

Usage:
    python box_prior.py --spm 20232024 20242025 20252026        # the fit and how well box stats explain RAPM
    python box_prior.py --compare 20262027                       # chain vs. chain + box prior, on unseen stints
"""

import argparse
import json
import os
from collections import defaultdict

import numpy as np

import rapm
import rapm_stints as rs
import xg_model as xm

FEATURES = ["ixg", "attempts", "a1", "a2", "blocks", "takeaways", "giveaways", "hits"]
SEASONS = [20212022, 20222023, 20232024, 20242025, 20252026, 20262027]
ALPHA = 0.5          # weight on last season's rating in the prior
BOX_HOURS = 5.0      # a box estimate counts h / (h + BOX_HOURS): little ice time, little trust
MIN_SPM_HOURS = 5.0  # players in the SPM fit


def box_stats(season, model=None):
    """{pid: {pos, hours, <FEATURES> per 60}} at 5v5, cached in {CACHE}/war_v2/box_{season}.json."""
    path = os.path.join(rs.CACHE, "war_v2", f"box_{season}.json")
    if os.path.exists(path):
        with open(path) as f:
            return {int(k): v for k, v in json.load(f).items()}
    model = model or xm.load_model()
    counts = defaultdict(lambda: dict.fromkeys(FEATURES, 0.0))
    pos = {}
    for game_id in rs._game_ids(season):
        pbp = rs.load("pbp", season, game_id)
        for r in pbp.get("rosterSpots", []):
            pos[r["playerId"]] = "D" if r.get("positionCode") == "D" else ("G" if r.get("positionCode") == "G" else "F")
        for shot in xm.shots_from_game(pbp):
            if shot["situation"] == rs.FIVE_ON_FIVE and shot["shooter"]:
                counts[shot["shooter"]]["ixg"] += xm.predict(shot, model)
                counts[shot["shooter"]]["attempts"] += 1
        for play in pbp.get("plays", []):
            if str(play.get("situationCode") or "").zfill(4) != rs.FIVE_ON_FIVE:
                continue
            d, kind = play.get("details") or {}, play.get("typeDescKey")
            if kind == "goal":
                for key, field in (("a1", "assist1PlayerId"), ("a2", "assist2PlayerId")):
                    if d.get(field):
                        counts[d[field]][key] += 1
            elif kind == "blocked-shot":
                if d.get("shootingPlayerId"):
                    counts[d["shootingPlayerId"]]["attempts"] += 1  # a blocked attempt is still his attempt
                if d.get("blockingPlayerId"):
                    counts[d["blockingPlayerId"]]["blocks"] += 1
            elif kind in ("takeaway", "giveaway") and d.get("playerId"):
                counts[d["playerId"]][kind + "s"] += 1
            elif kind == "hit" and d.get("hittingPlayerId"):
                counts[d["hittingPlayerId"]]["hits"] += 1
    hours = defaultdict(float)
    for stints in rs.load_stints(season).values():
        for s in stints:
            for p in s["home"] + s["away"]:
                hours[p] += s["seconds"] / 3600
    out = {}
    for p, h in hours.items():
        if pos.get(p) in ("F", "D"):
            out[p] = {"pos": pos[p], "hours": h, **{k: counts[p][k] / h for k in FEATURES}}
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(out, f)
    return out


def chain_ratings(seasons, lam=rapm.CHAIN_LAMBDA, prior_fn=None):
    """
    {season: ratings} with each season's ratings as of the end of that
    season, from one chain over all of them (one design). prior_fn(season,
    previous beta, design) gives the prior; default: last season's beta.
    """
    seasons = sorted(seasons)
    _, design = rapm.build(seasons)
    beta, out, betas = None, {}, {}
    for season in seasons:
        sums = rapm.build([season], design=design)[0][0]
        prior = prior_fn(season, beta, design) if prior_fn else beta
        beta = rapm.solve(sums, design, lam, prior)
        betas[season] = beta
        out[season] = rapm.ratings(beta, design, sums)
    return out, betas, design


def fit_spm(ratings_by_season, box_by_season):
    """{(group, "offense"|"defense"): coefficients (intercept first)}, weighted by hours."""
    coefs = {}
    for group in ("F", "D"):
        for target in ("offense", "defense"):
            x, y, w = [], [], []
            for season, rated in ratings_by_season.items():
                box = box_by_season[season]
                for p, b in box.items():
                    if b["pos"] == group and b["hours"] >= MIN_SPM_HOURS and p in rated:
                        x.append([1.0] + [b[k] for k in FEATURES])
                        y.append(rated[p][target])
                        w.append(b["hours"])
            x, y, w = np.array(x), np.array(y), np.array(w)
            xtw = x.T * w
            coefs[(group, target)] = np.linalg.solve(xtw @ x + np.eye(len(FEATURES) + 1) * 1e-3, xtw @ y)
    return coefs


def box_estimate(b, coefs):
    """(offense, defense) a player's box stats point to, pulled toward 0 by his ice time."""
    trust = b["hours"] / (b["hours"] + BOX_HOURS)
    features = np.array([1.0] + [b[k] for k in FEATURES])
    return (float(features @ coefs[(b["pos"], "offense")]) * trust,
            float(features @ coefs[(b["pos"], "defense")]) * trust)


def prior_vector(design, box, coefs, previous=None, previous_hours=None, alpha=ALPHA, defense=True):
    """
    The prior beta for one season: alpha x last season's ratings + (1 -
    alpha) x the box estimate; the box estimate alone for a player with no
    ice time last season. defense=False leaves defense on last season's
    rating (box stats explain little of it). Controls get no prior (they
    aren't penalized).
    """
    use_defense = defense
    prior = np.zeros(design.n) if previous is None else previous.copy()
    for p, i in design.index.items():
        if p not in box:
            continue
        offense, box_defense = box_estimate(box[p], coefs)
        j = design.n_players + i  # defense column; its sign is flipped (positive beta = allows more)
        new = previous is None or not (previous_hours or {}).get(p)
        prior[i] = offense if new else alpha * previous[i] + (1 - alpha) * offense
        if use_defense:
            prior[j] = -box_defense if new else alpha * previous[j] + (1 - alpha) * -box_defense
    return prior


def chain_with_box(seasons, lam=rapm.CHAIN_LAMBDA, alpha=ALPHA, spm_seasons=None, defense=True):
    """
    chain_ratings with the box prior. The SPM for each season is fit on the
    plain chain's ratings of the *other* seasons in `spm_seasons` (default:
    all of `seasons`), so no season's prior is built from its own fit.
    """
    seasons = sorted(seasons)
    plain, _, _ = chain_ratings(seasons, lam)
    boxes = {s: box_stats(s) for s in seasons}
    pool = [s for s in (spm_seasons or seasons) if s in plain]
    hours = {}

    def prior_fn(season, previous, design):
        coefs = fit_spm({s: plain[s] for s in pool if s != season}, boxes)
        prior = prior_vector(design, boxes[season], coefs, previous, hours, alpha, defense)
        hours.clear()
        hours.update({p: b["hours"] for p, b in boxes[season].items()})
        return prior

    return chain_ratings(seasons, lam, prior_fn)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--spm", nargs="+", type=int, metavar="SEASON")
    parser.add_argument("--compare", type=int, metavar="TARGET")
    args = parser.parse_args()

    if args.spm:
        plain, _, _ = chain_ratings(args.spm)
        boxes = {s: box_stats(s) for s in args.spm}
        coefs = fit_spm(plain, boxes)
        for (group, target), c in coefs.items():
            ys, ps, ws = [], [], []
            for s in args.spm:
                for p, b in boxes[s].items():
                    if b["pos"] == group and b["hours"] >= MIN_SPM_HOURS and p in plain[s]:
                        ys.append(plain[s][p][target])
                        ps.append(float(np.array([1.0] + [b[k] for k in FEATURES]) @ c))
                        ws.append(b["hours"])
            r = np.corrcoef(ys, ps)[0, 1]
            terms = ", ".join(f"{k} {v:+.3f}" for k, v in zip(["const"] + FEATURES, c))
            print(f"{group} {target:<8} r {r:.3f}  ({terms})")

    if args.compare:
        target = args.compare
        history = [s for s in SEASONS if s < target]
        _, design = rapm.build(history + [target])
        score = rapm.build([target], design=design)[0][0]
        print(f"scoring on {target} ({score.weight:.0f} hours)")
        print(f"  controls only        {score.error(_controls_only(history, design)):.4f}")
        _, betas, d = chain_ratings(history)
        print(f"  chain                {score.error(_remap(betas[history[-1]], d, design)):.4f}")
        for defense in (True, False):
            for alpha in (0.3, 0.7, 0.9):
                _, betas, d = chain_with_box(history, rapm.CHAIN_LAMBDA, alpha, defense=defense)
                label = "offense and defense" if defense else "offense only"
                print(f"  chain + box, {label}, alpha {alpha}  {score.error(_remap(betas[history[-1]], d, design)):.4f}")


def _controls_only(seasons, design):
    sums = rapm.build(seasons, design=design)[0][0]
    return rapm.solve(sums, design, 1e9)


def _remap(beta, source, target):
    """A beta from one design in another's columns (players the source doesn't know get 0)."""
    out = np.zeros(target.n)
    for p, i in target.index.items():
        j = source.index.get(p)
        if j is not None:
            out[i] = beta[j]
            out[target.n_players + i] = beta[source.n_players + j]
    for c, i in target.controls.items():
        out[i] = beta[source.controls[c]]
    return out


if __name__ == "__main__":
    main()
