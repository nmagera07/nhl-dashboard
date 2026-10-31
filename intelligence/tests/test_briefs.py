import json

import pytest

from app import briefs
from app.briefs import Game, check_brief, write_brief
from app.providers import AllProvidersFailed, Provider, ProviderChain
from tests.fakes import fake_factory, rate_limited, tool_call

SOURCES = ('{"moneyline":{"CGY":{"best_price":"+180","puckpulse_fair_price":"+188","puckpulse_chance_pct":34.7},'
           '"EDM":{"best_price":"-210","puckpulse_fair_price":"-188","puckpulse_chance_pct":65.2}},'
           '"recent":[{"date":"2026-10-26","opponent":"DET","score":"3-4","decided_in":"SO"}]}')
GOOD = """- Tristan Jarry is confirmed in goal for EDM.
- EDM is -210 at the best book, with a fair price of -188 (a 65% chance).
- EDM lost 4-3 in a shootout to DET on Oct. 26."""
GAME = Game(2026020200, "CGY", "EDM", "2026-10-28")


class TestCheck:
    def test_a_brief_built_from_the_results_passes(self):
        assert check_brief(GOOD, SOURCES) == []

    def test_a_number_not_in_the_results_is_caught(self):
        problems = check_brief("- EDM has won 7 straight at home.", SOURCES)
        assert problems and "7" in problems[0]

    def test_odds_must_match_exactly_sign_included(self):
        assert check_brief("- CGY is +180 at the best book.", SOURCES) == []
        assert check_brief("- CGY is -180 at the best book.", SOURCES)  # wrong side of the line
        assert check_brief("- CGY is +185 at the best book.", SOURCES)

    def test_rounding_a_result_is_fine_but_changing_it_isnt(self):
        assert check_brief("- CGY has a 35% chance.", SOURCES) == []  # 34.7, rounded
        assert check_brief("- CGY has a 34.7% chance.", SOURCES) == []
        assert check_brief("- CGY has a 36% chance.", SOURCES)

    def test_betting_tip_wording_is_caught(self):
        problems = check_brief("- EDM at -210 is a lock.", SOURCES)
        assert problems == ["Remove betting-tip wording: lock."]

    def test_spelled_out_counts_are_caught(self):
        problems = check_brief("- CGY has won four straight.", SOURCES)
        assert problems and "four" in problems[0]

    def test_shape_three_bullets_and_nothing_else(self):
        assert check_brief("Here's the brief:\n" + GOOD, SOURCES)
        assert check_brief(GOOD + "\n- CGY is +180.", SOURCES) == ["Use at most 3 bullets (there are 4)."]


class FakeRunner:
    def __init__(self):
        self.calls = []

    async def run(self, name, arguments):
        self.calls.append((name, json.loads(arguments)))
        return SOURCES


def chain(turns, calls):
    return ProviderChain([Provider("groq", "Groq", None, "k", "m")], client_factory=fake_factory({"groq": turns}, calls))


@pytest.mark.asyncio
async def test_the_agent_researches_then_writes():
    calls, runner = [], FakeRunner()
    turns = ([tool_call("get_bets", '{"team":"EDM"}'), tool_call("get_lineup", '{"team":"EDM"}', "call_2")], GOOD)

    brief = await write_brief(chain(turns, calls), runner, GAME, "Wednesday, October 28, 2026")

    assert brief.text == GOOD and brief.model == "Groq" and brief.problems == [] and brief.first_problems == []
    assert runner.calls == [("get_bets", {"team": "EDM"}), ("get_lineup", {"team": "EDM"})]
    assert brief.tools == ['get_bets({"team":"EDM"})', 'get_lineup({"team":"EDM"})']
    offered = {t["function"]["name"] for t in calls[0][1]["tools"]}
    assert offered == set(briefs.BRIEF_TOOL_NAMES)  # research tools only, no simulations
    assert "CGY @ EDM on 2026-10-28" in calls[0][1]["messages"][1]["content"]


