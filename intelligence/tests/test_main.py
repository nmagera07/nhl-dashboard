import httpx
import pytest
from fastapi import HTTPException
from app.config import Settings
from app.dashboard import DashboardClient
from app.main import ALL_BUSY, ChatContext, ChatRequest, IntelligenceService
from app.providers import Provider, ProviderChain
from tests.fakes import fake_factory, rate_limited


def settings():
    return Settings("https://dashboard.test", ["http://localhost:5173"], providers=[Provider("groq", "Groq", None, "k", "test-model")])


def chain(behavior, calls=None):
    return ProviderChain(settings().providers, client_factory=fake_factory({"groq": behavior}, calls if calls is not None else []))


@pytest.mark.asyncio
async def test_player_answer_uses_dashboard_context():
    calls = []
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"first_name": "Player", "last_name": "One", "position_code": "C", "season_stats": [{"season_id": 20262027, "points": 50}]}))
    async with httpx.AsyncClient(base_url="https://dashboard.test", transport=transport) as client:
        service = IntelligenceService(settings(), dashboard=DashboardClient("https://dashboard.test", client), chain=chain("Player One is producing efficiently.", calls))
        result = await service.answer(ChatRequest(message="How is he doing?", context=ChatContext(page="player", player_id=7)))
    assert result.answer == "Player One is producing efficiently."
    assert result.evidence[0].endpoint == "/players/7"
    assert result.model == "Groq"
    _, kwargs = calls[0]
    assert kwargs["model"] == "test-model"
    assert "Player One" in kwargs["messages"][1]["content"]


def test_player_context_requires_player_id():
    with pytest.raises(ValueError):
        ChatContext(page="player")


def test_game_context_requires_game_id():
    with pytest.raises(ValueError):
        ChatContext(page="game")


@pytest.mark.asyncio
async def test_all_providers_failing_becomes_a_friendly_503():
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"first_name": "Player", "last_name": "One"}))
    async with httpx.AsyncClient(base_url="https://dashboard.test", transport=transport) as client:
        service = IntelligenceService(settings(), dashboard=DashboardClient("https://dashboard.test", client), chain=chain(rate_limited()))
        with pytest.raises(HTTPException) as error:
            await service.answer(ChatRequest(message="How is he doing?", context=ChatContext(page="player", player_id=7)))

    assert error.value.status_code == 503
    assert error.value.detail == ALL_BUSY


@pytest.mark.asyncio
async def test_no_providers_configured_is_a_503():
    service = IntelligenceService(Settings("https://dashboard.test", []), dashboard=DashboardClient("https://dashboard.test"))
    with pytest.raises(HTTPException) as error:
        await service.answer(ChatRequest(message="Hi", context=ChatContext(page="standings")))
    assert error.value.detail == "NHL Intelligence is not configured yet."


@pytest.mark.asyncio
async def test_stream_reports_which_provider_answered():
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"first_name": "Player", "last_name": "One"}))
    async with httpx.AsyncClient(base_url="https://dashboard.test", transport=transport) as client:
        service = IntelligenceService(settings(), dashboard=DashboardClient("https://dashboard.test", client), chain=chain(["Fine ", "season."]))
        events = [e async for e in service.answer_stream(ChatRequest(message="?", context=ChatContext(page="player", player_id=7)))]

    assert '"text": "Fine "' in events[0]
    assert '"type": "done"' in events[-1] and '"model": "Groq"' in events[-1]


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


def test_health_reports_commit_and_configured_providers(monkeypatch):
    from fastapi.testclient import TestClient

    import app.main as main

    monkeypatch.setenv("GIT_SHA", "abc123")
    monkeypatch.setenv("GROQ_API_KEY", "k")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with TestClient(main.app) as client:
        body = client.get("/health").json()

    assert body["status"] == "ok"
    assert body["commit"] == "abc123"
    assert "groq" in body["providers"] and "gemini" not in body["providers"]
