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


NHL_ROW = {"playerId": 8478402, "skaterFullName": "Connor McDavid", "teamAbbrevs": "EDM", "positionCode": "C", "gamesPlayed": 10,
           "goals": 10, "totalPrimaryAssists": 10, "totalSecondaryAssists": 10, "shots": 100, "blockedShots": 20,
           "penaltiesDrawn": 10, "penalties": 10, "totalFaceoffWins": 100, "totalFaceoffLosses": 100,
           "satFor": 200, "satAgainst": 100, "evenStrengthGoalsFor": 10, "evenStrengthGoalsAgainst": 0}


class TestNhlSource:
    def test_the_nhl_reports_give_the_same_game_score(self):
        scores = pv.nhl_game_scores([NHL_ROW, {**NHL_ROW, "playerId": 2, "gamesPlayed": 0}])
        assert scores == {8478402: {"name": "Connor McDavid", "team": "EDM", "pos": "C", "gp": 10, "gs": pytest.approx(35.0)}}

    def test_a_traded_player_counts_for_his_last_team(self):
        assert pv.nhl_game_scores([{**NHL_ROW, "teamAbbrevs": "NYI,COL"}])[8478402]["team"] == "COL"

    def test_missing_report_fields_count_as_zero(self):
        row = {k: NHL_ROW[k] for k in ("playerId", "skaterFullName", "teamAbbrevs", "positionCode", "gamesPlayed", "goals")}
        assert pv.nhl_game_scores([row])[8478402]["gs"] == pytest.approx(7.5)

    def test_fetch_merges_each_report_by_player(self, monkeypatch):
        reports = {"scoringpergame": {"goals": 5}, "penalties": {"penalties": 2}, "faceoffwins": {"totalFaceoffWins": 3},
                   "summaryshooting": {"satFor": 40}, "goalsForAgainst": {"evenStrengthGoalsFor": 4}}
        seen = []

        def get(url, timeout):
            report = url.split("/skater/")[1].split("?")[0]
            seen.append(url)
            return type("R", (), {"raise_for_status": lambda self: None,
                                  "json": lambda self: {"data": [{"playerId": 1, **reports[report]}]}})()
        monkeypatch.setattr(pv.requests, "get", get)
        assert pv.fetch_nhl_skaters(2025) == [{"playerId": 1, "goals": 5, "penalties": 2, "totalFaceoffWins": 3,
                                               "satFor": 40, "evenStrengthGoalsFor": 4}]
        assert all("seasonId=20252026" in u for u in seen) and len(seen) == 5

    def test_calibration_fits_team_goal_differential_on_team_game_score(self):
        skaters = {y: {1: {"team": "AAA", "pos": "C", "gp": 82, "gs": 82 * 1.0},
                       2: {"team": "BBB", "pos": "C", "gp": 82, "gs": 82 * 0.5},
                       3: {"team": "BBB", "pos": "D", "gp": 10, "gs": 1.5}} for y in (2024, 2025)}
        goals = {y: {"AAA": (82 * 0.2, 82), "BBB": (82 * 0.1 + 0.3, 82)} for y in (2024, 2025)}
        fit = pv.calibrate([2024, 2025], skaters=skaters.get, team_goals=goals.get)
        assert fit["team_seasons"] == 4 and fit["replacement_gs"] == {"D": 0.15}
        # Two teams a season, so the fit is the slope between them: GD/gp over Game Score/gp.
        x_aaa, x_bbb = 1.0, (82 * 0.5 + 1.5) / 82
        y_aaa, y_bbb = 0.2, (82 * 0.1 + 0.3) / 82
        assert fit["gs_to_goals"] == round((y_aaa - y_bbb) / (x_aaa - x_bbb), 3) and fit["r"] == 1.0


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


class TestGoalieStarts:
    rates = {1: 0.2, 2: -0.1}
    last = {1: {"gp": 60}, 2: {"gp": 20}}
    rosters = {1: "WPG", 2: "WPG", 3: "PHI"}

    def test_no_starts_yet_matches_last_seasons_split(self):
        without = pv.team_goalie_strength(self.rates, self.last, self.rosters)
        preseason = pv.team_goalie_strength(self.rates, self.last, self.rosters, starts={}, prior_starts=20)
        assert preseason == pytest.approx(without)

    def test_this_seasons_starts_take_over_as_games_are_played(self):
        # The starter is hurt: the backup has started all 30 games.
        early = pv.team_goalie_strength(self.rates, self.last, self.rosters, starts={2: 3}, prior_starts=20)
        late = pv.team_goalie_strength(self.rates, self.last, self.rosters, starts={2: 30}, prior_starts=20)
        assert late["WPG"] < early["WPG"]
        wpg = (15 * 0.2 + (5 + 30) * -0.1) / 50  # 20 * 3/4 for the starter, 20 * 1/4 + 30 for the backup
        phi = pv.GOALIE_REPLACEMENT
        assert late["WPG"] == pytest.approx(round(wpg - (wpg + phi) / 2, 4))


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


class TestRosterStrength:
    def test_sums_values_by_games_and_centers_on_the_league(self):
        values = {1: {"pos": "C", "value": 0.10}, 2: {"pos": "D", "value": 0.05}, 3: {"pos": "C", "value": -0.02}}
        last = {1: {"gp": 82}, 2: {"gp": 41}, 3: {"gp": 82}}
        strength = pv.team_roster_strength(values, last, {1: "AAA", 2: "AAA", 3: "BBB"})
        aaa, bbb = 0.10 + 0.05 * 0.5, -0.02
        assert strength == pytest.approx({"AAA": round(aaa - (aaa + bbb) / 2, 4), "BBB": round(bbb - (aaa + bbb) / 2, 4)})

    def test_more_regulars_than_slots_are_scaled_to_fit(self):
        values = {i: {"pos": "D", "value": 0.06} for i in range(8)}  # 8 full-time D for 6 slots
        last = {i: {"gp": 82} for i in range(8)}
        rosters = {**{i: "DEEP" for i in range(8)}, 99: "NONE"}
        strength = pv.team_roster_strength({**values, 99: {"pos": "C", "value": 0.0}}, {**last, 99: {"gp": 82}}, rosters)
        assert strength["DEEP"] - strength["NONE"] == pytest.approx(6 * 0.06, abs=1e-3)


class TestOurGoalies:
    def test_gsax_is_xg_against_minus_goals_with_nhl_games_and_last_team(self):
        rows = [{"playerId": 1, "goalieFullName": "A", "teamAbbrevs": "ANA,BUF", "gamesPlayed": 24, "timeOnIce": 7200},
                {"playerId": 2, "goalieFullName": "B", "teamAbbrevs": "PIT", "gamesPlayed": 1, "timeOnIce": 0},
                {"playerId": 3, "goalieFullName": "C", "teamAbbrevs": "PIT", "gamesPlayed": 1, "timeOnIce": 600}]
        season = pv.our_season_goalies(rows, {1: (10.0, 8), 2: (1.0, 0)}, scale=1.1)
        assert season == {1: {"name": "A", "team": "BUF", "gp": 24, "games": 2.0, "gsax": pytest.approx(3.0)}}  # 2: no ice time; 3: no shots

    def test_xg_scale_puts_league_goals_over_league_xg(self):
        assert pv.xg_scale({1: (10.0, 11), 2: (10.0, 9)}) == 1.0
        assert pv.xg_scale({1: (8.0, 10)}) == 1.25 and pv.xg_scale({}) == 1.0
