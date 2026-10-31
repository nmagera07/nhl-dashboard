"""The eval suite's deterministic checks (evals/checks.py). No AI calls."""

import json

import pytest

from evals.checks import grounded_percentages, mentions_any, percent_near, score_mentioned, tool_called

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


def test_score_mentioned_accepts_dashes_or_words():
    assert score_mentioned("Lost 3\u20132 in a shootout.", 2, 3).passed
    assert score_mentioned("Pittsburgh scored 2 goals while Columbus scored 3.", 2, 3).passed
    assert not score_mentioned("Pittsburgh lost a close one, 4-1 in shots.", 2, 3).passed
    assert not score_mentioned("Their odds fell 2% to 3%.", 2, 3).passed  # percentages aren't scores


# Agent checks, on sentences from real stored briefs (10-29 and 10-30).
from evals.agents import FixedLookups  # noqa: E402
from evals.checks import (action_matches, back_to_back, bet_prices, goalie_status, goalies_named,  # noqa: E402
                          odds_on_team, team_aliases)
from evals.investigator_cases import CASES  # noqa: E402

ALIASES = team_aliases([
    {"team_abbrev": "WPG", "team_name": "Winnipeg Jets", "common_name": "Jets"},
    {"team_abbrev": "FLA", "team_name": "Florida Panthers", "common_name": "Panthers"},
    {"team_abbrev": "MTL", "team_name": "Montréal Canadiens", "common_name": "Canadiens"},
    {"team_abbrev": "DAL", "team_name": "Dallas Stars", "common_name": "Stars"},
    {"team_abbrev": "SEA", "team_name": "Seattle Kraken", "common_name": "Kraken"},
    {"team_abbrev": "STL", "team_name": "St. Louis Blues", "common_name": "Blues"},
])
BETS = json.dumps({"games": [{"game": "MTL @ DAL",
                              "moneyline": {"MTL": {"best_price": "+142", "puckpulse_fair_price": "+139"},
                                            "DAL": {"best_price": "-162", "puckpulse_fair_price": "-139"}},
                              "puck_line": {"MTL +1.5": {"best_price": "-175"}, "DAL -1.5": {"best_price": "+150"}}}]})


def test_aliases_cover_city_nickname_and_unaccented_names():
    assert {"Montréal", "Montreal", "Canadiens", "Montréal Canadiens"} <= set(ALIASES["MTL"])


def test_goalie_status_fails_only_an_overclaimed_starter():
    starters = {"Jake Oettinger": "confirmed", "Jakub Dobes": "projected"}
    assert goalie_status("- Jake Oettinger is confirmed in goal for DAL, while Jakub Dobes is projected for MTL.",
                         starters).passed
    wrong = goalie_status("- Jakub Dobes is confirmed for MTL.", starters)
    assert not wrong.passed and "Dobes called confirmed, really projected" in wrong.detail
    undersold = goalie_status("- SEA starts projected goalie Philipp Grubauer.", {"Philipp Grubauer": "confirmed"})
    assert undersold.passed and "really confirmed" in undersold.detail


def test_goalies_named():
    assert goalies_named("- Oettinger starts.", {"Jake Oettinger": "confirmed"}).passed
    assert not goalies_named("- DAL is favored.", {"Jake Oettinger": "confirmed"}).passed


def test_back_to_back_must_name_a_team_on_one():
    text = "- Winnipeg plays the second night of a back-to-back following a 6-4 loss to Tampa Bay last night."
    assert back_to_back(text, {"WPG"}, ALIASES).passed
    assert not back_to_back(text, {"FLA"}, ALIASES).passed
    assert back_to_back("- FLA is favored.", set(), ALIASES).passed


def test_odds_must_belong_to_the_team_in_their_clause():
    prices = bet_prices([BETS, "not json"])
    assert prices["MTL"] == {"+142", "+139", "-175"}
    right = ("- DAL is favored at -162 on DraftKings against MTL at +142 on FanDuel, "
             "with PuckPulse's fair price at -139 for DAL and +139 for MTL.")
    assert odds_on_team(right, prices, ALIASES).passed
    assert odds_on_team("- Dallas is -162, with a fair price of -139.", prices, ALIASES).passed  # carried over
    stl = {"STL": {"-109", "+104"}, "DAL": {"-162"}}
    assert odds_on_team("- Dallas -162 on Oct. 29; St. Louis -109 versus a fair +104.", stl, ALIASES).passed
    wrong = odds_on_team("- Montreal is -162 tonight.", prices, ALIASES)
    assert not wrong.passed and "-162 for MTL" in wrong.detail


def test_action_line():
    assert action_matches("Shift chart late.\nAction: none, it fixes itself on the next run.", "none").passed
    assert not action_matches("Result missing.\nAction: none.", "investigate").passed
    assert action_matches("Result missing.\nAction: check the job's logs.", "investigate").passed
    assert action_matches("WAR stale.\nAction: look at war.py in the job's logs.", "war.py").passed
    assert not action_matches("WAR stale.", "war.py").passed


@pytest.mark.asyncio
async def test_fixed_lookups_answer_from_fixtures_and_record_calls():
    case = next(c for c in CASES if c.id == "postponed")
    lookups = FixedLookups(case.lookups)
    assert json.loads(await lookups.run("nhl_game_status", '{"game_id": 2026020216}'))["status"] == "postponed"
    assert "error" in json.loads(await lookups.run("nhl_shift_data", '{"game_id": 2026020216}'))
    assert lookups.calls == [("nhl_game_status", "2026020216"), ("nhl_shift_data", "2026020216")]
    assert all(set(c.must_call) <= set(c.lookups) for c in CASES)  # every required lookup has an answer
