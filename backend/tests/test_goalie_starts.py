"""goalie_starts: projected starting goalies."""

from datetime import date

import pytest

import goalie_starts as gs


def test_the_goalie_who_has_been_starting_is_favored():
    probs = gs.start_probabilities({"A", "B"}, ["A", "A", "B", "A", "A"], {})
    assert probs["A"] > 0.7 and probs["A"] + probs["B"] == pytest.approx(1)


def test_recent_starts_count_more_than_old_ones():
    probs = gs.start_probabilities({"A", "B"}, ["A"] * 6 + ["B"] * 6, {})
    assert probs["B"] > probs["A"]  # B took over


def test_the_second_night_of_a_back_to_back_goes_to_the_other_goalie():
    probs = gs.start_probabilities({"A", "B"}, ["A", "A", "A", "B", "A"], {}, started_last_night="A")
    assert probs["B"] > 0.75


def test_last_seasons_split_only_matters_before_starts_pile_up():
    early = gs.start_probabilities({"A", "B"}, [], {"A": 0.7, "B": 0.3})
    assert early["A"] > early["B"]
    later = gs.start_probabilities({"A", "B"}, ["B"] * 5, {"A": 0.7, "B": 0.3})
    assert later["B"] > 0.8


def test_a_call_up_with_no_starts_still_gets_a_small_chance():
    probs = gs.start_probabilities({"A", "B", "C"}, ["A", "B", "A"], {})
    assert 0 < probs["C"] < 0.15


class FakeCursor:
    def __init__(self, history):
        self.history = history

    def execute(self, sql, params=None):
        pass

    def fetchall(self):
        return self.history


def test_team_projection_uses_the_current_roster_and_last_night():
    roster = {"goalies": [{"id": 1, "firstName": {"default": "Arturs"}, "lastName": {"default": "Silovs"}},
                          {"id": 2, "firstName": {"default": "Sergei"}, "lastName": {"default": "Murashov"}}]}

    def get(url):
        return roster if "/roster/" in url else {"goalies": [{"playerId": 1, "gamesStarted": 50}, {"playerId": 9, "gamesStarted": 32}]}

    history = [(date(2026, 10, 14), 1), (date(2026, 10, 16), 1), (date(2026, 10, 17), 1)]
    rows = gs.team_projection(FakeCursor(history), "PIT", 20262027, date(2026, 10, 18), get=get)
    assert [r[1] for r in rows] == ["Sergei Murashov", "Arturs Silovs"]  # Silovs started last night
    assert sum(r[2] for r in rows) == pytest.approx(1, abs=0.002)
    assert all(r[0] != 9 for r in rows)  # last season's goalie who left isn't a candidate
