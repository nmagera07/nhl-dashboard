"""
Phase 1 -- pure function tests for simulate_playoff_odds.py.

win_probability() and team_ratings() are pure arithmetic; simulate() takes
a seeded random.Random so its results are reproducible.
determine_playoff_teams() only touches its plain-dict/list arguments, so
it's exercised directly with hand-built standings -- no DB, no network.
"""

import random

import pytest

from simulate_playoff_odds import determine_playoff_teams, simulate, team_ratings, win_probability


# ---------------------------------------------------------------------------
# win_probability
# ---------------------------------------------------------------------------


class TestWinProbability:
    def test_evenly_matched_teams_favor_home_ice(self):
        # Equal ratings: only home ice separates them. Calibrated from real
        # games, the home team wins about 54.5%.
        assert win_probability(0.0, 0.0) == pytest.approx(0.5448, abs=1e-3)

    def test_only_the_rating_difference_matters(self):
        assert win_probability(0.5, 0.5) == pytest.approx(win_probability(-0.3, -0.3))

    def test_strong_home_favorite(self):
        # A +1.0 GD/game team hosting a -1.0 team.
        assert win_probability(1.0, -1.0) == pytest.approx(0.823, abs=1e-3)

    def test_strong_away_favorite_despite_home_ice(self):
        assert win_probability(-1.0, 1.0) < 0.25

    def test_result_always_in_unit_interval(self):
        for home, away in [(-5.0, 5.0), (5.0, -5.0), (100.0, 100.0), (-2000.0, 2000.0)]:
            assert 0.0 <= win_probability(home, away) <= 1.0


# ---------------------------------------------------------------------------
# team_ratings
# ---------------------------------------------------------------------------


def _team(gp, gd, **extra):
    return {"games_played": gp, "goal_differential": gd, **extra}


class TestTeamRatings:
    def test_a_hot_start_is_shrunk_toward_the_prior(self):
        # 4-0 with +10 GD is +2.5/game raw; with a 30-game prior at 0.0
        # it rates as +10/34 = +0.29.
        mean, _ = team_ratings({"PIT": _team(4, 10)}, {}, prior_games=30)["PIT"]
        assert mean == pytest.approx(10 / 34)

    def test_the_prior_pulls_toward_last_seasons_strength(self):
        mean, _ = team_ratings({"PIT": _team(0, 0)}, {"PIT": 0.4}, prior_games=30)["PIT"]
        assert mean == pytest.approx(0.4)

    def test_this_seasons_results_dominate_later_in_the_year(self):
        mean, _ = team_ratings({"PIT": _team(70, 70)}, {"PIT": -0.5}, prior_games=30)["PIT"]
        assert mean == pytest.approx((70 - 15) / 100)
        assert mean > 0.5

    def test_uncertainty_shrinks_as_games_are_played(self):
        early = team_ratings({"A": _team(0, 0)}, {}, prior_games=30, talent_sd=0.35)["A"][1]
        late = team_ratings({"A": _team(90, 0)}, {}, prior_games=30, talent_sd=0.35)["A"][1]
        assert early == pytest.approx(0.35)
        assert late == pytest.approx(0.35 * (30 / 120) ** 0.5)


# ---------------------------------------------------------------------------
# simulate
# ---------------------------------------------------------------------------


def _league():
    """4 divisions of 5 teams, 2 per conference: 20 teams, 16 playoff spots."""
    standings = {}
    for div, conf in (("A", "East"), ("B", "East"), ("C", "West"), ("D", "West")):
        for i in range(1, 6):
            standings[f"{div}{i}"] = {
                "points": 0, "wins": 0, "regulation_wins": 0, "row": 0,
                "games_played": 0, "goal_differential": 0, "division": div, "conference": conf,
            }
    return standings


class TestSimulate:
    def test_a_team_that_has_clinched_always_makes_it(self):
        standings = _league()
        standings["A1"]["points"] = 500
        ratings = {t: (0.0, 0.0) for t in standings}
        schedule = [("A2", "A3"), ("B1", "B2")] * 5

        odds = simulate(standings, schedule, 200, ratings, rng=random.Random(1))

        assert odds["A1"] == 1.0
        assert all(0.0 <= p <= 1.0 for p in odds.values())

    def test_probabilities_sum_to_the_number_of_playoff_spots(self):
        standings = _league()
        ratings = {t: (0.0, 0.3) for t in standings}
        schedule = [(h, a) for h in standings for a in standings if h != a]

        odds = simulate(standings, schedule, 300, ratings, rng=random.Random(7))

        # Exactly 16 teams make it in every simulated season (3 per division
        # x 4 + 2 wild cards x 2 conferences), so the odds add up to 16.
        assert sum(odds.values()) == pytest.approx(16)
        assert all(p < 1.0 for p in odds.values())  # nobody's a lock

    def test_a_much_stronger_team_makes_it_more_often(self):
        standings = _league()
        ratings = {t: (0.0, 0.1) for t in standings}
        ratings["A4"] = (1.5, 0.1)
        ratings["A1"] = (-1.5, 0.1)
        schedule = [(h, a) for h in standings for a in standings if h != a]

        odds = simulate(standings, schedule, 300, ratings, rng=random.Random(3))

        assert odds["A4"] > odds["A1"]


# ---------------------------------------------------------------------------
# determine_playoff_teams
# ---------------------------------------------------------------------------


