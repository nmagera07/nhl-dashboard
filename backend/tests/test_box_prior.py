"""box_prior: the SPM fit and the prior it gives RAPM."""

import numpy as np
import pytest

import box_prior as bp
import rapm


def _box(pos="F", hours=10.0, ixg=1.0, **kw):
    return {"pos": pos, "hours": hours, **{k: 0.0 for k in bp.FEATURES}, "ixg": ixg, **kw}


def _coefs():
    zero = np.zeros(len(bp.FEATURES) + 1)
    offense = zero.copy()
    offense[1 + bp.FEATURES.index("ixg")] = 0.5  # +0.5 offense per ixG/60
    defense = zero.copy()
    defense[0] = 0.2
    return {(g, t): (offense if t == "offense" else defense) for g in ("F", "D") for t in ("offense", "defense")}


def test_the_box_estimate_trusts_ice_time():
    offense, defense = bp.box_estimate(_box(hours=bp.BOX_HOURS, ixg=2.0), _coefs())
    assert offense == pytest.approx(1.0 * 0.5) and defense == pytest.approx(0.2 * 0.5)  # half trust at BOX_HOURS


def test_the_prior_blends_last_season_and_the_box_estimate():
    design = rapm.Design([1, 2])
    previous = np.zeros(design.n)
    previous[design.index[1]] = 0.4                    # player 1's offense last season
    previous[design.n_players + design.index[1]] = 0.1  # and defense (positive beta = allows more)
    box = {1: _box(hours=1e9, ixg=2.0), 2: _box(hours=1e9, ixg=4.0)}
    prior = bp.prior_vector(design, box, _coefs(), previous, previous_hours={1: 12.0}, alpha=0.75)
    assert prior[design.index[1]] == pytest.approx(0.75 * 0.4 + 0.25 * 1.0)
    assert prior[design.n_players + design.index[1]] == pytest.approx(0.75 * 0.1 + 0.25 * -0.2)
    assert prior[design.index[2]] == pytest.approx(2.0)  # new: the box estimate alone

    offense_only = bp.prior_vector(design, box, _coefs(), previous, {1: 12.0}, alpha=0.75, defense=False)
    assert offense_only[design.n_players + design.index[1]] == pytest.approx(0.1)  # defense left on last season
    assert offense_only[design.n_players + design.index[2]] == 0.0
