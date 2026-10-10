"""The eval suite's deterministic checks (evals/checks.py). No AI calls."""

import json

from evals.checks import grounded_percentages, mentions_any, percent_near, tool_called

SCENARIO = json.dumps({"baseline": {"playoff_pct": 0.597}, "with_scenario": {"playoff_pct": 0.728, "avg_points": 100.3}})


def test_mentions_any_is_case_insensitive():
    assert mentions_any("The Dallas Stars visit tonight.", ["DAL", "Dallas Stars"]).passed
    assert not mentions_any("They play Chicago.", ["DAL", "Dallas Stars"]).passed


def test_percent_near():
    assert percent_near("Odds rise to 72.8%.", 72.8).passed
    assert percent_near("Odds rise to 73 %.", 72.8).passed           # rounded is fine
    assert not percent_near("Odds rise to 75%.", 72.8).passed
    assert not percent_near("Odds rise a lot.", 72.8).passed


def test_grounded_percentages_accepts_tool_numbers_rounding_and_differences():
    answer = "From 59.7% to 73%, up about 13.1% overall."  # 72.8 rounded; 72.8 - 59.7 = 13.1
    assert grounded_percentages(answer, [SCENARIO]).passed


def test_grounded_percentages_flags_made_up_numbers():
    result = grounded_percentages("Their odds jump to 85%.", [SCENARIO])
    assert not result.passed and "85.0" in result.detail


def test_grounded_percentages_with_no_percentages_passes():
    assert grounded_percentages("They play Dallas tonight.", []).passed


def test_tool_called_checks_name_and_arguments():
    trace = [("simulate_scenario", '{"team":"pit","games":4,"wins":4}', SCENARIO)]
    assert tool_called(trace, "simulate_scenario", {"team": "PIT", "games": 4, "wins": 4}).passed
    assert not tool_called(trace, "simulate_scenario", {"team": "PIT", "games": 5}).passed
    assert tool_called(trace, ("get_game", "simulate_scenario")).passed
    miss = tool_called([], "playoff_path")
    assert not miss.passed and "no tools" in miss.detail


def test_mentions_any_treats_every_dash_alike():
    assert mentions_any("Detroit needs an 8‑2 record.", ["8-2"]).passed  # non-breaking hyphen
    assert mentions_any("Final: 3–2", ["3-2"]).passed                     # en dash
