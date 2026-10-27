"""
RAPM (WAR v2 step 2): each skater's 5-on-5 offense and defense, separated
from his linemates and the opponents he faced.

Every stint (rapm_stints.py) is two rows, one per attacking side:
    xG/60 of the attacking side = intercept
        + offense of each of its five skaters
        + defense of each of the five defenders   (positive = allows more)
        + home ice + score state + where the stint's faceoff was
weighted by the stint's length (so short stints barely count), and fit by
ridge regression: every player's numbers are pulled toward league average
(0) by lambda, so a player with few minutes stays near 0 until the data
says otherwise. Controls (home, score, zone) aren't pulled.

Score state is from the attacking side (trailing teams push), with tied as
the baseline; zone is an offensive- or defensive-zone faceoff for the
attacking side, with neutral-zone and on-the-fly starts as the baseline.

Every column is a 0/1 indicator, so the normal equations (X'WX, X'Wy, y'Wy)
are built by counting with np.bincount, without a sparse-matrix library.
Those sums also score a fit on held-out games (squared error from the
sums alone), which is how lambda is picked: 5-fold cross-validation by
game.

Results are per 60 minutes at 5-on-5. Reported "defense" is flipped so
that positive is good (xG against prevented per 60).

Usage:
    python rapm.py --cv 20242025 20252026          # pick lambda
    python rapm.py --fit 20252026 --top 20          # one season's leaders
    python rapm.py --predict 20242025 20252026      # fit one season, score the next
    python rapm.py --repeat 20242025 20252026       # year-over-year, RAPM vs raw on-ice
"""

import argparse
from collections import defaultdict

import numpy as np

import rapm_stints as rs

LAMBDA = 15.0  # in hours of 5v5 (row weights are hours); --cv and --predict on 2024-26 both pick ~10-25
CONTROLS = ["intercept", "home", "trail2", "trail1", "lead1", "lead2", "ozone", "dzone"]
WIDTH = 1 + 5 + 5 + 4  # intercept, 5 attackers, 5 defenders, home/score/zone (padded)
CHUNK = 100_000


def _score_col(lead):
    if lead <= -2:
        return "trail2"
    if lead == -1:
        return "trail1"
    if lead == 1:
        return "lead1"
    if lead >= 2:
        return "lead2"
    return None


def rows(games, season_weight=1.0):
    """
    Each stint as two attacking-side rows: (players on offense, players on
    defense, controls, xG/60, weight in hours). `games` is {game_id: [stints]}.
    """
    for game_id, stints in games.items():
        for s in stints:
            if s["seconds"] <= 0:
                continue
            hours = s["seconds"] / 3600 * season_weight
            for side, other, sign in (("home", "away", 1), ("away", "home", -1)):
                lead = s["score"] * sign
                zone = s["zone"] if side == "home" else {"O": "D", "D": "O"}.get(s["zone"], s["zone"])
                controls = ["intercept", _score_col(lead), {"O": "ozone", "D": "dzone"}.get(zone)]
                if side == "home":
                    controls.append("home")
                yield game_id, s[side], s[other], [c for c in controls if c], s[f"{side}_xg"] / (s["seconds"] / 3600), hours


class Design:
    """Column numbers: offense of player i is i, defense is P + i, then the controls; one padding column at the end."""

    def __init__(self, players):
        self.players = sorted(players)
        self.index = {p: i for i, p in enumerate(self.players)}
        self.n_players = len(self.players)
        self.controls = {c: 2 * self.n_players + i for i, c in enumerate(CONTROLS)}
        self.n = 2 * self.n_players + len(CONTROLS)
        self.pad = self.n

    def encode(self, offense, defense, controls):
        cols = ([self.index[p] for p in offense] + [self.n_players + self.index[p] for p in defense]
                + [self.controls[c] for c in controls])
        return cols + [self.pad] * (WIDTH - len(cols))


class Sums:
    """X'WX, X'Wy, y'Wy and total weight for a set of rows."""

    def __init__(self, n):
        self.n = n
        self.xtx = np.zeros((n, n))
        self.xty = np.zeros(n)
        self.yty = 0.0
        self.weight = 0.0

    def add(self, cols, y, w):
        cols, y, w = np.asarray(cols, dtype=np.int64), np.asarray(y), np.asarray(w)
        side = self.n + 1
        pairs = (cols[:, :, None] * side + cols[:, None, :]).ravel()
        counts = np.bincount(pairs, weights=np.repeat(w, WIDTH * WIDTH), minlength=side * side)
        self.xtx += counts.reshape(side, side)[: self.n, : self.n]
        self.xty += np.bincount(cols.ravel(), weights=np.repeat(w * y, WIDTH), minlength=side)[: self.n]
        self.yty += float(np.sum(w * y * y))
        self.weight += float(np.sum(w))

    def __add__(self, other):
        out = Sums(self.n)
        out.xtx, out.xty = self.xtx + other.xtx, self.xty + other.xty
        out.yty, out.weight = self.yty + other.yty, self.weight + other.weight
        return out

    def __sub__(self, other):
        out = Sums(self.n)
        out.xtx, out.xty = self.xtx - other.xtx, self.xty - other.xty
        out.yty, out.weight = self.yty - other.yty, self.weight - other.weight
        return out

    def error(self, beta):
        """Weighted mean squared error of beta on these rows, from the sums alone."""
        return (self.yty - 2 * beta @ self.xty + beta @ self.xtx @ beta) / self.weight


