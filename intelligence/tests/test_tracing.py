"""Tracing (app/tracing.py): what lands in a trace, and that it can never break an answer."""

import json

import pytest

from app import tracing
from app.config import Settings
from app.main import ChatContext, ChatRequest, IntelligenceService
from app.providers import Provider, ProviderChain
from app.research import research_and_write
from tests.fakes import fake_factory, rate_limited, tool_call

GEMINI = Provider("gemini", "Google Gemini", None, "k", "gemini-flash-lite-latest")
GROQ = Provider("groq", "Groq", None, "k", "openai/gpt-oss-120b")


class FakeObservation:
    """Records what the code tells Langfuse, as a tree."""

    def __init__(self, name, as_type, **fields):
        self.name, self.as_type, self.fields = name, as_type, dict(fields)
        self.children, self.ended = [], 0

    def start_observation(self, *, name, as_type="span", **fields):
        child = FakeObservation(name, as_type, **fields)
        self.children.append(child)
        return child

    def update(self, **fields):
        for key, value in fields.items():
            if key == "metadata" and isinstance(self.fields.get("metadata"), dict):
                self.fields["metadata"] = {**self.fields["metadata"], **value}
            elif value is not None:
                self.fields[key] = value

    def end(self):
        self.ended += 1

    def tree(self):
        return [(c.as_type, c.name, c.fields.get("level", "DEFAULT")) for c in self.children]


class FakeLangfuse:
    def __init__(self):
        self.traces = []

    def start_observation(self, *, name, as_type="span", **fields):
        trace = FakeObservation(name, as_type, **fields)
        self.traces.append(trace)
        return trace


class BrokenLangfuse:
    def start_observation(self, **_):
        raise RuntimeError("Langfuse is down")


@pytest.fixture
def langfuse():
    fake = FakeLangfuse()
    tracing.configure(client=fake)
    return fake


class Runner:
    """A ToolRunner stand-in: canned results by tool name."""

    def __init__(self, results):
        self.results = results

    async def run(self, name, arguments):
        return json.dumps(self.results[name])


def test_off_without_keys():
    assert tracing.configure({}) is False
    assert tracing.start("chat") is tracing.NULL
    with tracing.job("post") as trace:
        assert not trace and tracing.current() is tracing.NULL


@pytest.mark.asyncio
class TestProviderChain:
    async def test_a_fallback_shows_the_failed_call_and_the_one_that_answered(self, langfuse):
        chain = ProviderChain([GEMINI, GROQ], client_factory=fake_factory({"gemini": rate_limited(), "groq": "Hi."}, []))
        with tracing.job("digest", input={"facts": 1}):
            await chain.complete_with_tools([{"role": "user", "content": "q"}], None, 100)

        (trace,) = langfuse.traces
        assert (trace.name, trace.ended) == ("digest", 1)
        assert trace.tree() == [("generation", "gemini", "ERROR"), ("generation", "groq", "DEFAULT")]
        failed, answered = trace.children
        assert failed.fields["status_message"] == "HTTP 429"
        assert answered.fields["model"] == "openai/gpt-oss-120b"
        assert answered.fields["input"] == [{"role": "user", "content": "q"}]  # exactly what was sent
        assert answered.fields["output"] == {"content": "Hi."}
        assert all(c.ended == 1 for c in trace.children)

    async def test_a_streamed_turn_records_when_the_first_piece_arrived(self, langfuse):
        chain = ProviderChain([GROQ], client_factory=fake_factory({"groq": "Crosby leads."}, []))
        trace = tracing.start("chat")
        [e async for e in chain.stream_with_tools([], None, 100, trace=trace)]

        (generation,) = langfuse.traces[0].children
        assert generation.fields["output"] == {"content": "Crosby leads."}
        assert generation.fields["completion_start_time"] is not None


@pytest.mark.asyncio
class TestChatTrace:
    async def service(self, turns):
        chain = ProviderChain([GROQ], client_factory=fake_factory({"groq": turns}, []))
        svc = IntelligenceService(Settings("https://dashboard.test", [], providers=chain.providers), chain=chain)

        async def no_context(context):
            from app.dashboard import ContextBundle
            return ContextBundle(facts={}, evidence=[])
        svc.context_for = no_context
        return svc

    async def test_one_question_is_one_trace_model_tool_model(self, langfuse, monkeypatch):
        svc = await self.service(([tool_call("get_leaders", '{"category":"goals"}')], "Ovechkin leads with 9."))

        async def leaders(self, name, arguments):
            return json.dumps({"leaders": [{"name": "Alex Ovechkin", "goals": 9}]})
        monkeypatch.setattr("app.main.ToolRunner.run", leaders)
        response = await svc.answer(ChatRequest(message="Who leads in goals?", context=ChatContext(page="standings")))

        assert response.answer == "Ovechkin leads with 9."
        (trace,) = langfuse.traces
        assert (trace.name, trace.fields["input"], trace.fields["output"]) == ("chat", "Who leads in goals?", "Ovechkin leads with 9.")
        assert trace.fields["metadata"]["answered_by"] == "Groq"
        assert trace.tree() == [("generation", "groq", "DEFAULT"), ("tool", "get_leaders", "DEFAULT"), ("generation", "groq", "DEFAULT")]
        tool = trace.children[1]
        assert tool.fields["input"] == {"category": "goals"}
        assert tool.fields["output"] == {"leaders": [{"name": "Alex Ovechkin", "goals": 9}]}
        assert trace.ended == 1

    async def test_a_tool_error_is_flagged(self, langfuse, monkeypatch):
        svc = await self.service(([tool_call("get_team", '{"team":"XYZ"}')], "I couldn't find that team."))

        async def unknown(self, name, arguments):
            return json.dumps({"error": "Unknown team 'XYZ'."})
        monkeypatch.setattr("app.main.ToolRunner.run", unknown)
        await svc.answer(ChatRequest(message="XYZ?", context=ChatContext(page="standings")))

        tool = langfuse.traces[0].children[1]
        assert (tool.fields["level"], tool.fields["status_message"]) == ("WARNING", "Unknown team 'XYZ'.")

    async def test_a_broken_langfuse_never_breaks_an_answer(self):
        tracing.configure(client=BrokenLangfuse())
        svc = await self.service("Fine.")
        response = await svc.answer(ChatRequest(message="How's it going?", context=ChatContext(page="standings")))
        assert response.answer == "Fine."


@pytest.mark.asyncio
async def test_scheduled_agents_trace_their_tools_and_checks(langfuse):
    chain = ProviderChain([GROQ], client_factory=fake_factory({"groq": (
        [tool_call("get_odds", "{}")], "Odds are 61%.", "Odds are 60%.",
    )}, []))

    def check(text, sources):
        return [] if "60%" in text else ["61% isn't in the results"]

    with tracing.job("brief", input={"game": 1}):
        draft = await research_and_write(chain, Runner({"get_odds": {"odds": "60%"}}), "Be accurate.", "Brief?",
                                         [{"type": "function", "function": {"name": "get_odds"}}], check, 2, 100, "Write.")

    assert draft.text == "Odds are 60%."
    assert langfuse.traces[0].tree() == [
        ("generation", "groq", "DEFAULT"), ("tool", "get_odds", "DEFAULT"), ("generation", "groq", "DEFAULT"),
        ("guardrail", "check", "WARNING"), ("generation", "groq", "DEFAULT"), ("guardrail", "recheck", "DEFAULT"),
    ]
    assert langfuse.traces[0].children[0].fields["metadata"]["tools_offered"] == ["get_odds"]
