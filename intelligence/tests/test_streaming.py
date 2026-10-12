"""Streaming answers: the provider chain's stream_with_tools and the SSE events."""

import json
from types import SimpleNamespace

import pytest

from app.providers import AllProvidersFailed, Provider, ProviderChain, _merge_tool_call
from tests.fakes import fake_factory, rate_limited, tool_call

GROQ = Provider("groq", "Groq", None, "k", "m")
GEMINI = Provider("gemini", "Google Gemini", None, "k", "m")


async def collect(gen):
    return [e async for e in gen]


@pytest.mark.asyncio
class TestStreamWithTools:
    async def test_text_streams_then_finishes_with_the_whole_message(self):
        chain = ProviderChain([GROQ], client_factory=fake_factory({"groq": "Crosby leads."}, []))
        events = await collect(chain.stream_with_tools([], None, 100))

        assert [e[1] for e in events if e[0] == "text"] == ["Crosby", " leads."]
        assert events[-1][0] == "done" and events[-1][1].content == "Crosby leads." and events[-1][2] is GROQ

    async def test_tool_calls_come_back_as_a_message(self):
        chain = ProviderChain([GROQ], client_factory=fake_factory({"groq": [tool_call("get_leaders", '{"category":"points"}')]}, []))
        (done,) = await collect(chain.stream_with_tools([], [], 100))

        call = done[1].tool_calls[0]
        assert (call.id, call.function.name, call.function.arguments) == ("call_1", "get_leaders", '{"category":"points"}')

    async def test_falls_back_when_a_provider_fails_before_any_text(self):
        chain = ProviderChain([GEMINI, GROQ], client_factory=fake_factory({"gemini": rate_limited(), "groq": "Hi."}, []))
        events = await collect(chain.stream_with_tools([], None, 100))

        assert events[-1][2] is GROQ and events[-1][3] == 1

    async def test_all_failing_raises(self):
        chain = ProviderChain([GROQ], client_factory=fake_factory({"groq": rate_limited()}, []))
        with pytest.raises(AllProvidersFailed):
            await collect(chain.stream_with_tools([], None, 100))

    async def test_a_failure_after_text_went_out_is_not_retried_elsewhere(self):
        async def broken_stream():
            yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="Half an ans", tool_calls=None))])
            raise rate_limited()

        async def create(**kwargs):
            return broken_stream()

        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        chain = ProviderChain([GROQ, GEMINI], client_factory=lambda p: client)
        seen = []
        with pytest.raises(Exception, match="rate limited"):
            async for event in chain.stream_with_tools([], None, 100):
                seen.append(event)
        assert seen == [("text", "Half an ans")]


class TestMergeToolCall:
    def test_groq_fragments_are_joined_by_index(self):
        calls = {}
        for part in ({"index": 0, "id": "fc_1", "type": "function", "function": {"name": "get_team", "arguments": '{"te'}},
                     {"index": 0, "function": {"arguments": 'am":"PIT"}'}}):
            _merge_tool_call(calls, SimpleNamespace(model_dump=lambda exclude_none, p=part: json.loads(json.dumps(p))))
        assert calls[0]["function"] == {"name": "get_team", "arguments": '{"team":"PIT"}'} and calls[0]["id"] == "fc_1"

    def test_gemini_keeps_its_thought_signature(self):
        part = {"id": "call_9", "type": "function", "function": {"name": "get_leaders", "arguments": "{}"},
                "extra_content": {"google": {"thought_signature": "sig"}}}
        calls = {}
        _merge_tool_call(calls, SimpleNamespace(model_dump=lambda exclude_none: dict(part)))
        assert calls["call_9"]["extra_content"] == {"google": {"thought_signature": "sig"}}


@pytest.mark.asyncio
async def test_text_before_a_tool_call_is_reset_in_the_stream():
    import httpx

    from app.config import Settings
    from app.dashboard import DashboardClient
    from app.main import ChatContext, ChatRequest, IntelligenceService

    turns = ("Let me check.", [tool_call("get_leaders", "{}")], "Crosby leads.")
    calls = []

    # First turn: text *and* a tool call in the same reply.
    class Thinking:
        def __init__(self):
            self.n = 0

        async def create(self, **kwargs):
            calls.append(kwargs)
            self.n += 1
            async def gen():
                if self.n == 1:
                    yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="Let me check.", tool_calls=None))])
                    yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=None, tool_calls=turns[1]))])
                else:
                    yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="Crosby leads.", tool_calls=None))])
            return gen()

    completions = Thinking()
    chain = ProviderChain([GROQ], client_factory=lambda p: SimpleNamespace(chat=SimpleNamespace(completions=completions)))
    transport = httpx.MockTransport(lambda r: httpx.Response(200, json=[{"team_abbrev": "PIT", "snapshot_date": "2026-10-10"}]))
    async with httpx.AsyncClient(base_url="https://d.test", transport=transport) as http:
        settings = Settings("https://d.test", [], providers=[GROQ])
        service = IntelligenceService(settings, dashboard=DashboardClient("https://d.test", http), chain=chain)
        events = [json.loads(e[6:]) async for e in service.answer_stream(ChatRequest(message="?", context=ChatContext(page="standings")))]

    types = [e["type"] for e in events]
    assert types[:3] == ["delta", "reset", "status"]
    assert events[-2] == {"type": "delta", "text": "Crosby leads."} and types[-1] == "done"
