"""app.providers: provider config from env, and the fallback chain."""

import pytest

from app.providers import AllProvidersFailed, Provider, ProviderChain, providers_from_env
from tests.fakes import fake_factory, rate_limited, tool_call


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


MESSAGES = [{"role": "system", "content": "sys"}, {"role": "user", "content": "q"}]
TOOLS = [{"type": "function", "function": {"name": "get_leaders", "parameters": {"type": "object", "properties": {}}}}]


@pytest.mark.asyncio
class TestCompleteWithTools:
    async def test_the_first_provider_answers_and_gets_the_tools(self):
        calls = []
        chain = ProviderChain([provider("gemini"), provider("groq")], client_factory=fake_factory({"gemini": "Hi", "groq": "unused"}, calls))

        message, used, index = await chain.complete_with_tools(MESSAGES, TOOLS, 100)

        assert (message.content, used.name, index) == ("Hi", "gemini", 0)
        assert [name for name, _ in calls] == ["gemini"]
        assert calls[0][1]["messages"] == MESSAGES and calls[0][1]["tools"] == TOOLS

    async def test_a_tool_call_turn_counts_as_an_answer(self):
        chain = ProviderChain([provider("gemini")], client_factory=fake_factory({"gemini": [tool_call("get_leaders", "{}")]}, []))

        message, _, _ = await chain.complete_with_tools(MESSAGES, TOOLS, 100)

        assert message.tool_calls[0].function.name == "get_leaders"

    async def test_a_rate_limited_provider_falls_back_and_later_turns_start_there(self):
        calls = []
        chain = ProviderChain([provider("gemini"), provider("groq")], client_factory=fake_factory({"gemini": rate_limited(), "groq": "From Groq"}, calls))

        message, used, index = await chain.complete_with_tools(MESSAGES, TOOLS, 100)
        await chain.complete_with_tools(MESSAGES, TOOLS, 100, start=index)

        assert (message.content, used.name, index) == ("From Groq", "groq", 1)
        assert [name for name, _ in calls] == ["gemini", "groq", "groq"]

    async def test_an_empty_answer_also_falls_back(self):
        chain = ProviderChain([provider("gemini"), provider("groq")], client_factory=fake_factory({"gemini": "  ", "groq": "Real answer"}, []))

        message, _, _ = await chain.complete_with_tools(MESSAGES, TOOLS, 100)

        assert message.content == "Real answer"

    async def test_no_tools_means_none_are_sent(self):
        calls = []
        chain = ProviderChain([provider("gemini")], client_factory=fake_factory({"gemini": "Done"}, calls))

        await chain.complete_with_tools(MESSAGES, None, 100)

        assert "tools" not in calls[0][1]

    async def test_all_failing_raises(self):
        chain = ProviderChain([provider("gemini"), provider("groq")], client_factory=fake_factory({"gemini": rate_limited(), "groq": rate_limited()}, []))

        with pytest.raises(AllProvidersFailed):
            await chain.complete_with_tools(MESSAGES, TOOLS, 100)
