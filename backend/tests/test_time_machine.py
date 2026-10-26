"""time_machine and GET /players/{id}/time-machine."""

import pytest

import time_machine
from tests.test_compare_card import ERA, GRETZKY, MCDAVID


def test_simulate_is_seeded_and_centered_on_the_rate():
    a = time_machine.simulate(0.5, 1.0, seed="x", sims=2000)
    assert a == time_machine.simulate(0.5, 1.0, seed="x", sims=2000)  # a shared link shows the same numbers
    # 1.5 points a game over 82 games = 123
    assert abs(a["points"]["median"] - 123) <= 3
    assert a["points"]["low"] < a["points"]["median"] < a["points"]["high"]
    assert sum(n for _, n in a["histogram"]) == 2000
    assert a["bin_width"] >= 1


def test_simulate_a_scoreless_rate():
    out = time_machine.simulate(0, 0, seed="zero", sims=100)
    assert out["points"] == {"median": 0, "low": 0, "high": 0}
    assert out["histogram"] == [[0, 100]]


def test_run_translates_by_league_scoring():
    out = time_machine.run(GRETZKY, None, 20252026, {**ERA["seasons"], "20252026": ERA["reference"]})
    assert out["source"]["season_id"] == 19851986  # his best season by default
    assert out["factor"] == round(3.08 / 3.97, 3)
    # 215 points in 80 games, times 3.08/3.97, over 82 games = 171
    assert out["pace_82"]["points"] == 171
    assert abs(out["points"]["median"] - 171) <= 4


@pytest.mark.parametrize("player,season,message", [
    ({**GRETZKY, "position_code": "G"}, None, "skaters"),
    (GRETZKY, 19801981, "19801981"),
    ({**GRETZKY, "season_history": []}, None, "No NHL"),
])
def test_run_refuses(player, season, message):
    with pytest.raises(ValueError, match=message):
        time_machine.run(player, season, 20252026, {**ERA["seasons"], "20252026": 3.08})


def test_route(client, monkeypatch):
    import api
    players = {8447400: GRETZKY, 8478402: MCDAVID, 8451033: {**GRETZKY, "position_code": "G"}}
    monkeypatch.setattr(api, "player_detail", lambda pid: players[pid])
    monkeypatch.setattr(api, "era_scoring", lambda: {**ERA, "seasons": {**ERA["seasons"], "20252026": 3.08}})
    body = client.get("/players/8478402/time-machine?target=19851986").json()
    assert body["player"]["name"] == "Connor McDavid" and body["target"]["season_id"] == 19851986
    assert body["points"]["median"] > 153  # more goals per game in 1985-86
    assert client.get("/players/8447400/time-machine").json()["target"]["season_id"] == 20252026  # today by default
    assert client.get("/players/8451033/time-machine").status_code == 400
