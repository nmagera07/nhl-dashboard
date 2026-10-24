"""nhl_players: retired players from the NHL's search and profile pages, and the API routes."""

import pytest

import nhl_players

LANDING = {
    "playerId": 8447400, "firstName": {"default": "Wayne"}, "lastName": {"default": "Gretzky"}, "position": "C",
    "sweaterNumber": 99, "shootsCatches": "L", "heightInInches": 72, "weightInPounds": 185, "birthDate": "1961-01-26",
    "birthCity": {"default": "Brantford"}, "birthCountry": "CAN", "headshot": "https://x/8447400.png",
    "isActive": False, "inHHOF": 1,
    "careerTotals": {"regularSeason": {"gamesPlayed": 1487, "goals": 894, "assists": 1963, "points": 2857},
                     "playoffs": {"gamesPlayed": 208, "goals": 122, "assists": 260, "points": 382}},
    "seasonTotals": [
        {"season": 19781979, "leagueAbbrev": "WHA", "gameTypeId": 2, "gamesPlayed": 80, "goals": 46, "points": 110},
        {"season": 19791980, "leagueAbbrev": "NHL", "gameTypeId": 2, "gamesPlayed": 79, "goals": 51, "assists": 86,
         "points": 137, "teamName": {"default": "Edmonton Oilers"}, "sequence": 1},
        {"season": 19951996, "leagueAbbrev": "NHL", "gameTypeId": 2, "gamesPlayed": 62, "goals": 15, "assists": 66,
         "points": 81, "shots": 144, "teamName": {"default": "Los Angeles Kings"}, "sequence": 1},
        {"season": 19951996, "leagueAbbrev": "NHL", "gameTypeId": 2, "gamesPlayed": 18, "goals": 8, "assists": 13,
         "points": 21, "shots": 51, "teamName": {"default": "St. Louis Blues"}, "sequence": 2},
        {"season": 19981999, "leagueAbbrev": "NHL", "gameTypeId": 2, "gamesPlayed": 70, "goals": 9, "assists": 53,
         "points": 62, "teamName": {"default": "New York Rangers"}, "sequence": 1},
    ],
}


def test_a_retired_players_page_has_nhl_seasons_only_with_trades_combined():
    d = nhl_players.player_detail(LANDING)
    assert (d["first_name"], d["last_name"], d["status"], d["in_hall_of_fame"]) == ("Wayne", "Gretzky", "retired", True)
    assert (d["last_season_id"], d["last_team_name"], d["team_abbrev"]) == (19981999, "New York Rangers", None)
    assert [r["season_id"] for r in d["season_history"]] == [19981999, 19951996, 19791980]  # no WHA
    traded = d["season_history"][1]
    assert (traded["games_played"], traded["points"]) == (80, 102)
    assert d["career_totals"]["regular_season"]["points"] == 2857


def test_drafted_but_never_played_is_not_found():
    with pytest.raises(nhl_players.PlayerNotFound):
        nhl_players.player_detail({**LANDING, "seasonTotals": [LANDING["seasonTotals"][0]]})


def test_search_skips_players_who_never_played_and_lists_recent_ones_first():
    class Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return [{"playerId": "8456438", "name": "Keith Gretzky", "lastSeasonId": None, "active": False},
                    {"playerId": "8458985", "name": "Brent Gretzky", "lastSeasonId": "19941995", "active": False},
                    {"playerId": "8447400", "name": "Wayne Gretzky", "lastSeasonId": "19981999", "active": False,
                     "lastTeamAbbrev": "NYR", "positionCode": "C"}]

    found = nhl_players.search("gretzky", get=lambda *a, **k: Resp())
    assert [p["name"] for p in found] == ["Wayne Gretzky", "Brent Gretzky"]
    assert found[0] == {"player_id": 8447400, "name": "Wayne Gretzky", "position_code": "C", "active": False,
                        "last_team_abbrev": "NYR", "last_season_id": 19981999}


class TestApi:
    def test_a_player_not_on_a_roster_comes_from_the_nhl(self, client, db_router, monkeypatch):
        db_router.when("from players p", None)
        monkeypatch.setattr(nhl_players, "fetch_landing", lambda pid: LANDING)
        body = client.get("/players/8447400").json()
        assert body["status"] == "retired" and body["team_abbrev"] is None
        assert body["career_totals"]["regular_season"]["points"] == 2857

    def test_never_played_is_a_404(self, client, db_router, monkeypatch):
        db_router.when("from players p", None)

        def missing(pid):
            raise nhl_players.PlayerNotFound(pid)

        monkeypatch.setattr(nhl_players, "fetch_landing", missing)
        assert client.get("/players/8456438").status_code == 404

    def test_search(self, client, monkeypatch):
        monkeypatch.setattr(nhl_players, "search", lambda q: [{"player_id": 8447400, "name": "Wayne Gretzky"}])
        assert client.get("/players/search?q=Gretzky").json() == {"players": [{"player_id": 8447400, "name": "Wayne Gretzky"}]}
        assert client.get("/players/search?q=a").status_code == 422


def test_imports_without_a_database_setting():
    """The API runs without DATABASE_URL (it has its own read-only setting); importing this must not need it."""
    import os
    import subprocess
    import sys

    env = {k: v for k, v in os.environ.items() if k != "DATABASE_URL"}
    code = "import os, dotenv; dotenv.load_dotenv = lambda *a, **k: False; import nhl_players"
    result = subprocess.run([sys.executable, "-c", code], cwd=os.path.dirname(nhl_players.__file__), env=env,
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
