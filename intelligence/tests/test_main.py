import httpx
import pytest
from fastapi import HTTPException
from openai import OpenAIError

from app.config import Settings
from app.dashboard import DashboardClient
from app.main import ChatContext, ChatRequest, IntelligenceService


class FakeResponses:
    async def create(self, **kwargs):
        assert kwargs["model"] == "test-model"
        assert "Player One" in kwargs["input"]
        return type("Response", (), {"output_text": "Player One is producing efficiently."})()


class FakeOpenAI:
    responses = FakeResponses()


class FailingResponses:
    async def create(self, **kwargs):
        raise OpenAIError("provider failed")


class FailingOpenAI:
    responses = FailingResponses()


@pytest.mark.asyncio
async def test_player_answer_uses_dashboard_context():
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"first_name": "Player", "last_name": "One", "position_code": "C", "season_stats": [{"season_id": 20262027, "points": 50}]}))
    async with httpx.AsyncClient(base_url="https://dashboard.test", transport=transport) as client:
        service = IntelligenceService(
            Settings("https://dashboard.test", "test-key", "test-model", ["http://localhost:5173"]),
            dashboard=DashboardClient("https://dashboard.test", client), openai_client=FakeOpenAI(),
        )
        result = await service.answer(ChatRequest(message="How is he doing?", context=ChatContext(page="player", player_id=7)))
    assert result.answer == "Player One is producing efficiently."
    assert result.evidence[0].endpoint == "/players/7"


def test_player_context_requires_player_id():
    with pytest.raises(ValueError):
        ChatContext(page="player")


def test_game_context_requires_game_id():
    with pytest.raises(ValueError):
        ChatContext(page="game")


@pytest.mark.asyncio
async def test_openai_failure_becomes_safe_service_error():
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"name": "Player One"}))
    async with httpx.AsyncClient(base_url="https://dashboard.test", transport=transport) as client:
        service = IntelligenceService(
            Settings("https://dashboard.test", "test-key", "test-model", ["http://localhost:5173"]),
            dashboard=DashboardClient("https://dashboard.test", client),
            openai_client=FailingOpenAI(),
        )
        with pytest.raises(HTTPException) as error:
            await service.answer(
                ChatRequest(message="How is he doing?", context=ChatContext(page="player", player_id=7))
            )

    assert error.value.status_code == 503
    assert error.value.detail == "NHL Intelligence's AI provider is temporarily unavailable."


@pytest.mark.asyncio
async def test_dashboard_retries_transient_timeout():
    attempts = 0

    def handler(request):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise httpx.ReadTimeout("slow upstream", request=request)
        return httpx.Response(200, json={"first_name": "Player", "last_name": "One"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(base_url="https://dashboard.test", transport=transport) as client:
        context = await DashboardClient("https://dashboard.test", client).player_context(7)

    assert attempts == 2
    assert context.facts["player"]["name"] == "Player One"
