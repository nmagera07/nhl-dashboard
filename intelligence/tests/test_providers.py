"""app.providers: provider config from env, and the fallback chain."""

import pytest

from app.providers import AllProvidersFailed, Provider, ProviderChain, providers_from_env
from tests.fakes import fake_factory, rate_limited


def provider(name):
    return Provider(name, name.title(), f"https://{name}.test/v1", "key", f"{name}-model")


class TestProvidersFromEnv:
    def test_only_providers_with_credentials_are_used_in_the_configured_order(self):
        env = {"AI_PROVIDERS": "groq,gemini,cloudflare", "GEMINI_API_KEY": "g", "GROQ_API_KEY": "q",
               "CLOUDFLARE_API_TOKEN": "c"}  # no CLOUDFLARE_ACCOUNT_ID -> skipped

        assert [p.name for p in providers_from_env(env)] == ["groq", "gemini"]

    def test_default_order_is_free_providers_only(self):
        env = {"GEMINI_API_KEY": "g", "GROQ_API_KEY": "q", "OPENAI_API_KEY": "paid"}

        assert [p.name for p in providers_from_env(env)] == ["gemini", "groq"]

    def test_cloudflare_url_includes_the_account_and_models_can_be_overridden(self):
        env = {"AI_PROVIDERS": "cloudflare,ollama", "CLOUDFLARE_API_TOKEN": "c", "CLOUDFLARE_ACCOUNT_ID": "acct",
               "CLOUDFLARE_MODEL": "@cf/some/model", "OLLAMA_BASE_URL": "http://localhost:11434/v1"}

        cloudflare, ollama = providers_from_env(env)
        assert cloudflare.base_url == "https://api.cloudflare.com/client/v4/accounts/acct/ai/v1"
        assert cloudflare.model == "@cf/some/model"
        assert ollama.base_url == "http://localhost:11434/v1"

    def test_no_keys_means_no_providers(self):
        assert providers_from_env({}) == []


@pytest.mark.asyncio
class TestComplete:
    async def test_the_first_provider_answers(self):
        calls = []
        chain = ProviderChain([provider("gemini"), provider("groq")], client_factory=fake_factory({"gemini": "Hi", "groq": "unused"}, calls))

        text, used = await chain.complete("sys", "q", 100)

        assert (text, used.name) == ("Hi", "gemini")
        assert [name for name, _ in calls] == ["gemini"]
        assert calls[0][1]["messages"][0] == {"role": "system", "content": "sys"}

    async def test_a_rate_limited_provider_falls_back_to_the_next(self):
        calls = []
        chain = ProviderChain([provider("gemini"), provider("groq")], client_factory=fake_factory({"gemini": rate_limited(), "groq": "From Groq"}, calls))

        text, used = await chain.complete("sys", "q", 100)

        assert (text, used.name) == ("From Groq", "groq")

    async def test_an_empty_answer_also_falls_back(self):
        chain = ProviderChain([provider("gemini"), provider("groq")], client_factory=fake_factory({"gemini": "  ", "groq": "Real answer"}, []))

        text, _ = await chain.complete("sys", "q", 100)

        assert text == "Real answer"

    async def test_all_failing_raises(self):
        chain = ProviderChain([provider("gemini"), provider("groq")], client_factory=fake_factory({"gemini": rate_limited(), "groq": rate_limited()}, []))

        with pytest.raises(AllProvidersFailed):
            await chain.complete("sys", "q", 100)


@pytest.mark.asyncio
class TestStream:
    async def collect(self, chain):
        return [item async for item in chain.stream("sys", "q", 100)]

    async def test_falls_back_before_the_first_chunk(self):
        chain = ProviderChain([provider("gemini"), provider("groq")], client_factory=fake_factory({"gemini": rate_limited(), "groq": ["Hel", "lo"]}, []))

        events = await self.collect(chain)

        assert events[:2] == [("delta", "Hel"), ("delta", "lo")]
        assert events[2][0] == "done" and events[2][1].name == "groq"

    async def test_a_failure_mid_answer_is_not_retried_elsewhere(self):
        calls = []
        chain = ProviderChain([provider("gemini"), provider("groq")], client_factory=fake_factory({"gemini": ["Hel", rate_limited()], "groq": ["unused"]}, calls))

        with pytest.raises(Exception):
            await self.collect(chain)
        assert [name for name, _ in calls] == ["gemini"]

    async def test_all_failing_raises(self):
        chain = ProviderChain([provider("gemini")], client_factory=fake_factory({"gemini": rate_limited()}, []))

        with pytest.raises(AllProvidersFailed):
            await self.collect(chain)
