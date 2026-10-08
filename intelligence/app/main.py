import json
import logging
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from openai import OpenAIError
from pydantic import BaseModel, Field, model_validator
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from .config import Settings, get_settings
from .dashboard import ContextBundle, DashboardClient, DashboardUnavailable
from .providers import AllProvidersFailed, ProviderChain


logger = logging.getLogger(__name__)


class ChatContext(BaseModel):
    page: Literal["player", "team", "standings", "game"]
    player_id: int | None = Field(default=None, gt=0)
    team_abbrev: str | None = Field(default=None, min_length=2, max_length=3)
    game_id: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_page_target(self):
        if self.page == "player" and not self.player_id:
            raise ValueError("player_id is required for player context")
        if self.page == "team" and not self.team_abbrev:
            raise ValueError("team_abbrev is required for team context")
        if self.page == "game" and not self.game_id:
            raise ValueError("game_id is required for game context")
        return self


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=1000)
    context: ChatContext


class Evidence(BaseModel):
    label: str
    endpoint: str


class ChatResponse(BaseModel):
    answer: str
    evidence: list[Evidence]
    model: str | None = None  # which provider answered, e.g. "Google Gemini"


NOT_CONFIGURED = "NHL Intelligence is not configured yet."
ALL_BUSY = "NHL Intelligence is taking a breather (its free AI providers are busy). Try again in a minute."
MID_ANSWER_FAILURE = "NHL Intelligence lost its connection mid-answer. Try asking again."


SYSTEM_INSTRUCTIONS = """You are NHL Intelligence, a concise hockey analyst.
Use only the supplied dashboard data. Do not invent game events, injuries, line combinations, or facts absent from the context. On a game page you get that game's box score (scoring summary, three stars, team and player stats) but no play-by-play; on other pages you get season-level data only, so if asked what happened in a specific game there, say to open that game's page. League context lists only the top leaders, not every player. Write player names exactly as they appear in the data; never expand an initial into a first name. Explain statistics in plain language, distinguish facts from reasonable inferences, and keep answers under 220 words."""


class IntelligenceService:
    def __init__(self, settings: Settings, dashboard: DashboardClient | None = None, chain: ProviderChain | None = None):
        self.settings = settings
        self.dashboard = dashboard or DashboardClient(settings.dashboard_api_url)
        self.chain = chain if chain is not None else ProviderChain(settings.providers)

    async def context_for(self, context: ChatContext) -> ContextBundle:
        if context.page == "player":
            return await self.dashboard.player_context(context.player_id)
        if context.page == "team":
            return await self.dashboard.team_context(context.team_abbrev)
        if context.page == "game":
            return await self.dashboard.game_context(context.game_id)
        return await self.dashboard.league_context()

    def prompt_for(self, request: ChatRequest, context: ContextBundle) -> str:
        facts = json.dumps(context.facts, default=str, separators=(",", ":"))
        if len(facts) > self.settings.max_context_chars:
            # Safety net only: the compact contexts are sized to fit well under this.
            logger.warning("Context for %s is %d chars; truncating", request.context.page, len(facts))
            facts = facts[: self.settings.max_context_chars] + "\n[Dashboard context truncated to control usage.]"
        return (
            f"Question: {request.message}\n\nPage context: {request.context.model_dump_json()}"
            f"\n\nDashboard data (JSON): {facts}"
        )

    async def _context(self, request: ChatRequest) -> ContextBundle:
        if not self.chain:
            raise HTTPException(status_code=503, detail=NOT_CONFIGURED)
        try:
            return await self.context_for(request.context)
        except DashboardUnavailable as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    async def answer(self, request: ChatRequest) -> ChatResponse:
        context = await self._context(request)
        try:
            text, provider = await self.chain.complete(
                SYSTEM_INSTRUCTIONS, self.prompt_for(request, context), self.settings.max_output_tokens
            )
        except AllProvidersFailed as exc:
            raise HTTPException(status_code=503, detail=ALL_BUSY) from exc
        return ChatResponse(answer=text, evidence=[Evidence(**item) for item in context.evidence], model=provider.label)

    async def answer_stream(self, request: ChatRequest):
        """Yield server-sent events as the model produces answer text."""
        context = await self._context(request)
        prompt = self.prompt_for(request, context)
        try:
            async for kind, value in self.chain.stream(SYSTEM_INSTRUCTIONS, prompt, self.settings.max_output_tokens):
                if kind == "delta":
                    yield f"data: {json.dumps({'type': 'delta', 'text': value})}\n\n"
                else:
                    yield f"data: {json.dumps({'type': 'done', 'evidence': context.evidence, 'model': value.label})}\n\n"
        except AllProvidersFailed:
            yield f"data: {json.dumps({'type': 'error', 'message': ALL_BUSY})}\n\n"
        except OpenAIError:
            logger.exception("AI provider failed mid-answer")
            yield f"data: {json.dumps({'type': 'error', 'message': MID_ANSWER_FAILURE})}\n\n"


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.intelligence = IntelligenceService(get_settings())
    yield


settings = get_settings()
app = FastAPI(title="NHL Intelligence", version="0.1.0", lifespan=lifespan)
limiter = Limiter(key_func=get_remote_address, default_limits=["30/minute"])
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(CORSMiddleware, allow_origins=settings.allowed_origins, allow_methods=["GET", "POST"], allow_headers=["Content-Type"])


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
@limiter.limit("5/minute")
@limiter.limit("30/day")
async def chat(payload: ChatRequest, request: Request):
    return await request.app.state.intelligence.answer(payload)


@app.post("/chat/stream")
@limiter.limit("5/minute")
@limiter.limit("30/day")
async def chat_stream(payload: ChatRequest, request: Request):
    return StreamingResponse(
        request.app.state.intelligence.answer_stream(payload),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )
