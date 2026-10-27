"""war_v2: goals above average from RAPM and the other parts, then replacement level and wins."""

import pytest

import war_v2

LEAGUE = {"pp_seconds": 3600.0, "pp_xgf": 7.0, "pk_seconds": 3600.0, "pk_xga": 7.0, "pp_net_xg": 6.0, "pim": 40}


def _player(pos="F", gp=82, **kw):
    base = {"name": "X", "pos": pos, "team": "PIT", "gp": gp, "goals": 0, "ixg": 0.0, "pim_taken": 0, "pim_drawn": 0,
            "pp_seconds": 0.0, "pp_xgf": 0.0, "pk_seconds": 0.0, "pk_xga": 0.0}
    return {**base, **kw}


def test_each_part_in_goals():
    inputs = {"league": LEAGUE, "players": {1: _player(goals=30, ixg=24.0, pim_drawn=20, pim_taken=10,
                                                       pp_seconds=7200.0, pp_xgf=19.0, pk_seconds=1800.0, pk_xga=2.5)}}
    ev = {1: {"offense": 0.3, "defense": -0.1, "hours": 20.0}}
    parts = war_v2.goals_above_average(inputs, ev)[1]
    assert parts["ev_offense"] == pytest.approx(6.0) and parts["ev_defense"] == pytest.approx(-2.0)
    assert parts["finishing"] == pytest.approx(6.0)
    assert parts["power_play"] == pytest.approx((19.0 - 14.0) / 5)    # 2 hours at 7 xG/hour expected
    assert parts["penalty_kill"] == pytest.approx((3.5 - 2.5) / 4)    # half an hour: 3.5 expected against
    assert parts["penalties"] == pytest.approx(10 * 6.0 / 40)          # 10 more minutes drawn than taken
    assert parts["total"] == pytest.approx(sum(v for k, v in parts.items() if k != "total"))
    assert war_v2.goals_above_average(inputs, ev, finishing_weight=0.5)[1]["finishing"] == pytest.approx(3.0)


def test_replacement_is_the_fringe_players_rate_per_game():
    players = {1: _player(gp=80, goals=10, ixg=0.0), 2: _player(gp=10, goals=0, ixg=2.0), 3: _player(gp=20, goals=0, ixg=3.0),
               4: _player(pos="D", gp=80)}
    out = war_v2.skater_war({"league": LEAGUE, "players": players}, ev={}, goals_per_win=5.0)
    rate = (-2.0 - 3.0) / 30  # the 5-29 GP forwards: -5 goals over 30 games
    assert out[1]["gar"] == pytest.approx(round(10 - rate * 80, 2), abs=0.01)
    assert out[1]["war"] == pytest.approx(out[1]["gar"] / 5.0, abs=0.01)
    assert out[2]["parts"]["finishing"] == -2.0
