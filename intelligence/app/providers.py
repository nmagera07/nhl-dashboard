"""
Free-first AI providers with automatic fallback.

Every provider here speaks the OpenAI-compatible Chat Completions API, so
one client class works for all of them; only the base URL, key, and model
differ. Providers are tried in order (AI_PROVIDERS); a rate limit, outage,
timeout, or bad key on one moves on to the next. Use keys with no payment
method attached, so a provider can only refuse, never bill.

Environment:
    AI_PROVIDERS            order to try, e.g. "gemini,groq,cloudflare,ollama"
    GEMINI_API_KEY          Google AI Studio key        (GEMINI_MODEL)
    GROQ_API_KEY            Groq console key            (GROQ_MODEL)
    CLOUDFLARE_ACCOUNT_ID   + CLOUDFLARE_API_TOKEN      (CLOUDFLARE_MODEL)
    OLLAMA_BASE_URL         local Ollama, e.g. http://localhost:11434/v1 (OLLAMA_MODEL)
    OPENAI_API_KEY          paid fallback, off unless listed (OPENAI_MODEL)

A provider without its key/URL is skipped. Model names change often, so
every default can be overridden with its *_MODEL variable, or per entry in
AI_PROVIDERS as name:model (e.g. "gemini,gemini:gemini-2.5-flash-lite,groq").
"""

import logging
import os
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Mapping

from openai import AsyncOpenAI, OpenAIError

logger = logging.getLogger(__name__)

DEFAULT_ORDER = "gemini,groq,cloudflare,ollama"


@dataclass(frozen=True)
class Provider:
    name: str
    label: str
    base_url: str | None
    api_key: str
    model: str


def providers_from_env(env: Mapping[str, str] = os.environ) -> list[Provider]:
    def get(key, default=None):
        return (env.get(key) or default or "").strip()

    available = {}
    if get("GEMINI_API_KEY"):
        available["gemini"] = Provider(
            "gemini", "Google Gemini", "https://generativelanguage.googleapis.com/v1beta/openai/",
            get("GEMINI_API_KEY"), get("GEMINI_MODEL", "gemini-flash-lite-latest"),
        )
    if get("GROQ_API_KEY"):
        available["groq"] = Provider(
            "groq", "Groq", "https://api.groq.com/openai/v1",
            # 120b over 20b: in the eval bake-off (2026-10-10) the 20b garbled
            # digest facts and misread stats; the 120b didn't, same limits.
            get("GROQ_API_KEY"), get("GROQ_MODEL", "openai/gpt-oss-120b"),
        )
    if get("CLOUDFLARE_API_TOKEN") and get("CLOUDFLARE_ACCOUNT_ID"):
        available["cloudflare"] = Provider(
            "cloudflare", "Cloudflare Workers AI",
            f"https://api.cloudflare.com/client/v4/accounts/{get('CLOUDFLARE_ACCOUNT_ID')}/ai/v1",
            get("CLOUDFLARE_API_TOKEN"), get("CLOUDFLARE_MODEL", "@cf/meta/llama-3.1-8b-instruct"),
        )
    if get("OLLAMA_BASE_URL"):
        available["ollama"] = Provider(
            "ollama", "Ollama (local)", get("OLLAMA_BASE_URL"), "ollama", get("OLLAMA_MODEL", "qwen2.5:7b"),
        )
    if get("OPENAI_API_KEY"):
        available["openai"] = Provider(
            "openai", "OpenAI", None, get("OPENAI_API_KEY"), get("OPENAI_MODEL", "gpt-5.6-luna"),
        )

    # An entry can name a model too ("gemini:gemini-2.5-flash-lite"). Free
    # quotas are per model, so one key can back several links in the chain.
    chain = []
    for entry in (e.strip() for e in get("AI_PROVIDERS", DEFAULT_ORDER).split(",")):
        name, _, model = entry.partition(":")
        if name not in available:
            continue
        base = available[name]
        chain.append(Provider(entry, f"{base.label} ({model})", base.base_url, base.api_key, model) if model else base)
    return chain


class AllProvidersFailed(Exception):
    """Every configured provider refused or failed."""