def build(seasons, design=None, folds=1, weights=None):
    """
    ({fold: Sums}, design) for the seasons' rows; games are split into
    `folds` groups by game id (for cross-validation). `weights` maps a
    season to its row weight (default 1).
    """
    loaded = {season: rs.load_stints(season) for season in seasons}
    if design is None:
        players = {p for games in loaded.values() for g in games.values() for s in g for p in s["home"] + s["away"]}
        design = Design(players)
    sums = {f: Sums(design.n) for f in range(folds)}
    batch = defaultdict(lambda: ([], [], []))
    for season, games in loaded.items():
        for game_id, offense, defense, controls, y, w in rows(games, (weights or {}).get(season, 1.0)):
            if not all(p in design.index for p in offense + defense):
                continue  # a player the design doesn't know (scoring a fit on a later season)
            fold = int(game_id) % folds
            cols, ys, ws = batch[fold]
            cols.append(design.encode(offense, defense, controls))
            ys.append(y)
            ws.append(w)
            if len(cols) >= CHUNK:
                sums[fold].add(cols, ys, ws)
                batch[fold] = ([], [], [])
    for fold, (cols, ys, ws) in batch.items():
        if cols:
            sums[fold].add(cols, ys, ws)
    return sums, design


def solve(sums, design, lam=LAMBDA, prior=None):
    """
    Ridge solution. Player columns are pulled toward 0, or toward `prior`
    (a beta from an earlier fit with the same design) when given.
    """
    penalty = np.zeros(design.n)
    penalty[: 2 * design.n_players] = lam
    target = penalty * (prior if prior is not None else 0.0)
    return np.linalg.solve(sums.xtx + np.diag(penalty) + np.eye(design.n) * 1e-9, sums.xty + target)


def ratings(beta, design, sums):
    """{player: {offense, defense, net, hours}} per 60 at 5-on-5; defense positive = prevents xG."""
    hours = np.diag(sums.xtx)  # a player's weighted rows: on offense (= his ice time) and on defense
    out = {}
    for p, i in design.index.items():
        offense, defense = beta[i], -beta[design.n_players + i]
        out[p] = {"offense": float(offense), "defense": float(defense), "net": float(offense + defense),
                  "hours": float(hours[i])}
    return out


def _scaled(sums, factor):
    out = Sums(sums.n)
    out.xtx, out.xty, out.yty, out.weight = sums.xtx * factor, sums.xty * factor, sums.yty * factor, sums.weight * factor
    return out


def cross_validate(seasons, lambdas, folds=5):
    sums, design = build(seasons, folds=folds)
    total = sum(sums.values(), Sums(design.n))
    results = {}
    for lam in lambdas:
        errors = [sums[f].error(solve(total - sums[f], design, lam)) for f in range(folds)]
        results[lam] = float(np.mean(errors))
    return results


