import pytest

import win_probability as wp

HOME, AWAY = 1, 2


def _play(kind, period, clock, team=None, **details):
    return {"typeDescKey": kind, "timeInPeriod": clock, "eventId": len(details) + period * 1000,
            "periodDescriptor": {"number": period, "periodType": "REG" if period <= 3 else "OT"},
            "details": {"eventOwnerTeamId": team, **details}}


def _game(plays, state="LIVE", home_score=0, away_score=0, game_type=2):
    return {"gameType": game_type, "gameState": state, "plays": plays,
            "homeTeam": {"id": HOME, "abbrev": "PIT", "score": home_score},
            "awayTeam": {"id": AWAY, "abbrev": "PHI", "score": away_score},
            "rosterSpots": [{"playerId": 71, "firstName": {"default": "Evgeni"}, "lastName": {"default": "Malkin"}}]}


def test_even_teams_tied_late_is_near_a_coin_flip_with_a_home_shootout_edge():
    p = wp.home_win_prob(2.8, 2.8, 0, 1)
    assert 0.5 < p < 0.55


def test_a_lead_is_worth_more_the_less_time_is_left():
    early, late = wp.home_win_prob(2.8, 2.8, 1, 3000), wp.home_win_prob(2.8, 2.8, 1, 300)
    assert 0.6 < early < late < 0.95
    assert wp.home_win_prob(2.8, 2.8, -1, 300) == pytest.approx(1 - late, abs=0.08)


def test_a_power_play_helps_the_team_on_it():
    assert wp.home_win_prob(2.8, 2.8, 0, 1800, pp_home_seconds=120) > wp.home_win_prob(2.8, 2.8, 0, 1800)
    assert wp.home_win_prob(2.8, 2.8, 0, 1800, pp_away_seconds=120) < wp.home_win_prob(2.8, 2.8, 0, 1800)


def test_overtime_goal_and_end_of_regulation_are_decided():
    assert wp.home_win_prob(2.8, 2.8, 1, 120, in_overtime=True) == 1.0
    assert wp.home_win_prob(2.8, 2.8, -1, 0) == 0.0
    assert wp.home_win_prob(2.8, 2.8, 0, 0, playoff=True) == pytest.approx(0.525, abs=0.01)


def test_anchor_starts_the_curve_at_the_pregame_chance():
    home_mu, away_mu = wp.anchor(3.0, 2.6, 0.62)
    assert wp.home_win_prob(home_mu, away_mu, 0, wp.REGULATION_SECONDS) == pytest.approx(0.62, abs=1e-4)
    assert home_mu * away_mu == pytest.approx(3.0 * 2.6)


def test_series_replays_goals_and_ends_at_the_result():
    pbp = _game([
        _play("goal", 1, "05:00", HOME, scoringPlayerId=71),
        _play("penalty", 2, "10:00", HOME, typeCode="MIN", duration=2),
        _play("goal", 2, "11:00", AWAY),
        _play("period-end", 3, "20:00"),
    ], state="OFF", home_score=1, away_score=1)
    pbp["homeTeam"]["score"] = 2  # won in the shootout
    curve = wp.series(pbp, 2.8, 2.8)
    seconds = [s for s, _ in curve["points"]]
    assert seconds == sorted(seconds) and seconds[0] == 0
    assert curve["points"][-1] == (3600, 1.0)
    first, second = curve["goals"]
    assert first == {"second": 300, "team": "home", "scorer": "E. Malkin", "before": first["before"], "after": first["after"]}
    assert first["after"] > first["before"] and second["after"] < second["before"]
    assert second["team"] == "away"
    assert wp.biggest_swing(curve["goals"]) in curve["goals"]


def test_a_power_play_goal_ends_the_minor():
    pbp = _game([_play("penalty", 1, "10:00", AWAY, typeCode="MIN", duration=2), _play("goal", 1, "10:30", HOME),
                 _play("faceoff", 1, "11:00")])
    with_pp = wp.series(pbp, 2.8, 2.8, at=[631])["points"][0][1]
    no_pp = wp.series(_game([_play("goal", 1, "10:30", HOME), _play("faceoff", 1, "11:00")]), 2.8, 2.8, at=[631])
    assert with_pp == pytest.approx(no_pp["points"][0][1])


def test_checkpoints_only_compute_the_seconds_asked_for():
    pbp = _game([_play("goal", 1, "05:00", HOME), _play("faceoff", 2, "10:00")])
    assert [s for s, _ in wp.series(pbp, 2.8, 2.8, at=[0, 600, 1500])["points"]] == [0, 600, 1500]


def test_endpoint_returns_the_curve(client, monkeypatch, db_router):
    import api

    pbp = _game([_play("goal", 1, "05:00", HOME, scoringPlayerId=71), _play("faceoff", 1, "08:00")])
    monkeypatch.setattr(api, "game_play_by_play", lambda game_id: pbp)
    db_router.when("from game_predictions", {"home_win_prob": 0.6, "home_goals": 3.0, "away_goals": 2.7})

    body = client.get("/games/2026020001/win-probability").json()

    assert body["available"] is True and body["pregame"] == 0.6
    assert body["points"][0] == [0, pytest.approx(0.6, abs=1e-3)]
    assert body["swing"]["scorer"] == "E. Malkin"


def test_endpoint_is_unavailable_before_puck_drop_or_without_a_prediction(client, monkeypatch, db_router):
    import api

    monkeypatch.setattr(api, "game_play_by_play", lambda game_id: _game([], state="FUT"))
    assert client.get("/games/2026020001/win-probability").json() == {"available": False}

    monkeypatch.setattr(api, "game_play_by_play", lambda game_id: _game([_play("faceoff", 1, "00:00")]))
    db_router.when("from game_predictions", None)
    assert client.get("/games/2026020002/win-probability").json() == {"available": False}
