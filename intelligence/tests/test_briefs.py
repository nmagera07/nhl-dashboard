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

    assert brief.text == GOOD and brief.model == "Groq" and brief.problems == []
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
