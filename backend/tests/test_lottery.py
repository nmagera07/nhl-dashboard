"""lottery: the NHL draft lottery's exact odds."""

import pytest

import lottery

ORDER = [f"T{i + 1}" for i in range(16)]  # worst first


def test_matches_the_nhls_published_odds_for_the_worst_team():
    worst = lottery.pick_chances(ORDER)["T1"]
    assert worst[0] == pytest.approx(0.255, abs=5e-4)   # its 18.5% share plus the 12th-16th teams' 7.0%
    assert worst[1] == pytest.approx(0.188, abs=5e-4)
    assert worst[2] == pytest.approx(0.557, abs=5e-4)   # never lower than 3rd


def test_every_team_and_every_pick_adds_up():
    chances = lottery.pick_chances(ORDER)
    assert all(sum(p) == pytest.approx(1) for p in chances.values())
    assert all(sum(chances[t][k] for t in ORDER) == pytest.approx(1) for k in range(16))


def test_only_the_11_worst_can_win_first_and_moves_are_capped_at_10():
    chances = lottery.pick_chances(ORDER)
    assert chances["T11"][0] > 0 and chances["T12"][0] == 0
    assert chances["T12"][1] > 0                      # 12th up 10 spots: 2nd
    assert chances["T16"][5] > 0 and sum(chances["T16"][:5]) == 0  # 16th can rise to 6th at most


def test_winning_never_moves_a_team_down():
    # A 12th-16th team wins draw 1, so the worst team keeps No. 1; it then wins draw 2 too.
    order = lottery.final_order(ORDER, "T14", "T1")
    assert order[0] == "T1" and order.index("T14") == 3


def test_needs_16_teams():
    with pytest.raises(ValueError):
        lottery.pick_chances(ORDER[:15])
