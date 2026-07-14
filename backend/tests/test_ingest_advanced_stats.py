"""
Pure-function tests for ingest_advanced_stats.py -- MoneyPuck CSV row
parsing and the PDO calculation. Values in the "real-shaped" tests below
are the actual PIT (team) and Sidney Crosby (player_id 8471675) 5-on-5
rows fetched from MoneyPuck's real seasonSummary CSV during development,
hand-verified against the raw CSV before this ingestion script existed.
"""

from ingest_advanced_stats import moneypuck_year, parse_skater_row, parse_team_row, _pdo


class TestMoneypuckYear:
    def test_extracts_start_year_from_season_id(self):
        assert moneypuck_year(20252026) == 2025

    def test_older_season(self):
        assert moneypuck_year(20182019) == 2018


class TestPdo:
    def test_average_team_is_close_to_100(self):
        # 10% shooting, 90% save -- textbook "average" split.
        assert _pdo(goals_for=10, shots_for=100, goals_against=10, shots_against=100) == 100.0

    def test_lucky_team_is_above_100(self):
        # Hot shooting AND hot goaltending -- unsustainably good results.
        pdo = _pdo(goals_for=15, shots_for=100, goals_against=5, shots_against=100)
        assert round(pdo, 2) == 110.0  # 15% shooting + 95% save = 110

    def test_zero_shots_for_returns_none_rather_than_dividing_by_zero(self):
        assert _pdo(goals_for=0, shots_for=0, goals_against=5, shots_against=100) is None

    def test_zero_shots_against_returns_none_rather_than_dividing_by_zero(self):
        assert _pdo(goals_for=5, shots_for=100, goals_against=0, shots_against=0) is None


class TestParseTeamRow:
    def test_real_shaped_pit_5on5_row(self):
        # The real PIT 5-on-5 row from moneypuck.com's 2025 teams.csv.
        row = {
            "team": "PIT", "season": "2025", "situation": "5on5", "games_played": "82",
            "xGoalsPercentage": "0.51", "corsiPercentage": "0.5", "fenwickPercentage": "0.51",
            "xGoalsFor": "181.35", "xGoalsAgainst": "174.06",
            "goalsFor": "201.0", "goalsAgainst": "174.0",
            "shotsOnGoalFor": "1807.0", "shotsOnGoalAgainst": "1751.0",
        }

        parsed = parse_team_row(row)

        assert parsed["team_abbrev"] == "PIT"
        assert parsed["games_played"] == 82
        assert parsed["corsi_for_pct"] == 0.5
        assert parsed["fenwick_for_pct"] == 0.51
        assert parsed["xgoals_for_pct"] == 0.51
        assert parsed["xgoals_for"] == 181.35
        assert parsed["xgoals_against"] == 174.06
        assert parsed["goals_for"] == 201
        assert parsed["goals_against"] == 174
        assert parsed["shots_on_goal_for"] == 1807
        assert parsed["shots_on_goal_against"] == 1751
        assert round(parsed["pdo"], 2) == 101.19


class TestParseSkaterRow:
    def test_real_shaped_crosby_5on5_row(self):
        # The real Sidney Crosby (playerId 8471675) 5-on-5 row from
        # moneypuck.com's 2025 skaters.csv.
        row = {
            "playerId": "8471675", "season": "2025", "situation": "5on5", "games_played": "68",
            "icetime": "61928.0",
            "onIce_corsiPercentage": "0.5", "onIce_fenwickPercentage": "0.51",
            "onIce_xGoalsPercentage": "0.5",
            "OnIce_F_xGoals": "45.78", "OnIce_A_xGoals": "46.48",
            "I_F_xGoals": "10.75",
            "OnIce_F_goals": "44.0", "OnIce_F_shotsOnGoal": "437.0",
            "OnIce_A_goals": "45.0", "OnIce_A_shotsOnGoal": "451.0",
        }

        parsed = parse_skater_row(row)

        assert parsed["player_id"] == 8471675
        assert parsed["games_played"] == 68
        assert parsed["icetime_seconds"] == 61928
        assert parsed["corsi_for_pct"] == 0.5
        assert parsed["fenwick_for_pct"] == 0.51
        assert parsed["xgoals_for_pct"] == 0.5
        assert parsed["xgoals_for"] == 45.78
        assert parsed["xgoals_against"] == 46.48
        assert parsed["individual_xgoals"] == 10.75
        assert parsed["pdo"] is not None

    def test_missing_onice_shot_counts_yields_none_pdo_not_a_crash(self):
        # A call-up with almost no 5v5 icetime can have on-ice shot counts
        # of literally 0 -- parse_skater_row must not blow up on that.
        row = {
            "playerId": "8500000", "season": "2025", "situation": "5on5", "games_played": "1",
            "icetime": "45.0",
            "onIce_corsiPercentage": "0.4", "onIce_fenwickPercentage": "0.4",
            "onIce_xGoalsPercentage": "0.4",
            "OnIce_F_xGoals": "0.02", "OnIce_A_xGoals": "0.03",
            "I_F_xGoals": "0.01",
            "OnIce_F_goals": "0.0", "OnIce_F_shotsOnGoal": "0.0",
            "OnIce_A_goals": "0.0", "OnIce_A_shotsOnGoal": "0.0",
        }

        parsed = parse_skater_row(row)

        assert parsed["pdo"] is None