def _names(players):
    """Player names from the cached play-by-play rosters (offline, no database)."""
    names = {}
    for season in (20262027, 20252026, 20242025, 20232024):
        for game_id in rs._game_ids(season)[-200:]:
            for r in (rs.load("pbp", season, game_id) or {}).get("rosterSpots", []):
                names.setdefault(r["playerId"], f"{r['firstName']['default']} {r['lastName']['default']}")
        if players <= names.keys():
            break
    return names


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--cv", nargs="+", type=int, metavar="SEASON")
    parser.add_argument("--fit", nargs="+", type=int, metavar="SEASON")
    parser.add_argument("--predict", nargs=2, type=int, metavar=("FIT", "SCORE"))
    parser.add_argument("--compare", nargs=3, type=int, metavar=("OLDER", "LAST", "SCORE"),
                        help="one season vs. two weighted vs. last season with the older one as its prior")
    parser.add_argument("--repeat", nargs=2, type=int, metavar=("FIRST", "SECOND"))
    parser.add_argument("--lam", type=float, default=LAMBDA)
    parser.add_argument("--top", type=int, default=15)
    parser.add_argument("--min-hours", type=float, default=500 / 60)
    args = parser.parse_args()

    if args.cv:
        for lam, error in cross_validate(args.cv, [3, 10, 20, 40, 80, 150, 300, 1e9]).items():
            print(f"lambda {lam:>12,.0f}: held-out error {error:.4f}")

    if args.fit:
        sums, design = build(args.fit)
        total = sums[0]
        beta = solve(total, design, args.lam)
        print("controls (xG/60):", {c: round(float(beta[i]), 3) for c, i in design.controls.items()})
        rated = {p: r for p, r in ratings(beta, design, total).items() if r["hours"] >= args.min_hours}
        names = _names(set(rated))
        ranked = sorted(rated.items(), key=lambda kv: kv[1]["net"], reverse=True)
        for label, chunk in (("best", ranked[: args.top]), ("worst", ranked[-args.top:])):
            print(f"-- {label} net (of {len(ranked)} with {args.min_hours * 60:.0f}+ min)")
            for p, r in chunk:
                print(f"  {names.get(p, p):<24} off {r['offense']:+.3f}  def {r['defense']:+.3f}  "
                      f"net {r['net']:+.3f}  {r['hours'] * 60:.0f} min")

    if args.predict:
        first, second = args.predict
        fit_sums, design = build([first])
        score_sums, _ = build([second], design=design)
        for lam in (5, 10, 15, 25, 50, 1e9):
            beta = solve(fit_sums[0], design, lam)
            print(f"lambda {lam:>12,.0f}: {second} error {score_sums[0].error(beta):.4f}"
                  + ("  (no players: controls only)" if lam >= 1e9 else ""))

    if args.compare:
        older, last, score = args.compare
        sums, design = build([older, last, score])  # one design so every fit scores the same rows
        by_season = {season: build([season], design=design)[0][0] for season in (older, last, score)}
        target = by_season[score]
        print(f"scoring on {score} ({target.weight:.0f} hours of rows)")
        print(f"  controls only:               {target.error(solve(by_season[last], design, 1e9)):.4f}")
        for lam in (10, 15, 25):
            print(f"  lambda {lam}: {last} alone       {target.error(solve(by_season[last], design, lam)):.4f}")
        for decay in (0.25, 0.5, 1.0):
            for lam in (15, 25, 40):
                both = by_season[last] + _scaled(by_season[older], decay)
                print(f"  lambda {lam}: {older} x{decay} + {last}  {target.error(solve(both, design, lam)):.4f}")
        for lam_prior in (15, 25):
            prior = solve(by_season[older], design, lam_prior)
            for lam in (10, 15, 25, 40):
                print(f"  lambda {lam}: {last}, prior {older} (lambda {lam_prior})  "
                      f"{target.error(solve(by_season[last], design, lam, prior)):.4f}")

    if args.repeat:
        first, second = args.repeat
        fits = {}
        for season in (first, second):
            sums, design = build([season])
            fits[season] = ratings(solve(sums[0], design, args.lam), design, sums[0])
        raw = {season: _raw_on_ice(season) for season in (first, second)}
        both = [p for p in fits[first] if p in fits[second]
                and min(fits[first][p]["hours"], fits[second][p]["hours"]) >= args.min_hours]
        teams = {season: _teams(season) for season in (first, second)}
        moved = [p for p in both if teams[first].get(p) != teams[second].get(p)]
        for label, group in (("all", both), ("changed teams", moved)):
            print(f"-- {label} ({len(group)} players with {args.min_hours * 60:.0f}+ min both seasons)")
            for key in ("offense", "defense", "net"):
                a = [fits[first][p][key] for p in group]
                b = [fits[second][p][key] for p in group]
                ra = [raw[first][p][key] for p in group]
                rb = [raw[second][p][key] for p in group]
                print(f"  {key:<8} year-over-year r: RAPM {np.corrcoef(a, b)[0, 1]:.3f}   raw on-ice {np.corrcoef(ra, rb)[0, 1]:.3f}")


def _teams(season):
    """Each player's team for the season: the one he dressed for most (cached play-by-play rosters)."""
    games = defaultdict(lambda: defaultdict(int))
    for game_id in rs._game_ids(season):
        for r in (rs.load("pbp", season, game_id) or {}).get("rosterSpots", []):
            games[r["playerId"]][r["teamId"]] += 1
    return {p: max(by_team, key=by_team.get) for p, by_team in games.items()}


def _raw_on_ice(season):
    """On-ice xG for and against per 60 at 5-on-5, no adjustments (defense flipped: positive = good)."""
    totals = defaultdict(lambda: [0.0, 0.0, 0.0])
    for stints in rs.load_stints(season).values():
        for s in stints:
            for side, other in (("home", "away"), ("away", "home")):
                for p in s[side]:
                    t = totals[p]
                    t[0] += s[f"{side}_xg"]
                    t[1] += s[f"{other}_xg"]
                    t[2] += s["seconds"] / 3600
    out = {}
    for p, (xgf, xga, hours) in totals.items():
        if hours:
            out[p] = {"offense": xgf / hours, "defense": -xga / hours, "net": (xgf - xga) / hours}
    return out


if __name__ == "__main__":
    main()
