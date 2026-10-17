"""goal_model: from expected goals to the moneyline, puck line, and total."""

import pytest

import goal_model as gm


def test_final_scores_are_a_distribution_with_no_ties():
    scores = gm.final_scores(3.1, 2.6)
    assert sum(scores.values()) == pytest.approx(1, abs=1e-6)
    assert not any(h == a for h, a in scores)  # overtime/shootout always decides it


def test_com_poisson_keeps_the_mean_and_tightens_the_spread():
    probs = gm.com_poisson(2.8, nu=1.145)
    mean = sum(k * p for k, p in enumerate(probs))
    variance = sum((k - mean) ** 2 * p for k, p in enumerate(probs))
    assert mean == pytest.approx(2.8, abs=1e-3)
    assert variance < 2.8  # less random than Poisson
    assert gm.com_poisson(2.8, nu=1) == pytest.approx(gm.poisson(2.8))


def test_ties_are_weighted_up_as_in_real_hockey():
    plain = gm.regulation_scores(2.8, 2.8, nu=1, shared=0, weights=(1, 1))
    weighted = gm.regulation_scores(2.8, 2.8, nu=1, shared=0, weights=(1.367, 1.09))
    tie = lambda s: sum(p for (h, a), p in s.items() if h == a)  # noqa: E731
    assert tie(weighted) > tie(plain) * 1.25
    assert sum(weighted.values()) == pytest.approx(1)


def test_empty_netters_turn_one_goal_leads_into_two():
    no_en = gm.final_scores(3.4, 2.4, en_goals=(0, 0, 0, 0))
    with_en = gm.final_scores(3.4, 2.4)
    assert gm.home_covers(with_en, -1.5) > gm.home_covers(no_en, -1.5) + 0.05
    assert gm.home_win(with_en) == pytest.approx(gm.home_win(no_en), abs=0.01)  # the winner barely changes


def test_split_reproduces_the_win_probability():
    for p in (0.35, 0.5, 0.66):
        home, away = gm.split_for_win_prob(5.7, p)
        assert home + away == pytest.approx(5.7, abs=1e-3)
        assert gm.home_win(gm.final_scores(home, away)) == pytest.approx(p, abs=1e-3)


def test_better_offenses_raise_the_total_but_only_partly():
    league = 3.0
    average = {"offense": 3.0, "defense": 3.0}
    attack = {"offense": 3.6, "defense": 3.4}
    base = gm.expected_total(average, average, league)
    high = gm.expected_total(attack, attack, league)
    assert high > base
    assert high - base < 0.6 * (2 * 0.6 + 2 * 0.4)  # pulled toward the league's total


def test_tired_teams_score_less():
    team = {"offense": 3.0, "defense": 3.0}
    assert gm.expected_total(team, team, 3.0, home_b2b=True) < gm.expected_total(team, team, 3.0)


def test_bet_probabilities_on_both_sides_of_the_line():
    bets = gm.bet_probabilities(3.3, 2.4, home_spread=-1.5, total_line=6.5)
    underdog = gm.bet_probabilities(2.4, 3.3, home_spread=1.5, total_line=6.5)
    assert 0.35 < bets["home_covers"] < 0.5
    assert underdog["home_covers"] == pytest.approx(1 - bets["home_covers"], abs=0.02)  # roughly symmetric
    assert 0 < bets["over"] < 1
