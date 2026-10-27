"""rapm: the stint regression, its sums, and the prior."""

import numpy as np
import pytest

import rapm


def _stint(home, away, seconds, home_xg, away_xg, score=0, zone=None):
    return {"home": home, "away": away, "seconds": seconds, "home_xg": home_xg, "away_xg": away_xg,
            "score": score, "zone": zone}


def _games(n=60):
    """Home skater 1 or 6 rotates in; every stint with 1 on the ice creates far more xG for the home side."""
    rng = np.random.default_rng(0)
    games = {}
    for g in range(n):
        stints = []
        for k in range(20):
            star = k % 2 == 0
            home = [1 if star else 6, 2, 3, 4, 5]
            stints.append(_stint(home, [21, 22, 23, 24, 25], 60, (0.12 if star else 0.03) + rng.uniform(0, 0.01), 0.05))
        games[str(g)] = stints
    return games


def _fit(games, lam=1.0, prior=None):
    design = rapm.Design({p for g in games.values() for s in g for p in s["home"] + s["away"]})
    sums = rapm.Sums(design.n)
    cols, ys, ws = [], [], []
    for _, offense, defense, controls, y, w in rapm.rows(games):
        cols.append(design.encode(offense, defense, controls))
        ys.append(y)
        ws.append(w)
    sums.add(cols, ys, ws)
    return design, sums, rapm.solve(sums, design, lam, prior)


def test_the_player_on_for_the_chances_gets_the_offense():
    design, sums, beta = _fit(_games())
    rated = rapm.ratings(beta, design, sums)
    assert rated[1]["offense"] > 1.0 > 0 > rated[6]["offense"]  # +5.4 xG/60 between them, split around 0
    assert abs(rated[2]["offense"]) < 0.3  # always on the ice: no credit for what 1 and 6 did
    assert rated[1]["hours"] == pytest.approx(60 * 10 * 60 / 3600)


def test_the_error_from_the_sums_matches_the_rows():
    design, sums, beta = _fit(_games(5))
    direct = [(y - sum(beta[c] for c in design.encode(o, d, ctl) if c < design.n)) ** 2 * w
              for _, o, d, ctl, y, w in rapm.rows(_games(5))]
    assert sums.error(beta) == pytest.approx(sum(direct) / sums.weight)


def test_rows_read_score_and_zone_from_each_attacking_side():
    rows = list(rapm.rows({"1": [_stint([1, 2, 3, 4, 5], [6, 7, 8, 9, 10], 30, 0.1, 0.0, score=-2, zone="O")]}))
    (_, _, _, home_controls, home_y, w), (_, _, _, away_controls, _, _) = rows
    assert sorted(home_controls) == ["home", "intercept", "ozone", "trail2"]  # home trails by 2, faceoff in the away end
    assert sorted(away_controls) == ["dzone", "intercept", "lead2"]
    assert home_y == pytest.approx(0.1 * 120) and w == pytest.approx(30 / 3600)


def test_a_heavy_penalty_pulls_players_to_their_prior():
    design, sums, _ = _fit(_games())
    prior = np.zeros(design.n)
    prior[design.index[6]] = 2.0
    beta = rapm.solve(sums, design, 1e9, prior)
    assert beta[design.index[6]] == pytest.approx(2.0, abs=1e-3) and beta[design.index[1]] == pytest.approx(0.0, abs=1e-3)
