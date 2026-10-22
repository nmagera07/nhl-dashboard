"""pickem + the /pickem routes: names, locking, keys, records."""

from datetime import datetime, timezone

import pytest

import api
import pickem

GAME = {"homeTeam": {"abbrev": "DET"}, "awayTeam": {"abbrev": "PHI"}, "gameState": "FUT",
        "startTimeUTC": "2026-10-15T23:30:00Z", "gameDate": "2026-10-15"}
BEFORE = datetime(2026, 10, 15, 22, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize("name,ok", [
    ("Nate", True), ("puck_fan.87", True), ("ab", False), ("x" * 21, False), ("1234", False),
    ("PuckPulse", False), ("Puck Pulse 2", False), ("<script>", False), ("FuCkBoy", False),
])
def test_display_names(name, ok):
    assert (pickem.name_problem(name) is None) == ok


@pytest.mark.parametrize("name", [
    "n1gger", "NIIIGGER", "n.i.g.g.a", "Kike_Lover", "hitler fan", "H1tl3r", "HeilHitler", "Big Spic", "BigSpic",
    "spic99", "kkk boys", "crew1488", "14 88 crew", "White Power", "gas the jews", "DirtyJew", "zog bot", "Chink",
])
def test_slurs_and_hate_are_blocked(name):
    assert pickem.name_problem(name) == "Please pick a different name."


@pytest.mark.parametrize("name", [
    "MyAnusIsBleeding", "Conspicuous", "Raccoon Fan", "Knight Rider", "Japan Fan", "Jewel", "Night Owl",
    "Spicy Wings", "Mighty Ducks", "agent00", "Skinny Pete", "Coonhound",
])
def test_ordinary_names_still_work(name):
    assert pickem.name_problem(name) is None


def test_keys_are_random_and_stored_hashed():
    a, b = pickem.new_key(), pickem.new_key()
    assert a != b and a.startswith("pp_") and len(a) > 30
    assert pickem.hash_key(a) != a and len(pickem.hash_key(a)) == 64


def test_picks_lock_by_state_or_start_time():
    assert pickem.pick_problem(GAME, "DET", now=BEFORE) is None
    assert "two teams" in pickem.pick_problem(GAME, "PIT", now=BEFORE)
    assert "locked" in pickem.pick_problem({**GAME, "gameState": "LIVE"}, "DET", now=BEFORE)
    # Still "FUT" in a cached scoreboard, but past the start time: locked anyway.
    assert "locked" in pickem.pick_problem(GAME, "DET", now=datetime(2026, 10, 15, 23, 31, tzinfo=timezone.utc))


class TestRoutes:
    def test_join_returns_a_key_once(self, client, db_router):
        db_router.when("insert into pickem_players", None)
        body = client.post("/pickem/join", json={"name": "Nate"}).json()
        assert body["name"] == "Nate" and body["key"].startswith("pp_")
        insert = next((q, p) for q, p in db_router.calls if "insert into pickem_players" in q.lower())
        assert body["key"] not in insert[1] and pickem.hash_key(body["key"]) in insert[1]  # only the hash is stored

    def test_join_rejects_bad_names(self, client, db_router):
        response = client.post("/pickem/join", json={"name": "PuckPulse"})
        assert response.status_code == 400 and "reserved" in response.json()["detail"]

    def test_unknown_key_is_401(self, client, db_router):
        db_router.when("from pickem_players where key_hash", None)
        assert client.post("/pickem/me", json={"key": "pp_nope"}).status_code == 401

    def test_a_started_game_is_locked(self, client, db_router, monkeypatch):
        monkeypatch.setattr(api, "game_boxscore", lambda gid: {**GAME, "gameState": "LIVE"})
        response = client.post("/pickem/pick", json={"key": "pp_x", "game_id": 2026020110, "team": "DET"})
        assert response.status_code == 409 and "locked" in response.json()["detail"]
        assert not any("insert into pickem_picks" in q.lower() for q, _ in db_router.calls)

    def test_a_pick_is_saved(self, client, db_router, monkeypatch):
        monkeypatch.setattr(api, "game_boxscore", lambda gid: {**GAME, "startTimeUTC": "2099-01-01T00:00:00Z"})
        db_router.when("from pickem_players where key_hash", {"player_id": "p1", "display_name": "Nate"})
        db_router.when("insert into pickem_picks", None)
        response = client.post("/pickem/pick", json={"key": "pp_x", "game_id": 2026020110, "team": "det"})
        assert response.json() == {"game_id": 2026020110, "pick": "DET"}
        _, params = next((q, p) for q, p in db_router.calls if "insert into pickem_picks" in q.lower())
        assert params == ("p1", 2026020110, "2026-10-15", "DET", "PHI", "DET")

    def test_leaderboard_has_the_model_as_a_benchmark(self, client, db_router):
        db_router.when("group by pl.display_name", [{"display_name": "Nate", "correct": 7, "graded": 10}])
        db_router.when("from game_predictions gp join results", {"correct": 30, "graded": 45})
        body = client.get("/pickem/leaderboard").json()
        assert body == {"players": [{"name": "Nate", "correct": 7, "graded": 10}], "puckpulse": {"correct": 30, "graded": 45}}
