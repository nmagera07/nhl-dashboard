import pytest

from app import posts
from app.posts import check_post, draft_post, expanded_initials, parse
from app.providers import Provider, ProviderChain
from tests.fakes import fake_factory, tool_call

CANDIDATES = [
    {"id": "swing", "kind": "Swing of the Night", "facts": {"game": "CBJ @ PHI", "scorer": "J. Drysdale", "when": "0:11 left in the 3rd",
                                                           "result": {"winner": "CBJ", "score": "4-3 (OT)"},
                                                           "team_win_chance_before_pct": 1, "team_win_chance_after_pct": 50}},
    {"id": "upset-2026020197", "kind": "Upset", "facts": {"winner_pregame_win_chance_pct": 34, "result": {"winner": "VAN", "score": "6-5 (OT)"}}},
]
SOURCES = str(CANDIDATES)
GOOD = ("PICK: swing\n"
        "X: J. Drysdale tied it with 0:11 left, moving PuckPulse's win probability for PHI from 1% to 50%. CBJ still won 4-3 in OT.\n"
        "REDDIT: J. Drysdale ties it with 11 seconds left, but CBJ wins in OT")
check = check_post({"swing", "upset-2026020197"})


def test_parse_reads_the_three_lines():
    assert parse(GOOD)["pick"] == "swing" and parse(GOOD)["reddit"].endswith("wins in OT")
    assert parse("Here's my pick: swing") is None


class TestCheck:
    def test_a_grounded_draft_passes(self):
        assert check(GOOD, SOURCES) == []

    def test_the_pick_must_be_a_candidate(self):
        assert check(GOOD.replace("PICK: swing", "PICK: odds-FLA"), SOURCES) == ["PICK must be one of: swing, upset-2026020197."]

    def test_length_limits(self):
        long = GOOD.replace("CBJ still won", "CBJ still won " + "x" * posts.X_MAX)
        assert any("X post" in p for p in check(long, SOURCES))

    def test_a_first_name_the_facts_dont_give_is_caught(self):
        guessed = GOOD.replace("X: J. Drysdale", "X: Jamie Drysdale")
        assert any("Jamie Drysdale" in p for p in check(guessed, SOURCES))
        assert check(guessed, SOURCES + " Jamie Drysdale") == []  # found by a tool: fine

    def test_hashtags_tips_and_made_up_numbers(self):
        assert "No hashtags." in check(GOOD.replace("in OT.", "in OT. #NHL"), SOURCES)
        assert any("lock" in p for p in check(GOOD.replace("in OT.", "in OT. CBJ is a lock."), SOURCES))
        assert any("7" in p for p in check(GOOD.replace("in OT.", "in OT, their 7th straight."), SOURCES))


def test_expanded_initials_only_flags_guesses():
    assert expanded_initials("Jamie Drysdale tied it", "J. Drysdale") == ["Jamie Drysdale"]
    assert expanded_initials("J. Drysdale tied it, Jack Hughes too", "J. Drysdale") == []


def chain(turns, calls):
    return ProviderChain([Provider("groq", "Groq", None, "k", "m")], client_factory=fake_factory({"groq": turns}, calls))


class Runner:
    async def run(self, name, arguments):
        return '{"scoring":"J. Drysdale (3) 19:49 3rd"}'


@pytest.mark.asyncio
async def test_the_agent_may_look_up_color_then_drafts():
    calls = []
    turns = ([tool_call("get_game", '{"team":"PHI","opponent":"CBJ"}')], GOOD)
    post, draft = await draft_post(chain(turns, calls), Runner(), "2026-10-27", CANDIDATES)
    assert post["pick"] == "swing" and draft.tools == ['get_game({"team":"PHI","opponent":"CBJ"})']
    assert {t["function"]["name"] for t in calls[0][1]["tools"]} == set(posts.POST_TOOL_NAMES)
    assert '"id":"upset-2026020197"' in calls[0][1]["messages"][1]["content"]


@pytest.mark.asyncio
async def test_no_draft_when_the_rewrite_fails_too():
    post, draft = await draft_post(chain(("PICK: odds-FLA\nX: x\nREDDIT: r", "PICK: odds-FLA\nX: x\nREDDIT: r"), []),
                                   Runner(), "2026-10-27", CANDIDATES)
    assert post is None and draft.problems


HISTORY = [
    {"day": "2026-10-29", "story": "Swing of the Night", "passed_over": ["Upset"], "draft": "Long draft with 7 numbers.",
     "outcome": "edited", "posted": "Short one."},
    {"day": "2026-10-30", "story": "Upset", "draft": "Upset draft.", "outcome": "skipped"},
]


def test_learned_tallies_and_lists_each_day():
    text = posts.learned(HISTORY)
    assert "Posted by kind of story: Swing of the Night 1 of 1; Upset 0 of 1." in text
    assert '- 2026-10-29 Swing of the Night (over Upset): edited. Draft: "Long draft with 7 numbers." Posted: "Short one."' in text
    assert '- 2026-10-30 Upset: skipped. Draft: "Upset draft."' in text
    assert posts.learned([]) == ""


@pytest.mark.asyncio
async def test_history_goes_in_the_instructions_not_the_sources():
    calls = []
    post, draft = await draft_post(chain((GOOD,), calls), Runner(), "2026-10-27", CANDIDATES, HISTORY)
    system, prompt = calls[0][1]["messages"][0]["content"], calls[0][1]["messages"][1]["content"]
    assert "Short one." in system and "Short one." not in prompt
    # A number only in a past post isn't a source for tonight's.
    assert any("7" in p for p in check(GOOD.replace("from 1% to 50%", "from 7% to 50%"), SOURCES))
