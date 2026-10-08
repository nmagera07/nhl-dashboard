import json
import logging
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from openai import AsyncOpenAI, OpenAIError
from pydantic import BaseModel, Field, model_validator
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from .config import Settings, get_settings
from .dashboard import ContextBundle, DashboardClient, DashboardUnavailable


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


SYSTEM_INSTRUCTIONS = """You are NHL Intelligence, a concise hockey analyst.
Use only the supplied dashboard data. Do not invent game events, injuries, line combinations, or facts absent from the context. On a game page you get that game's box score (scoring summary, three stars, team and player stats) but no play-by-play; on other pages you get season-level data only, so if asked what happened in a specific game there, say to open that game's page. League context lists only the top leaders, not every player. Explain statistics in plain language, distinguish facts from reasonable inferences, and keep answers under 220 words."""


class IntelligenceService:
    def __init__(self, settings: Settings, dashboard: DashboardClient | None = None, openai_client=None):
        self.settings = settings
        self.dashboard = dashboard or DashboardClient(settings.dashboard_api_url)
        self.openai_client = openai_client or (AsyncOpenAI(api_key=settings.openai_api_key) if settings.openai_api_key else None)

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

    async def answer(self, request: ChatRequest) -> ChatResponse:
        if not self.openai_client:
            raise HTTPException(status_code=503, detail="NHL Intelligence is not configured yet.")
        try:
            context = await self.context_for(request.context)
        except DashboardUnavailable as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        try:
            response = await self.openai_client.responses.create(
                model=self.settings.openai_model,
                instructions=SYSTEM_INSTRUCTIONS,
                input=self.prompt_for(request, context),
                max_output_tokens=self.settings.max_output_tokens,
            )
        except OpenAIError as exc:
            logger.exception("OpenAI response failed")
            status_code = getattr(exc, "status_code", None)
            if status_code in {401, 403}:
                detail = "NHL Intelligence's AI provider configuration needs attention."
            elif status_code == 429:
                detail = "NHL Intelligence has reached its current AI usage limit."
            else:
                detail = "NHL Intelligence's AI provider is temporarily unavailable."
            raise HTTPException(status_code=503, detail=detail) from exc
        answer = getattr(response, "output_text", "").strip()
        if not answer:
            raise HTTPException(status_code=502, detail="The model returned an empty response.")
        return ChatResponse(answer=answer, evidence=[Evidence(**item) for item in context.evidence])

    async def answer_stream(self, request: ChatRequest):
        """Yield server-sent events as the model produces answer text."""
        if not self.openai_client:
            raise HTTPException(status_code=503, detail="NHL Intelligence is not configured yet.")
        try:
            context = await self.context_for(request.context)
        except DashboardUnavailable as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

        prompt = self.prompt_for(request, context)
        try:
            stream = await self.openai_client.responses.create(
                model=self.settings.openai_model,
                instructions=SYSTEM_INSTRUCTIONS,
                input=prompt,
                stream=True,
                max_output_tokens=self.settings.max_output_tokens,
            )
            async for event in stream:
                if getattr(event, "type", None) == "response.output_text.delta":
                    delta = getattr(event, "delta", "")
                    if delta:
                        yield f"data: {json.dumps({'type': 'delta', 'text': delta})}\n\n"
            yield f"data: {json.dumps({'type': 'done', 'evidence': context.evidence})}\n\n"
        except OpenAIError as exc:
            logger.exception("OpenAI streaming response failed")
            yield f"data: {json.dumps({'type': 'error', 'message': self.provider_error(exc)})}\n\n"

    @staticmethod
    def provider_error(exc: OpenAIError) -> str:
        status_code = getattr(exc, "status_code", None)
        if status_code in {401, 403}:
            return "NHL Intelligence's AI provider configuration needs attention."
        if status_code == 429:
            return "NHL Intelligence has reached its current AI usage limit."
        return "NHL Intelligence's AI provider is temporarily unavailable."


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
