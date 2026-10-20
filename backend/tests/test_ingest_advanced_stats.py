"""
ingest_advanced_stats.py: building the advanced stats tables from our
per-game 5-on-5 rows, the NHL's stats API, and goalie xG.
"""

from datetime import date

import pytest

import ingest_advanced_stats as ias
from ingest_advanced_stats import _pdo, current_season_id


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


class TestCurrentSeasonId:
    def test_fall_is_the_season_starting_this_year(self):
        assert current_season_id(date(2026, 10, 20)) == 20262027

    def test_spring_is_the_season_that_started_last_year(self):
        assert current_season_id(date(2027, 3, 1)) == 20262027


class TestTeams:
    def test_season_sums_become_shares_and_pdo(self):
        (pit,) = ias.team_stats([("PIT", 10, 300, 200, 220, 180, 150, 100, 15, 10, 12.5, 7.5)])
        assert pit["games_played"] == 10 and pit["corsi_for_pct"] == 0.6 and pit["fenwick_for_pct"] == 0.55
        assert pit["xgoals_for_pct"] == 0.625 and pit["xgoals_for"] == 12.5 and pit["shots_on_goal_against"] == 100
        assert pit["pdo"] == pytest.approx(100.0)  # 10% shooting, 90% save


class TestSkaters:
    NHL = {8471675: {"gamesPlayed": 10, "timeOnIcePerGame5v5": 900.0, "satFor": 120, "satAgainst": 80,
                     "usatFor": 90, "usatAgainst": 60, "skaterShootingPlusSavePct5v5": 1.025},
           8480000: {"gamesPlayed": 2, "timeOnIcePerGame5v5": 600.0, "satFor": 5, "satAgainst": 5, "usatFor": 4, "usatAgainst": 4},
           8480001: {"gamesPlayed": 0}}

    def test_nhl_shares_with_our_xg(self):
        rows = {r["player_id"]: r for r in ias.skater_stats(self.NHL, {8471675: (3.2, 8.0, 2.0)})}
        crosby = rows[8471675]
        assert crosby["icetime_seconds"] == 9000 and crosby["corsi_for_pct"] == 0.6 and crosby["fenwick_for_pct"] == 0.6
        assert crosby["xgoals_for_pct"] == 0.8 and crosby["individual_xgoals"] == 3.2 and crosby["pdo"] == 102.5
        assert 8480001 not in rows  # no games

    def test_a_skater_without_our_rows_gets_no_xg(self):
        rookie = next(r for r in ias.skater_stats(self.NHL, {}) if r["player_id"] == 8480000)
        assert rookie["xgoals_for_pct"] is None and rookie["individual_xgoals"] is None and rookie["pdo"] is None
        assert rookie["corsi_for_pct"] == 0.5


class TestGoalies:
    def test_nhl_games_and_shots_with_our_xg(self):
        nhl = [{"playerId": 1, "gamesPlayed": 12, "timeOnIce": 43000, "shotsAgainst": 330},
               {"playerId": 2, "gamesPlayed": 1, "timeOnIce": 3600, "shotsAgainst": 20}]
        (g,) = ias.goalie_stats(nhl, {1: (30, 33.5, 40, 9, 11.2)})
        assert g == {"player_id": 1, "games_played": 12, "icetime_seconds": 43000, "shots_faced": 330, "goals_allowed": 30,
                     "xgoals_against": 33.5, "high_danger_shots": 40, "high_danger_goals": 9, "high_danger_xgoals": 11.2}


class CoverageCursor:
    def __init__(self, scored, with_5v5):
        self.counts = [scored, with_5v5]

    def execute(self, sql, params=None):
        pass

    def fetchone(self):
        return (self.counts.pop(0),)


def test_coverage_is_the_share_of_scored_games_with_5v5_rows():
    assert ias.coverage(CoverageCursor(100, 96), 20262027) == 0.96
    assert ias.coverage(CoverageCursor(0, 0), 20262027) == 0.0