def _standing(points, wins):
    return {"points": points, "wins": wins}


class TestDeterminePlayoffTeams:
    def test_normal_case_top3_per_division_plus_top2_wildcard_per_conference(self):
        # 2 divisions per conference, 5 teams per division -- same shape
        # as the real NHL (3 automatic + 2 wildcard per conference), just
        # smaller so the expected set can be worked out by hand.
        divisions = {
            "A": ["A1", "A2", "A3", "A4", "A5"],
            "B": ["B1", "B2", "B3", "B4", "B5"],
            "C": ["C1", "C2", "C3", "C4", "C5"],
            "D": ["D1", "D2", "D3", "D4", "D5"],
        }
        conferences = {}
        for team in divisions["A"] + divisions["B"]:
            conferences[team] = "East"
        for team in divisions["C"] + divisions["D"]:
            conferences[team] = "West"

        trial_standings = {}
        for prefix, base_points in [("A", 100), ("C", 100)]:
            for i, pts in enumerate([100, 90, 80, 70, 60]):
                trial_standings[f"{prefix}{i + 1}"] = _standing(pts, 40 - i)
        for prefix in ["B", "D"]:
            for i, pts in enumerate([95, 85, 75, 65, 55]):
                trial_standings[f"{prefix}{i + 1}"] = _standing(pts, 38 - i)

        result = determine_playoff_teams(trial_standings, divisions, conferences)

        # Top 3 of each division, plus the top-2 wildcard pool per
        # conference (A4/B4 beat out A5/B5 on points).
        expected = {
            "A1", "A2", "A3", "A4",
            "B1", "B2", "B3", "B4",
            "C1", "C2", "C3", "C4",
            "D1", "D2", "D3", "D4",
        }
        assert result == expected
        assert "A5" not in result and "B5" not in result
        assert len(result) == 16

    def test_three_way_tie_on_points_and_wins_for_two_wildcard_spots(self):
        """
        Locks in the *current* tie-breaking behavior: when teams are tied
        on both points and wins (the only two sort keys used), Python's
        stable sort falls back to whatever order the teams were supplied
        in -- divisions dict order, then each division's own team-list
        order -- not any hockey-specific tiebreaker (head-to-head, ROW,
        etc). Three teams (A4, A5, B4) are deliberately tied 70pts/32wins
        for 2 wildcard spots; A4 and A5 (from division A, processed
        first) win the tie over B4 purely because of input order.
        """
        divisions = {
            "A": ["A1", "A2", "A3", "A4", "A5"],
            "B": ["B1", "B2", "B3", "B4", "B5"],
        }
        conferences = {team: "East" for team in divisions["A"] + divisions["B"]}

        trial_standings = {
            "A1": _standing(100, 40), "A2": _standing(90, 38), "A3": _standing(80, 36),
            "A4": _standing(70, 32), "A5": _standing(70, 32),
            "B1": _standing(95, 37), "B2": _standing(85, 35), "B3": _standing(75, 33),
            "B4": _standing(70, 32), "B5": _standing(60, 28),
        }

        result = determine_playoff_teams(trial_standings, divisions, conferences)

        assert result == {"A1", "A2", "A3", "B1", "B2", "B3", "A4", "A5"}
        assert "B4" not in result

    def test_division_with_fewer_than_three_teams_does_not_crash(self):
        # A 2-team division can't fill 3 automatic spots -- both teams
        # should just qualify with nothing left over for the wildcard pool.
        divisions = {
            "Small": ["S1", "S2"],
            "Big": ["B1", "B2", "B3", "B4"],
        }
        conferences = {"S1": "East", "S2": "East", "B1": "East", "B2": "East", "B3": "East", "B4": "East"}
        trial_standings = {
            "S1": _standing(80, 30), "S2": _standing(70, 28),
            "B1": _standing(100, 40), "B2": _standing(90, 38),
            "B3": _standing(60, 20), "B4": _standing(50, 18),
        }

        result = determine_playoff_teams(trial_standings, divisions, conferences)

        assert {"S1", "S2"} <= result

    def test_single_team_division(self):
        divisions = {"Solo": ["X1"], "Other": ["Y1", "Y2", "Y3", "Y4"]}
        conferences = {"X1": "East", "Y1": "East", "Y2": "East", "Y3": "East", "Y4": "East"}
        trial_standings = {
            "X1": _standing(50, 20),
            "Y1": _standing(100, 40), "Y2": _standing(90, 38),
            "Y3": _standing(80, 36), "Y4": _standing(70, 34),
        }

        result = determine_playoff_teams(trial_standings, divisions, conferences)

        assert "X1" in result

    def test_empty_divisions_returns_empty_set(self):
        assert determine_playoff_teams({}, {}, {}) == set()

    def test_division_with_zero_teams_raises_clear_value_error(self):
        # A division with no teams at all means `divisions` was built
        # wrong upstream (e.g. a bad divisionName) -- this now raises a
        # clear, named ValueError instead of an opaque IndexError from
        # indexing into an empty ranked[0].
        divisions = {"Empty": [], "Normal": ["N1", "N2", "N3"]}
        conferences = {"N1": "East", "N2": "East", "N3": "East"}
        trial_standings = {
            "N1": _standing(100, 40), "N2": _standing(90, 38), "N3": _standing(80, 36),
        }

        with pytest.raises(ValueError, match="Empty"):
            determine_playoff_teams(trial_standings, divisions, conferences)
