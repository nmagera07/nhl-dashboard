import logging
from types import SimpleNamespace

import pytest

from app import usage
from app.providers import Provider, ProviderChain
from tests.fakes import fake_factory

GROQ = Provider("groq", "Groq", None, "k", "gpt-oss-120b")


def test_each_call_is_logged_under_its_purpose(caplog):
    caplog.set_level(logging.INFO, logger="app.usage")
    usage.record(GROQ, SimpleNamespace(prompt_tokens=4120, completion_tokens=380))
    with usage.purpose("brief"):
        usage.record(GROQ, SimpleNamespace(prompt_tokens=900, completion_tokens=None))
    usage.record(GROQ, None)  # a provider that sends no usage
    assert [r.getMessage() for r in caplog.records] == [
        "AI usage: purpose=chat provider=groq model=gpt-oss-120b prompt=4120 completion=380",
        "AI usage: purpose=brief provider=groq model=gpt-oss-120b prompt=900 completion=0",
    ]


@pytest.mark.asyncio
async def test_the_chain_records_plain_and_streamed_calls(caplog, monkeypatch):
    caplog.set_level(logging.INFO, logger="app.usage")
    calls = []
    chain = ProviderChain([GROQ], client_factory=fake_factory({"groq": "Hi there."}, calls))
    seen = []
    monkeypatch.setattr(usage, "record", lambda provider, u: seen.append(u))
    with usage.purpose("digest"):
        await chain.complete_with_tools([{"role": "user", "content": "hi"}], None, 100)
    async for _ in chain.stream_with_tools([{"role": "user", "content": "hi"}], None, 100):
        pass
    assert seen  # recorded from the response and from each chunk (None when a fake sends no usage)
    assert calls[1][1]["stream_options"] == {"include_usage": True}
