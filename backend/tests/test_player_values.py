"""player_values: skater worth in goals/game over replacement."""

import pytest

import player_values as pv

HEADER = ("playerId,name,team,position,situation,games_played,I_F_goals,I_F_primaryAssists,I_F_secondaryAssists,"
          "I_F_shotsOnGoal,shotsBlockedByPlayer,penaltiesDrawn,penalties,faceoffsWon,faceoffsLost,"
          "OnIce_F_shotAttempts,OnIce_A_shotAttempts,OnIce_F_goals,OnIce_A_goals")


def _csv(*rows):
    return "\n".join([HEADER, *rows])


class TestGameScore:
    def test_weights(self):
        all_row = {"I_F_goals": 10, "I_F_primaryAssists": 10, "I_F_secondaryAssists": 10, "I_F_shotsOnGoal": 100,
                   "shotsBlockedByPlayer": 20, "penaltiesDrawn": 10, "penalties": 10, "faceoffsWon": 100, "faceoffsLost": 100}
        ev_row = {"OnIce_F_shotAttempts": 200, "OnIce_A_shotAttempts": 100, "OnIce_F_goals": 10, "OnIce_A_goals": 0}

        # 7.5 + 7 + 5.5 + 7.5 + 1 (penalties and faceoffs net to 0) + 5 + 1.5
        assert pv.game_score(all_row, ev_row) == pytest.approx(35.0)

    def test_parses_both_situations_and_skips_players_without_games(self):
        text = _csv(
            "1,A B,DET,C,all,10,5,0,0,0,0,0,0,0,0,0,0,0,0",
            "1,A B,DET,C,5on5,10,0,0,0,0,0,0,0,0,0,0,0,0,0",
            "2,C D,DET,D,all,0,0,0,0,0,0,0,0,0,0,0,0,0,0",
            "2,C D,DET,D,5on5,0,0,0,0,0,0,0,0,0,0,0,0,0,0",
        )
        assert pv.season_game_scores(text) == {1: {"name": "A B", "team": "DET", "pos": "C", "gp": 10, "gs": 3.75}}


class TestPlayerValues:
    def test_a_replacement_level_player_is_worth_zero(self):
        repl = pv.REPLACEMENT_GS["F"]
        values = pv.player_values({1: {"name": "X", "team": "DET", "pos": "C", "gp": 80, "gs": 80 * repl}}, {})
        assert values[1]["value"] == pytest.approx(0, abs=1e-4)

    def test_a_hot_start_is_pulled_toward_replacement(self):
        hot = {"name": "X", "team": "DET", "pos": "C", "gp": 5, "gs": 10.0}  # 2.0 per game, MacKinnon would be ~1.9
        value = pv.player_values({1: hot}, {})[1]["value"]
        assert 0 < value < pv.GS_TO_GOALS * (2.0 - pv.REPLACEMENT_GS["F"]) / 2

    def test_blends_this_season_with_last(self):
        cur = {1: {"name": "X", "team": "DET", "pos": "C", "gp": 10, "gs": 5.0}}
        prev = {1: {"name": "X", "team": "DET", "pos": "C", "gp": 80, "gs": 80.0}}
        with_history = pv.player_values(cur, prev)[1]
        assert with_history["value"] > pv.player_values(cur, {})[1]["value"]
        assert (with_history["gp"], with_history["gp_last_season"]) == (10, 80)

    def test_rosters_set_the_team_and_drop_players_not_on_one(self):
        prev = {1: {"name": "Moved", "team": "DET", "pos": "D", "gp": 82, "gs": 40.0},
                2: {"name": "Retired", "team": "DET", "pos": "C", "gp": 82, "gs": 40.0}}
        values = pv.player_values({}, prev, rosters={1: "TOR"})
        assert list(values) == [1] and values[1]["team"] == "TOR"


class TestRosterStrengthChange:
    def _p(self, team, gp=82, gs=82.0, pos="C"):
        return {"name": "X", "team": team, "pos": pos, "gp": gp, "gs": gs}

    def test_a_move_costs_one_team_what_the_other_gains(self):
        last = {1: self._p("DET"), 2: self._p("DET")}
        change = pv.roster_strength_change(last, {}, rosters={1: "TOR", 2: "DET"})
        value = pv.player_values(last, {})[1]["value"]
        assert change == pytest.approx({"DET": -value, "TOR": value})

    def test_departures_count_and_part_timers_count_less(self):
        last = {1: self._p("DET"), 2: self._p("BOS", gp=41, gs=41.0)}
        change = pv.roster_strength_change(last, {}, rosters={})
        values = pv.player_values(last, {})
        assert change == pytest.approx({"DET": -values[1]["value"], "BOS": -values[2]["value"] * 41 / 82})

    def test_a_relocated_franchise_keeps_its_roster(self):
        last = {1: self._p("ARI")}
        assert pv.roster_strength_change(last, {}, rosters={1: "UTA"}) == {}
        # ...but not in a season when the old team still exists
        assert set(pv.roster_strength_change(last, {}, rosters={1: "ARI", 2: "UTA"})) == set()