@pytest.mark.asyncio
async def test_a_made_up_number_gets_one_rewrite_without_more_tools():
    calls = []
    turns = ([tool_call("get_bets", '{"team":"EDM"}')], "- EDM has won 7 straight.", GOOD)

    brief = await write_brief(chain(turns, calls), FakeRunner(), GAME, "today")

    assert brief.text == GOOD
    assert brief.first_problems == ["These numbers aren't in the tool results: 7. Use only numbers from the results, as given."]
    rewrite = calls[2][1]
    assert "tools" not in rewrite
    assert "7" in rewrite["messages"][-1]["content"]  # told exactly what was wrong


@pytest.mark.asyncio
async def test_no_brief_when_the_rewrite_fails_too():
    turns = ([tool_call("get_bets", '{"team":"EDM"}')], "- EDM has won 7 straight.", "- EDM is a lock.")

    brief = await write_brief(chain(turns, []), FakeRunner(), GAME, "today")

    assert brief.text is None and brief.problems == ["Remove betting-tip wording: lock."]


@pytest.mark.asyncio
async def test_research_stops_after_the_round_limit():
    calls = []
    turns = tuple([tool_call("get_bets", '{"team":"EDM"}')] for _ in range(briefs.MAX_BRIEF_ROUNDS)) + (GOOD,)

    brief = await write_brief(chain(turns, calls), FakeRunner(), GAME, "today")

    assert brief.text == GOOD
    assert "tools" not in calls[-1][1] and "no more tools" in calls[-1][1]["messages"][-1]["content"]


@pytest.mark.asyncio
async def test_busy_providers_raise():
    with pytest.raises(AllProvidersFailed):
        await write_brief(chain(rate_limited(), []), FakeRunner(), GAME, "today")


def test_scores_low_number_first_and_tallied_records_are_caught():
    sources = SOURCES + '{"score":"1-5"}{"score":"2-3"}'
    problems = check_brief("- WPG enters on a 1-5 loss to FLA.", sources)
    assert problems == ["Write scores with the higher number first (1-5); drop any win-loss record you counted yourself."]
    assert check_brief("- OTT is 2-3 in recent games.", sources)
    assert check_brief("- WPG lost 5-1 to FLA, and CGY is +180.", sources) == []
    assert check_brief("- EDM was 4-3 on Oct. 26 and is -210.", SOURCES) == []  # odds aren't scores


GOALIES = ('{"starting_goalie":"Ukko-Pekka Luukkonen: projected by NHL.com\'s lineup"}'
           '{"goalies":{"home":"Darcy Kuemper: confirmed by beat reporters (via RotoWire)"}}')
NO_VALUE = '{"value_flags":"None right now: no price beats PuckPulse\'s fair odds by enough."}'


def test_value_talk_is_caught_when_the_results_say_there_is_none():
    # Groq, 10-31 evals: "showing slight extra value on the Sharks" with no value on the board.
    problems = check_brief("- SJS shows slight extra value tonight.", SOURCES + NO_VALUE)
    assert problems == ["The results say no price is value tonight; don't call anything value or an edge."]
    assert check_brief("- PuckPulse sees no value on either side.", SOURCES + NO_VALUE) == []
    assert check_brief("- CGY at +180 is value.", SOURCES) == []  # a board with value flagged


def test_only_a_confirmed_goalie_can_be_called_confirmed():
    sources = SOURCES + GOALIES
    problems = check_brief("- Ukko-Pekka Luukkonen and Darcy Kuemper are confirmed starters.", sources)
    assert problems == ["Only call a goalie confirmed if the results say so; Ukko-Pekka Luukkonen isn't confirmed "
                        "(say expected or projected, as the results do)."]
    assert check_brief("- Kuemper is confirmed for LAK, while Luukkonen is projected for BUF.", sources) == []
    assert check_brief("- Luukkonen starts against Kuemper, with both confirmed by beat reporters.", sources)
