"""Fake OpenAI-compatible clients for testing the provider chain offline."""

from types import SimpleNamespace

import httpx
from openai import APIStatusError


def rate_limited(provider="fake"):
    request = httpx.Request("POST", f"https://{provider}.test/chat/completions")
    return APIStatusError("rate limited", response=httpx.Response(429, request=request), body=None)


def tool_call(name, arguments, call_id="call_1"):
    """A model turn asking for one tool."""
    return SimpleNamespace(id=call_id, type="function", function=SimpleNamespace(name=name, arguments=arguments))


class _Completions:
    def __init__(self, behavior, calls, name):
        # behavior: answer text, an Exception, a list of tool calls, or a
        # list of turns (each one of those) consumed one per request.
        self.turns = list(behavior) if isinstance(behavior, tuple) else None
        self.behavior, self.calls, self.name = behavior, calls, name

    async def create(self, **kwargs):
        self.calls.append((self.name, kwargs))
        turn = self.turns.pop(0) if self.turns is not None else self.behavior
        if isinstance(turn, Exception):
            raise turn
        if isinstance(turn, list):
            message = SimpleNamespace(content=None, tool_calls=turn)
        else:
            message = SimpleNamespace(content=turn, tool_calls=None)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def fake_factory(behaviors, calls):
    """client_factory for ProviderChain: provider name -> behavior (see _Completions);
    a tuple is a sequence of turns, one per request."""
    def factory(provider):
        return SimpleNamespace(chat=SimpleNamespace(completions=_Completions(behaviors[provider.name], calls, provider.name)))
    return factory
