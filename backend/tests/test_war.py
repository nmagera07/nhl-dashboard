"""war.py (wins above replacement) and the WAR in the player API."""

import pytest

import player_values as pv
import war


def test_skaters_are_game_score_above_replacement_in_wins():
    skaters = {1: {"name": "Star", "team": "EDM", "pos": "C", "gp": 10, "gs": 15.0},
               2: {"name": "Fringe", "team": "SJS", "pos": "D", "gp": 10, "gs": 10 * pv.REPLACEMENT_GS["D"]}}
    out = war.skater_war(skaters, gs_to_goals=0.2, goals_per_win=6.0)
    expected_gar = 0.2 * (15.0 - 10 * pv.REPLACEMENT_GS["F"])
    assert out[1]["gar"] == pytest.approx(expected_gar, abs=0.01)
    assert out[1]["war"] == pytest.approx(expected_gar / 6.0, abs=0.01)
    assert out[2]["war"] == 0  # exactly replacement level


def test_goalies_get_saves_above_expected_plus_the_replacement_gap():
    goalies = {3: {"name": "Wall", "team": "BOS", "gp": 20, "games": 19.5, "gsax": 10.0}}
    out = war.goalie_war(goalies, replacement=-0.2, goals_per_win=6.0)
    assert out[3]["gar"] == pytest.approx(10.0 + 0.2 * 19.5, abs=0.01)
    assert out[3]["pos"] == "G"


def test_goals_per_win_is_the_inverse_slope_of_wins_on_goal_differential():
    # Every 6 goals of differential is one more win, exactly.
    records = {2025: {f"T{i}": (41 + i, 6 * i, 82) for i in range(-5, 6)}}
    gpw, r = war.fit_goals_per_win(records)
    assert gpw == pytest.approx(6.0, abs=0.01) and r == pytest.approx(1.0)


def test_store_replaces_the_season():
    class Cur:
        def __init__(self):
            self.sql = []

        def execute(self, sql, params=None):
            self.sql.append((" ".join(sql.split()), params))

    cur = Cur()
    war.store(cur, 20262027, {1: {"name": "Star", "team": "EDM", "pos": "C", "gp": 9, "gar": 4.75, "war": 0.77},
                              3: {"name": "Wall", "team": "BOS", "pos": "G", "gp": 5, "gar": 6.1, "war": 0.99}}, "2026-10-22")
    assert cur.sql[1] == ("DELETE FROM player_war WHERE season_id = %s", (20262027,))  # after CREATE TABLE
    inserts = [params for sql, params in cur.sql if sql.startswith("INSERT")]
    assert [p[4] for p in inserts] == ["F", "G"]
    assert inserts[0][9:] == (None,) * 6  # v1-shaped rows store no parts


class TestApi:
    def test_leaders_by_position(self, client, db_router):
        db_router.when("from player_war where season_id", [
            {"player_id": 8478402, "name": "Connor McDavid", "team_abbrev": "EDM", "position_group": "F",
             "games_played": 9, "gar": 4.75, "war": 0.77}])
        body = client.get("/players/war?position=F&limit=5").json()
        assert body["players"][0]["war"] == 0.77
        assert client.get("/players/war?position=X").status_code == 422

    def test_player_page_gets_war_and_rank(self, client, db_router, player_bio_row):
        db_router.when("from player_war where season_id", {"player_id": 8478402, "war": 0.77, "gar": 4.75,
                                                           "games_played": 9, "position_group": "F", "rank": 1, "of": 459})
        db_router.when("p.player_id = %s", player_bio_row)
        db_router.when("from player_season_stats", [])
        db_router.when("from player_advanced_stats", None)
        db_router.when("from player_career_totals", [])
        db_router.when("from player_season_history", [])
        body = client.get(f"/players/{player_bio_row['player_id']}").json()
        assert body["war"] == {"war": 0.77, "gar": 4.75, "games_played": 9, "group": "forwards", "rank": 1, "of": 459}

    def test_skaters_get_the_v2_parts_once_stored(self, client, db_router, player_bio_row):
        parts = {"ev_offense": 3.1, "ev_defense": -0.4, "finishing": 1.2, "power_play": 0.5, "penalty_kill": None,
                 "penalties": 0.3}
        db_router.when("from player_war where season_id", {"player_id": 8478402, "war": 0.77, "gar": 4.75, **parts,
                                                           "games_played": 9, "position_group": "F", "rank": 1, "of": 459})
        db_router.when("p.player_id = %s", player_bio_row)
        db_router.when("from player_season_stats", [])
        db_router.when("from player_advanced_stats", None)
        db_router.when("from player_career_totals", [])
        db_router.when("from player_season_history", [])
        body = client.get(f"/players/{player_bio_row['player_id']}").json()
        assert body["war"]["parts"] == {**parts, "penalty_kill": 0.0}
