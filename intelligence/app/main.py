import asyncio
import hmac
import json
import logging
import os
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
from .tools import LABELS, TOOLS, ToolRunner


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


# Follow-ups: the client sends the last couple of exchanges so "what about
# their power play?" makes sense. Capped server-side (count and length) so a
# client can't run up token usage; page data is only attached to the newest
# question, never repeated in history.
MAX_HISTORY_MESSAGES = 4  # 2 question/answer exchanges
MAX_HISTORY_CHARS = 1500  # per message


class HistoryTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=1000)
    context: ChatContext
    history: list[HistoryTurn] = Field(default_factory=list, max_length=20)

    def trimmed_history(self) -> list[dict[str, str]]:
        return [
            {"role": turn.role, "content": turn.content[:MAX_HISTORY_CHARS]}
            for turn in self.history[-MAX_HISTORY_MESSAGES:]
        ]


class DigestRequest(BaseModel):
    facts: dict


class DigestResponse(BaseModel):
    text: str
    model: str


DIGEST_INSTRUCTIONS = """You write the morning NHL digest for a hockey stats app, from a JSON list of facts.
Format (Markdown):
- First line: a bold one-sentence headline about LAST NIGHT's biggest result (never about tonight's games).
- Then sections with these headings, skipping any with no facts: "### Last night", "### Playoff race", "### Tonight".
- 2 to 4 short bullets per section. Each game, odds move, and the game of the night has a ready-made "line": use those lines (you may rephrase them) rather than translating abbreviations yourself.
- In "Playoff race", give the odds moves with both numbers (e.g. "from 54% to 44%"); they come from the app's playoff-odds model.
- In "Tonight", mention only the game of the night and the model's win probability for it. Do not list the other games.
Last night's games and tonight's games are different games: never mix them up.
Use only the facts. No invented stats, injuries, streaks, or storylines. Keep it under 170 words."""
MAX_DIGEST_FACTS_CHARS = 12000
DIGEST_MAX_TOKENS = 1500


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


TOOL_INSTRUCTIONS = """
You have tools for standings, teams, schedules, playoff odds history, players, and the playoff-odds model's season simulations. Call a tool whenever the question needs numbers that aren't in the page data. For any "what if" question or "what does X need", call simulate_scenario or playoff_path: never estimate odds or projections yourself. For a scenario, compare with_scenario to that tool's own baseline (not other odds figures). Report the tools' numbers as given (rounded is fine) and say they come from the playoff-odds model's simulations. Use 3-letter team abbreviations in tool calls."""

# Each round resends the conversation, so keep it short: free tiers cap
# tokens per minute, and three rounds cover even multi-team questions.
MAX_TOOL_ROUNDS = 3

SYSTEM_INSTRUCTIONS = """You are NHL Intelligence, a concise hockey analyst.
Use only the supplied dashboard data and tool results. Do not invent game events, injuries, line combinations, or facts absent from the context. You have no injury, lineup, or transaction data: if asked whether someone is injured, healthy, scratched, or traded, say you don't have that information, and don't infer health from games played. On a game page you get that game's box score (scoring summary, three stars, team and player stats) but no play-by-play; on other pages you get season-level data only, so if asked what happened in a specific game there, say to open that game's page. League context lists only the top leaders, not every player. Write player names exactly as they appear in the data; never expand an initial into a first name. Explain statistics in plain language, distinguish facts from reasonable inferences, and keep answers under 220 words."""


def today_eastern() -> str:
    """The date fans mean by "today" and "tonight" (NHL schedules are Eastern)."""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    return datetime.now(ZoneInfo("America/New_York")).strftime("%A, %B %-d, %Y")


