"""
Phase 1 -- pure function tests for simulate_playoff_odds.py.

win_probability() is pure arithmetic, no mocking needed.
determine_playoff_teams() only touches its plain-dict/list arguments, so
it's exercised directly with hand-built standings -- no DB, no network.
"""

import pytest

from simulate_playoff_odds import win_probability, determine_playoff_teams


# ---------------------------------------------------------------------------
# win_probability
# ---------------------------------------------------------------------------


class TestWinProbability:
    def test_evenly_matched_teams_favor_home_ice(self):
        # Equal point pctgs -- only the home-ice bump should separate them,
        # so the home team is a slight favorite, not a 50/50 coin flip.
        assert win_probability(0.5, 0.5) == pytest.approx(0.5230095872975623)
        assert win_probability(0.5, 0.5) > 0.5

    def test_strong_home_favorite(self):
        assert win_probability(0.700, 0.300) == pytest.approx(0.8737104209450813)

    def test_strong_away_favorite_despite_home_ice(self):
        # Home ice alone (a flat +0.02) isn't enough to flip a lopsided
        # matchup in the home team's favor.
        assert win_probability(0.300, 0.700) == pytest.approx(0.14805165414742627)

    def test_symmetric_inputs_always_land_on_the_same_value(self):
        # The formula only depends on the *difference* between the two
        # pctgs (plus the fixed home-ice bump), so any two equal inputs --
        # including the boundary 0.0/0.0 -- should produce the identical
        # probability as any other equal pair.
        assert win_probability(0.0, 0.0) == pytest.approx(win_probability(0.5, 0.5))
        assert win_probability(0.55, 0.55) == pytest.approx(win_probability(0.5, 0.5))

    def test_boundary_extreme_point_pctgs(self):
        # point_pctg is bounded to [0, 1] by construction (points / (games*2)),
        # so a perfect team at home vs. a winless team away is the most
        # lopsided real input this function will ever see.
        assert win_probability(1.0, 0.0) == pytest.approx(0.9909623162617605)
        assert win_probability(0.0, 1.0) == pytest.approx(0.010845859477081325)

    def test_result_always_in_unit_interval(self):
        # A logistic function should never escape [0, 1], even for inputs
        # well outside the normal 0-1 point-pctg range (never produced by
        # fetch_standings_as_of() in practice, but the function itself
        # does no input validation).
        for home, away in [(-5.0, 5.0), (5.0, -5.0), (100.0, 100.0)]:
            p = win_probability(home, away)
            assert 0.0 <= p <= 1.0

    def test_extreme_favorite_saturates_to_exactly_1(self):
        # Discovered edge case, confirmed empirically (not assumed): for a
        # large enough point-pctg gap, 10**(-diff*scale) underflows to a
        # value so small that 1 + that value rounds to exactly 1.0 at
        # float64 precision -- so the result isn't just "very close to"
        # 1, it IS exactly 1.0. This is a one-way asymmetry, not
        # symmetric saturation: the mirror-image extreme underdog case
        # (see below) stays a tiny nonzero float instead of flooring to
        # 0.0, because float64 has vastly more precision near 0 than it
        # does near 1 (a value 1e-20 away from 1.0 is indistinguishable
        # from 1.0, but a value 1e-20 away from 0.0 is still representable
        # just fine). Worth knowing since a caller computing the away
        # team's odds as 1 - win_probability(...) would silently get
        # exactly 0.0 here, not "extremely unlikely."
        assert win_probability(5.0, -5.0) == 1.0

    def test_extreme_underdog_stays_a_tiny_nonzero_float(self):
        result = win_probability(-5.0, 5.0)
        assert result != 0.0
        assert result == pytest.approx(1.0964781961431828e-20)


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
