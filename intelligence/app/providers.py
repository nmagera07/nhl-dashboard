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
every default can be overridden with its *_MODEL variable.
"""

import logging
import os
from dataclasses import dataclass
from typing import AsyncIterator, Mapping

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
            get("GROQ_API_KEY"), get("GROQ_MODEL", "openai/gpt-oss-20b"),
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

    order = [n.strip() for n in get("AI_PROVIDERS", DEFAULT_ORDER).split(",") if n.strip()]
    return [available[name] for name in order if name in available]


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
    def _messages(system: str, prompt: str) -> list[dict[str, str]]:
        return [{"role": "system", "content": system}, {"role": "user", "content": prompt}]

    @staticmethod
    def _why(exc: Exception) -> str:
        status = getattr(exc, "status_code", None)
        return f"HTTP {status}" if status else type(exc).__name__

    async def complete(self, system: str, prompt: str, max_tokens: int) -> tuple[str, Provider]:
        for provider in self.providers:
            try:
                response = await self._client(provider).chat.completions.create(
                    model=provider.model, messages=self._messages(system, prompt), max_tokens=max_tokens,
                )
                text = (response.choices[0].message.content or "").strip() if response.choices else ""
                if text:
                    return text, provider
                logger.warning("%s returned an empty answer; trying the next provider", provider.name)
            except OpenAIError as exc:
                logger.warning("%s failed (%s); trying the next provider", provider.name, self._why(exc))
        raise AllProvidersFailed()

    async def stream(self, system: str, prompt: str, max_tokens: int) -> AsyncIterator[tuple[str, object]]:
        """
        Yields ("delta", text) chunks, then ("done", provider). Falls back to
        the next provider only before the first chunk -- an answer that has
        started streaming can't switch models mid-sentence, so a failure
        after that raises.
        """
        for provider in self.providers:
            started = False
            try:
                stream = await self._client(provider).chat.completions.create(
                    model=provider.model, messages=self._messages(system, prompt),
                    max_tokens=max_tokens, stream=True,
                )
                async for chunk in stream:
                    delta = chunk.choices[0].delta.content if chunk.choices else None
                    if delta:
                        started = True
                        yield "delta", delta
                if started:
                    yield "done", provider
                    return
                logger.warning("%s streamed an empty answer; trying the next provider", provider.name)
            except OpenAIError as exc:
                if started:
                    raise
                logger.warning("%s failed (%s); trying the next provider", provider.name, self._why(exc))
        raise AllProvidersFailed()