def _echo(call) -> dict:
    """
    A tool call exactly as the provider sent it, extra fields included:
    Gemini attaches a "thought signature" (extra_content) to each call and
    rejects the follow-up request (HTTP 400) if it isn't sent back.
    """
    if hasattr(call, "model_dump"):
        return call.model_dump(exclude_none=True)
    return {"id": call.id, "type": "function", "function": {"name": call.function.name, "arguments": call.function.arguments}}


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
        return await self.dashboard.league_summary()

    def prompt_for(self, request: ChatRequest, context: ContextBundle) -> str:
        facts = json.dumps(context.facts, default=str, separators=(",", ":"))
        if len(facts) > self.settings.max_context_chars:
            # Safety net only: the compact contexts are sized to fit well under this.
            logger.warning("Context for %s is %d chars; truncating", request.context.page, len(facts))
            facts = facts[: self.settings.max_context_chars] + "\n[Dashboard context truncated to control usage.]"
        return (
            f"Today is {today_eastern()} (US Eastern).\n\n"
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

    async def run_agent(self, request: ChatRequest):
        """
        The agent loop. The model sees the page data and the tools; each round
        it either answers or asks for tools, which run here (in parallel) and
        go back to it as results. Yields ("tool", label) while working,
        ("tool_result", name, arguments, result) as each finishes (for evals
        and tracing), then ("answer", text, provider, evidence).
        """
        context = await self._context(request)
        runner = ToolRunner(self.dashboard)
        messages = [
            {"role": "system", "content": SYSTEM_INSTRUCTIONS + TOOL_INSTRUCTIONS},
            *request.trimmed_history(),
            {"role": "user", "content": self.prompt_for(request, context)},
        ]
        evidence = list(context.evidence)
        start = 0
        for round_number in range(MAX_TOOL_ROUNDS + 1):
            last_round = round_number == MAX_TOOL_ROUNDS
            if last_round:
                messages.append({"role": "user", "content": "Answer now using the results you have; no more tools."})
            message, provider, start = await self.chain.complete_with_tools(
                messages, None if last_round else TOOLS, self.settings.max_output_tokens, start=start,
            )
            calls = [] if last_round else list(message.tool_calls or [])
            if not calls:
                yield ("answer", (message.content or "").strip(), provider, evidence)
                return
            messages.append({"role": "assistant", "content": message.content, "tool_calls": [_echo(c) for c in calls]})
            for call in calls:
                status, source = LABELS.get(call.function.name, ("Looking that up", "Dashboard data"))
                yield ("tool", status)
                if not any(e["label"] == source for e in evidence):
                    evidence.append({"label": source, "endpoint": f"tool:{call.function.name}"})
            results = await asyncio.gather(*(runner.run(c.function.name, c.function.arguments) for c in calls))
            messages.extend({"role": "tool", "tool_call_id": c.id, "content": r} for c, r in zip(calls, results))
            for c, r in zip(calls, results):
                yield ("tool_result", c.function.name, c.function.arguments, r)

    async def answer(self, request: ChatRequest) -> ChatResponse:
        try:
            async for event in self.run_agent(request):
                if event[0] == "answer":
                    _, text, provider, evidence = event
                    return ChatResponse(answer=text, evidence=[Evidence(**e) for e in evidence], model=provider.label)
        except AllProvidersFailed as exc:
            raise HTTPException(status_code=503, detail=ALL_BUSY) from exc
        raise HTTPException(status_code=503, detail=ALL_BUSY)

    async def answer_stream(self, request: ChatRequest):
        """Server-sent events: a status line per tool while the agent works, then the answer."""
        error = None
        try:
            async for event in self.run_agent(request):
                if event[0] == "tool":
                    yield f"data: {json.dumps({'type': 'status', 'text': event[1] + '…'})}\n\n"
                elif event[0] == "answer":
                    _, text, provider, evidence = event
                    yield f"data: {json.dumps({'type': 'delta', 'text': text})}\n\n"
                    yield f"data: {json.dumps({'type': 'done', 'evidence': evidence, 'model': provider.label})}\n\n"
        except HTTPException as exc:  # not configured, or the dashboard is down
            error = exc.detail
        except AllProvidersFailed:
            error = ALL_BUSY
        except OpenAIError:
            logger.exception("AI provider failed mid-answer")
            error = MID_ANSWER_FAILURE
        if error:
            yield f"data: {json.dumps({'type': 'error', 'message': error})}\n\n"


    async def write_digest(self, facts: dict) -> DigestResponse:
        if not self.chain:
            raise HTTPException(status_code=503, detail=NOT_CONFIGURED)
        text = json.dumps(facts, default=str, separators=(",", ":"))
        if len(text) > MAX_DIGEST_FACTS_CHARS:
            raise HTTPException(status_code=413, detail="Too many facts for one digest.")
        messages = [{"role": "system", "content": DIGEST_INSTRUCTIONS}, {"role": "user", "content": f"Facts (JSON): {text}"}]
        try:
            # Reasoning models (Groq's gpt-oss) think from the same budget they
            # write from: at 600 tokens the digest came back empty, and cutting
            # reasoning effort instead made the evals catch it garbling facts.
            message, provider, _ = await self.chain.complete_with_tools(messages, None, DIGEST_MAX_TOKENS)
        except AllProvidersFailed as exc:
            raise HTTPException(status_code=503, detail=ALL_BUSY) from exc
        return DigestResponse(text=(message.content or "").strip(), model=provider.label)


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
    return {
        "status": "ok",
        "commit": os.getenv("GIT_SHA") or "unknown",
        "providers": [p.name for p in app.state.intelligence.settings.providers]
        if hasattr(app.state, "intelligence") else [],
    }


@app.post("/digest/write", response_model=DigestResponse)
@limiter.limit("10/hour")
async def digest_write(payload: DigestRequest, request: Request):
    """
    Write the morning digest from the daily job's facts. Private: requires
    the shared X-Digest-Token, so nobody else can spend the AI budget here.
    """
    expected = request.app.state.intelligence.settings.digest_token
    if not expected:
        raise HTTPException(status_code=503, detail="Digest writing isn't configured.")
    if not hmac.compare_digest(request.headers.get("X-Digest-Token", ""), expected):
        raise HTTPException(status_code=401, detail="Unauthorized.")
    return await request.app.state.intelligence.write_digest(payload.facts)


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
