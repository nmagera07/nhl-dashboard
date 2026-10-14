"""xg_model: shots and features from NHL play-by-play."""

import math

import pytest

import xg_model as xm

HOME, AWAY = 1, 2


def _play(kind, t, team, x=None, y=None, zone="O", situation="1551", period=1, defending="right", **extra):
    details = {"eventOwnerTeamId": team, "zoneCode": zone, **extra}
    if x is not None:
        details.update(xCoord=x, yCoord=y)
    return {"typeDescKey": kind, "timeInPeriod": f"{t // 60:02d}:{t % 60:02d}", "situationCode": situation,
            "homeTeamDefendingSide": defending, "periodDescriptor": {"number": period, "periodType": "REG"},
            "details": details}


def _game(*plays):
    return {"id": 2025020001, "homeTeam": {"id": HOME}, "awayTeam": {"id": AWAY}, "plays": list(plays)}


def test_strength_from_the_situation_code():
    assert xm.strength("1551", shooter_is_home=True) == "EV"
    assert xm.strength("1451", shooter_is_home=True) == "PP"   # away down a skater
    assert xm.strength("1451", shooter_is_home=False) == "SH"
    assert xm.strength("0651", shooter_is_home=True) == "EN"   # away goalie pulled
    assert xm.strength("1560", shooter_is_home=True) == "PP"   # 6 v 5: home's own net is empty, not the target


def test_distance_and_angle_use_the_net_being_attacked():
    # Home defends the right side, so it attacks the left net at x = -89.
    shot = xm.shots_from_game(_game(_play("shot-on-goal", 10, HOME, x=-79, y=10, shotType="wrist")))[0]
    assert shot["distance"] == pytest.approx(math.hypot(10, 10))
    assert shot["angle"] == pytest.approx(45.0)
    # Away attacks the right net.
    away = xm.shots_from_game(_game(_play("missed-shot", 10, AWAY, x=59, y=0)))[0]
    assert away["distance"] == pytest.approx(30.0) and away["angle"] == 0


def test_rebounds_rush_score_and_blocked_shots():
    shots = xm.shots_from_game(_game(
        _play("faceoff", 0, AWAY, x=0, y=0, zone="N"),
        _play("shot-on-goal", 3, HOME, x=-60, y=5),        # 3 s after a neutral-zone faceoff: rush
        _play("shot-on-goal", 5, HOME, x=-80, y=2),        # 2 s after its own shot: rebound
        _play("goal", 6, HOME, x=-85, y=1),
        _play("blocked-shot", 30, AWAY, x=40, y=0),        # blocked: not an unblocked shot
        _play("missed-shot", 40, AWAY, x=60, y=-10),
    ))
    assert [s["goal"] for s in shots] == [0, 0, 1, 0]
    assert shots[0]["rush"] and not shots[0]["rebound"]
    assert shots[1]["rebound"]
    assert shots[3]["lead"] == -1  # the away team trails after the goal


def test_shootouts_are_left_out_and_predictions_are_probabilities():
    so = _play("goal", 0, HOME, x=-80, y=0)
    so["periodDescriptor"] = {"number": 5, "periodType": "SO"}
    assert xm.shots_from_game(_game(so)) == []

    shot = xm.shots_from_game(_game(_play("shot-on-goal", 10, HOME, x=-79, y=0)))[0]
    model = {"coefficients": [-2.5] + [0.0] * (len(xm.FEATURE_NAMES) - 1)}
    assert len(xm.feature_vector(shot)) == len(xm.FEATURE_NAMES)
    assert xm.predict(shot, model) == pytest.approx(1 / (1 + math.exp(2.5)))
