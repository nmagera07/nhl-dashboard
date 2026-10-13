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


class TestGoalies:
    def test_parses_gsax_per_60_minute_game(self):
        text = "\n".join([
            "playerId,name,team,position,situation,games_played,icetime,xGoals,goals",
            "1,G A,WPG,G,all,60,216000,170,140",
            "1,G A,WPG,G,5on5,60,180000,120,100",
            "2,G B,WPG,G,all,0,0,0,0",
        ])
        assert pv.season_goalies(text) == {1: {"name": "G A", "team": "WPG", "gp": 60, "games": 60.0, "gsax": 30.0}}

    def test_rates_are_shrunk_hard_toward_average(self):
        hot = {1: {"gp": 60, "games": 60.0, "gsax": 30.0}}  # +0.5 per 60 for a season
        rate = pv.goalie_rates(hot, {})[1]
        assert 0 < rate < 0.5 * 60 / (60 + pv.GOALIE_SHRINK_GAMES) + 1e-9

    def test_team_strength_weights_starts_and_centers_on_the_league(self):
        rates = {1: 0.2, 2: 0.0, 3: -0.1}
        last = {1: {"gp": 60}, 2: {"gp": 20}, 3: {"gp": 40}}
        strength = pv.team_goalie_strength(rates, last, {1: "WPG", 2: "WPG", 3: "PHI", 4: "PHI"})
        wpg = (60 * 0.2 + 20 * 0.0) / 80
        phi = (40 * -0.1 + pv.GOALIE_NEWCOMER_GAMES * pv.GOALIE_REPLACEMENT) / (40 + pv.GOALIE_NEWCOMER_GAMES)
        mean = (wpg + phi) / 2
        assert strength == pytest.approx({"WPG": round(wpg - mean, 4), "PHI": round(phi - mean, 4)})


class TestAging:
    def test_age_is_taken_on_feb_1_of_the_season(self):
        assert pv.age_on_feb1("2000-02-01", 2026) == 27  # birthday on Feb 1 counts
        assert pv.age_on_feb1("2000-02-02", 2026) == 26
        assert pv.age_on_feb1("1987-08-07", 2026) == 39  # Crosby, 2026-27

    def test_young_players_improve_and_veterans_decline(self):
        assert pv.aging_change(20) > pv.aging_change(24) > 0
        assert 0 > pv.aging_change(30) > pv.aging_change(35)
        assert pv.aging_change(45) == pv.aging_change(39) and pv.aging_change(16) == pv.aging_change(19)  # clamped

    def test_team_aging_weights_by_games_and_centers_on_the_league(self):
        last = {1: {"gp": 82}, 2: {"gp": 41}, 3: {"gp": 82}}
        aging = pv.team_aging(last, {1: "YNG", 2: "YNG", 3: "OLD", 4: "OLD"}, {1: 21, 2: 21, 3: 36})
        young = 1.5 * pv.aging_change(21)
        old = pv.aging_change(36)  # player 4 has no age: counts for nothing
        assert aging == pytest.approx({"YNG": round((young - old) / 2, 4), "OLD": round((old - young) / 2, 4)})

    def test_fit_recovers_a_known_curve(self):
        pairs = [(age, 0.01 - 0.002 * (age - 27), 1.0) for age in range(19, 40)]
        coef = pv.fit_aging_curve(pairs, degree=1)
        assert coef == pytest.approx([0.01, -0.002], abs=1e-9)

    def test_pairs_need_both_seasons_and_an_age(self):
        seasons = {2024: {1: {"gp": 40, "gs": 20.0}, 2: {"gp": 40, "gs": 20.0}},
                   2025: {1: {"gp": 40, "gs": 30.0}, 2: {"gp": 10, "gs": 9.0}, 3: {"gp": 40, "gs": 9.0}}}
        assert pv.aging_pairs(seasons, {2025: {1: 24, 2: 24, 3: 24}}) == [(24, 0.25, 40.0)]