class ProviderChain:
    def __init__(self, providers: list[Provider], timeout: float = 20.0, client_factory=None):
        self.providers = providers
        self._factory = client_factory or (
            lambda p: AsyncOpenAI(api_key=p.api_key, base_url=p.base_url, timeout=timeout, max_retries=0)
        )
        self._clients: dict[str, object] = {}

    def __bool__(self) -> bool:
        return bool(self.providers)

    def _client(self, provider: Provider):
        if provider.name not in self._clients:
            self._clients[provider.name] = self._factory(provider)
        return self._clients[provider.name]

    @staticmethod
    def _why(exc: Exception) -> str:
        status = getattr(exc, "status_code", None)
        return f"HTTP {status}" if status else type(exc).__name__

    async def complete_with_tools(self, messages: list[dict], tools: list[dict], max_tokens: int, start: int = 0):
        """
        One agent turn: the reply message (text and/or tool calls) and the
        provider that gave it, plus its index so later turns of the same
        question start there (a provider that just failed isn't retried
        every round). The message list is plain OpenAI format, so a turn
        that falls back mid-conversation continues it on the next provider.
        """
        for index in range(start, len(self.providers)):
            provider = self.providers[index]
            for attempt in (1, 2):
                try:
                    extra = {"tools": tools} if tools else {}
                    response = await self._client(provider).chat.completions.create(
                        model=provider.model, messages=messages, max_tokens=max_tokens, **extra,
                    )
                    message = response.choices[0].message if response.choices else None
                    if message and (message.tool_calls or (message.content or "").strip()):
                        return message, provider, index
                    logger.warning("%s returned an empty turn; trying the next provider", provider.name)
                    break
                except OpenAIError as exc:
                    # Groq rejects a turn (HTTP 400 "tool_use_failed") when the
                    # model writes a malformed tool call; it's a sampling
                    # hiccup, and asking again usually works.
                    if attempt == 1 and self._malformed_tool_call(exc):
                        logger.info("%s wrote a malformed tool call; retrying once", provider.name)
                        continue
                    logger.warning("%s failed (%s); trying the next provider", provider.name, self._why(exc))
                    break
        raise AllProvidersFailed()

    async def stream_with_tools(self, messages: list[dict], tools: list[dict], max_tokens: int, start: int = 0):
        """
        complete_with_tools(), streamed: yields ("text", piece) as the
        answer is written, then ("done", message, provider, index). Falls
        back to the next provider like complete_with_tools() as long as no
        text has gone out yet; a failure after that is re-raised (the
        caller reports a mid-answer failure).
        """
        for index in range(start, len(self.providers)):
            provider = self.providers[index]
            for attempt in (1, 2):
                emitted = False
                try:
                    extra = {"tools": tools} if tools else {}
                    stream = await self._client(provider).chat.completions.create(
                        model=provider.model, messages=messages, max_tokens=max_tokens, stream=True, **extra,
                    )
                    text, calls = [], {}
                    async for chunk in stream:
                        delta = chunk.choices[0].delta if chunk.choices else None
                        if delta is None:
                            continue
                        piece = getattr(delta, "content", None)
                        if piece:
                            text.append(piece)
                            emitted = True
                            yield ("text", piece)
                        for call in getattr(delta, "tool_calls", None) or []:
                            _merge_tool_call(calls, call)
                    message = StreamedMessage("".join(text) or None, [StreamedToolCall(c) for c in calls.values()] or None)
                    if message.tool_calls or (message.content or "").strip():
                        yield ("done", message, provider, index)
                        return
                    logger.warning("%s returned an empty turn; trying the next provider", provider.name)
                    break
                except OpenAIError as exc:
                    if emitted:
                        raise
                    if attempt == 1 and self._malformed_tool_call(exc):
                        logger.info("%s wrote a malformed tool call; retrying once", provider.name)
                        continue
                    logger.warning("%s failed (%s); trying the next provider", provider.name, self._why(exc))
                    break
        raise AllProvidersFailed()

    @staticmethod
    def _malformed_tool_call(exc: Exception) -> bool:
        return getattr(exc, "status_code", None) == 400 and "tool_use_failed" in str(exc)


@dataclass
class StreamedMessage:
    """The pieces of a streamed turn, shaped like a non-streamed message."""
    content: str | None
    tool_calls: list | None


class StreamedToolCall:
    """A tool call rebuilt from stream chunks. model_dump() keeps every field
    the provider sent (Gemini's thought signature must be echoed back)."""

    def __init__(self, data: dict):
        self._data = data
        self.id = data.get("id")
        self.function = SimpleNamespace(name=data["function"]["name"], arguments=data["function"]["arguments"] or "{}")

    def model_dump(self, exclude_none: bool = True) -> dict:
        return {k: v for k, v in self._data.items() if not (exclude_none and v is None)}


def _merge_tool_call(calls: dict, call) -> None:
    """
    Fold one streamed tool-call fragment into `calls`. Groq numbers
    fragments with `index` and may split the arguments across chunks;
    Gemini sends each call whole, with no index but an extra_content field.
    """
    if hasattr(call, "model_dump"):
        part = call.model_dump(exclude_none=True)
    else:  # test fakes
        part = {"id": call.id, "type": getattr(call, "type", "function"),
                "function": {"name": call.function.name, "arguments": call.function.arguments}}
    key = part.pop("index", None)
    if key is None:
        key = part.get("id") or len(calls)
    merged = calls.setdefault(key, {"id": None, "type": "function", "function": {"name": "", "arguments": ""}})
    function = part.pop("function", {}) or {}
    merged["function"]["name"] += function.get("name") or ""
    merged["function"]["arguments"] += function.get("arguments") or ""
    for field, value in part.items():  # id, type, and anything provider-specific
        if value is not None:
            merged[field] = value
