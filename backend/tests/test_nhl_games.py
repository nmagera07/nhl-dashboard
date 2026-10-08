"""
nhl_games.game_boxscore -- merges the NHL's three gamecenter endpoints.
_get is faked, so no network calls are made.
"""

import pytest

import nhl_games
from nhl_games import NHLGamesUnavailable, game_boxscore

BOXSCORE = {"id": 2026020044, "gameState": "OFF", "awayTeam": {"abbrev": "NSH"}, "homeTeam": {"abbrev": "TOR"}}
LANDING = {"summary": {"scoring": [{"goals": []}], "threeStars": []}}
RIGHT_RAIL = {
    "linescore": {"byPeriod": [], "totals": {"away": 4, "home": 5}},
    "shotsByPeriod": [{"away": 11, "home": 8}],
    "teamGameStats": [{"category": "sog", "awayValue": 25, "homeValue": 37}],
}


def _fake_get(responses):
    def fake(path):
        for suffix, response in responses.items():
            if path.endswith(suffix):
                if isinstance(response, Exception):
                    raise response
                return response
        raise AssertionError(f"unexpected path {path}")

    return fake


class TestGameBoxscore:
    def test_merges_all_three_endpoints(self, monkeypatch):
        monkeypatch.setattr(
            nhl_games, "_get", _fake_get({"/boxscore": BOXSCORE, "/landing": LANDING, "/right-rail": RIGHT_RAIL})
        )

        game = game_boxscore(2026020044)

        assert game["id"] == 2026020044
        assert game["awayTeam"]["abbrev"] == "NSH"
        assert game["summary"] == LANDING["summary"]
        assert game["linescore"]["totals"] == {"away": 4, "home": 5}
        assert game["shotsByPeriod"] == RIGHT_RAIL["shotsByPeriod"]
        assert game["teamGameStats"] == RIGHT_RAIL["teamGameStats"]

    def test_landing_and_right_rail_outages_still_return_the_core_box_score(self, monkeypatch):
        down = NHLGamesUnavailable("down")
        monkeypatch.setattr(
            nhl_games, "_get", _fake_get({"/boxscore": BOXSCORE, "/landing": down, "/right-rail": down})
        )

        game = game_boxscore(2026020044)

        assert game["id"] == 2026020044
        assert game["summary"] == {}
        assert game["linescore"] == {}
        assert game["shotsByPeriod"] == []
        assert game["teamGameStats"] == []

    def test_boxscore_outage_is_still_an_error(self, monkeypatch):
        monkeypatch.setattr(
            nhl_games,
            "_get",
            _fake_get({"/boxscore": NHLGamesUnavailable("down"), "/landing": LANDING, "/right-rail": RIGHT_RAIL}),
        )

        with pytest.raises(NHLGamesUnavailable):
            game_boxscore(2026020044)
