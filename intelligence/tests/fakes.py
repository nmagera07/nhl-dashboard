"""Fake OpenAI-compatible clients for testing the provider chain offline."""

from types import SimpleNamespace

import httpx
from openai import APIStatusError


def rate_limited(provider="fake"):
    request = httpx.Request("POST", f"https://{provider}.test/chat/completions")
    return APIStatusError("rate limited", response=httpx.Response(429, request=request), body=None)


class _Completions:
    def __init__(self, behavior, calls, name):
        self.behavior, self.calls, self.name = behavior, calls, name

    async def create(self, **kwargs):
        self.calls.append((self.name, kwargs))
        if isinstance(self.behavior, Exception):
            raise self.behavior
        if kwargs.get("stream"):
            return self._stream(self.behavior)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=self.behavior))])

    @staticmethod
    async def _stream(chunks):
        for chunk in chunks:
            if isinstance(chunk, Exception):
                raise chunk
            yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=chunk))])


def fake_factory(behaviors, calls):
    """client_factory for ProviderChain: provider name -> answer text,
    list of stream chunks (Exceptions raised mid-stream), or an Exception."""
    def factory(provider):
        return SimpleNamespace(chat=SimpleNamespace(completions=_Completions(behaviors[provider.name], calls, provider.name)))
    return factory
