"""
NHL Stats Dashboard — API layer

A thin FastAPI service that reads from the standings_snapshots table
and serves it up as JSON, ready for a frontend to consume.

Setup:
    pip install -r requirements.txt

Run locally:
    uvicorn api:app --reload

Then visit http://127.0.0.1:8000/docs for interactive API docs (FastAPI
generates this automatically from the code below).
"""

import asyncio
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
import json
import os
import re
import threading
import time
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
from typing import List, Literal, Optional

import psycopg2
import psycopg2.errors
import requests
import psycopg2.extras
import sentry_sdk
from dotenv import load_dotenv
from pydantic import TypeAdapter
from fastapi import FastAPI, HTTPException, Path, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse, Response
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from logging_config import setup_logging
from response_models import (
    RootResponse,
    HealthResponse,
    Team,
    PlayoffOdds,
    PlayoffOddsHistory,
    RosterPlayer,
    PlayerLeader,
    PlayerLeaderTableRow,
    PlayerDetail,
    StandingsLatestRow,
    StandingsHistoryRow,
    SeasonFinalStanding,
)
import bets
import draft_board
import lottery
import report_card
import og_image
import projected_lineups
import push
from daily_cache import cache as daily_cache, daily_cached
import goal_model
import season_scenarios
import win_probability
from seasons import season_games
from response_models.pickem import PickemJoinIn, PickemMeIn, PickemPickIn
from response_models.push import PushSubscriptionIn, PushUnsubscribeIn
from prediction_record import track_record
import news
from nhl_games import (NHLGamesUnavailable, game_boxscore, game_play_by_play, games_on_date, month_calendar,
                       team_schedule, today_games)

load_dotenv()

# Deliberately separate from DATABASE_URL (used by the ingestion scripts,
# which need write access): the API only ever reads, so it connects with
# a least-privilege read-only Postgres role (nhl_api_readonly) instead.
# Fail loudly at startup rather than falling back to DATABASE_URL -- a
# silent fallback here would quietly hand the API owner-level credentials
# again, defeating the whole point of the split.
API_DATABASE_URL = os.environ.get("API_DATABASE_URL")
if not API_DATABASE_URL:
    raise RuntimeError(
        "API_DATABASE_URL is not set. api.py connects with a read-only DB role, "
        "separate from the owner-level DATABASE_URL used by the ingestion scripts -- "
        "set API_DATABASE_URL in your .env (see .env.example)."
    )

# Error tracking (Sentry) is optional, unlike API_DATABASE_URL above --
# a missing SENTRY_DSN just means errors aren't reported anywhere, not a
# broken deployment, so this degrades quietly instead of raising. Must
# run before the FastAPI app is constructed (Sentry's FastAPI/Starlette
# integration auto-enables at init time since both packages are
# installed -- see sentry_sdk.integrations._AUTO_ENABLING_INTEGRATIONS).
# Only 5xx responses are reported by default; expected 4xx responses
# (404s, 422 validation errors, 429 rate limits) are not treated as errors.
SENTRY_DSN = os.environ.get("SENTRY_DSN")
if SENTRY_DSN:
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        environment=os.environ.get("SENTRY_ENVIRONMENT", "development"),
        # Same commit GET /health reports, so each error is tied to a deploy.
        release=os.environ.get("GIT_SHA") or None,
        traces_sample_rate=0.1,
    )

# Azure Container Apps already captures stdout/stderr, and the container's
# filesystem is ephemeral, so skip the rotating file handler here -- just
# reuse the same shared setup with file logging disabled.
logger = setup_logging(__name__, log_to_file=False)

# Ingestion (ingest_standings.py) runs on a schedule outside this process
# (an Azure Container Apps Job `nhl-standings-ingest`, not something api.py ever calls --
# see the architecture note in the top-level README) -- so there's no
# in-process signal if it silently stops running. This periodic check is
# the one exception to "api.py only reads on request": once an hour it
# reads MAX(created_at) off standings_snapshots and logs an ERROR line if
# it's older than INGESTION_STALE_THRESHOLD_HOURS, the same
# scanned-for-a-traceback mechanism already used for
# nhl-api-startup-crash (see backend/README.md) picks the line up from
# Container Apps' console logs and fires the same email alert.
# Baked into the image at build time (Dockerfile ARG), reported by /health.
GIT_SHA = os.environ.get("GIT_SHA") or "unknown"

INGESTION_STALE_THRESHOLD_HOURS = float(os.environ.get("INGESTION_STALE_THRESHOLD_HOURS") or "30")
INGESTION_FRESHNESS_CHECK_INTERVAL_SECONDS = 60 * 60


def as_utc(dt):
    """
    created_at is TIMESTAMP (no time zone) -- psycopg2 hands back a naive
    datetime for it, which NOW() on this server stores in UTC. Attach
    that explicitly so it's comparable to a timezone-aware "now"
    (subtracting naive from aware raises TypeError -- caught the hard
    way against real data). A None input (no rows at all) passes through
    unchanged; an already-aware datetime is left alone too.
    """
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def compute_staleness(last_updated, now, threshold_hours):
    """
    Pure staleness calculation, kept separate from the DB/logging side
    effects below so it's trivially unit-testable. last_updated=None
    (no rows at all yet) counts as stale with hours_old=None.
    """
    if last_updated is None:
        return True, None
    hours_old = (now - last_updated).total_seconds() / 3600
    return hours_old > threshold_hours, hours_old


async def check_ingestion_freshness_loop():
    last_seen = None
    while True:
        try:
            conn = get_connection()
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT MAX(created_at) AS last_updated FROM standings_snapshots")
                    last_updated = as_utc(cur.fetchone()["last_updated"])
            finally:
                conn.close()

            # New standings rows mean the daily ingest has run: drop cached
            # responses now rather than waiting out their TTL.
            if last_seen is not None and last_updated != last_seen:
                daily_cache.clear()
                logger.info("New ingest detected -- cleared the daily response cache")
            last_seen = last_updated

            is_stale, hours_old = compute_staleness(
                last_updated, datetime.now(timezone.utc), INGESTION_STALE_THRESHOLD_HOURS
            )
            if is_stale:
                age_desc = "no rows at all" if hours_old is None else f"{hours_old:.1f}h ago"
                logger.error(
                    f"STALE_INGESTION: standings_snapshots last updated {age_desc} "
                    f"(threshold {INGESTION_STALE_THRESHOLD_HOURS}h) -- "
                    f"ingest_standings.py may not be running"
                )
            else:
                logger.info(f"Ingestion freshness check OK -- last standings update {hours_old:.1f}h ago")
        except Exception:
            logger.error("Ingestion freshness check itself failed", exc_info=True)

        await asyncio.sleep(INGESTION_FRESHNESS_CHECK_INTERVAL_SECONDS)


FANTASY_POLL_SECONDS = 3 * 60


FANTASY_UPDATE_COLUMNS = ("id", "player", "title", "summary", "url", "published", "source")


def load_fantasy_updates():
    """The last few days of saved RotoWire updates, into news.py's running list. Best effort."""
    since = datetime.now(timezone.utc) - news.MAX_UPDATE_AGE
    try:
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(f"SELECT {', '.join(FANTASY_UPDATE_COLUMNS)} FROM fantasy_updates WHERE published >= %s", (since,))
                rows = cur.fetchall()
        finally:
            conn.close()
    except Exception:
        logger.warning("Couldn't load saved fantasy updates; starting from RotoWire's latest", exc_info=True)
        return 0
    updates = [{**r, "published": news._iso(r["published"])} for r in rows]
    news.remember_fantasy_updates(updates)
    logger.info(f"Loaded {len(updates)} saved fantasy updates")
    return len(updates)


def store_fantasy_updates(updates):
    """Save new RotoWire updates (fantasy_updates). Best effort: a failure only costs them on the next restart."""
    try:
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                for u in updates:
                    cur.execute(
                        f"""
                        INSERT INTO fantasy_updates ({', '.join(FANTASY_UPDATE_COLUMNS)})
                        VALUES ({', '.join(['%s'] * len(FANTASY_UPDATE_COLUMNS))})
                        ON CONFLICT (id) DO NOTHING
                        """,
                        tuple(u[c] for c in FANTASY_UPDATE_COLUMNS),
                    )
        finally:
            conn.close()
    except Exception:
        logger.warning("Couldn't save fantasy updates", exc_info=True)


async def poll_fantasy_updates_loop():
    """
    RotoWire's feed holds only its latest 5 updates; polling keeps news.py's
    running list complete. Saved updates load first, so a restart picks up
    where the last one left off.
    """
    await asyncio.to_thread(load_fantasy_updates)
    while True:
        try:
            await asyncio.to_thread(news.poll_fantasy_updates, store=store_fantasy_updates)
        except Exception:
            logger.error("Fantasy update poll failed", exc_info=True)
        await asyncio.sleep(FANTASY_POLL_SECONDS)


@asynccontextmanager
async def lifespan(app: FastAPI):
    tasks = [asyncio.create_task(check_ingestion_freshness_loop()), asyncio.create_task(poll_fantasy_updates_loop())]
    yield
    for task in tasks:
        task.cancel()


app = FastAPI(
    title="NHL Stats Dashboard API",
    description="Serves NHL standings data collected from the NHL public API.",
    version="0.1.0",
    lifespan=lifespan,
)

# Coarse per-IP abuse/scraping guard. 60/minute is generous for normal
# frontend usage (a page load fires a handful of requests, well under
# this in any burst) while still bounding a naive scraper hammering the
# API. The two join-heavy endpoints (player_leaders, playoff_odds) get a
# tighter override below via @limiter.limit(...) -- retune either string
# here if real usage patterns call for it.
DEFAULT_RATE_LIMIT = "60/minute"
EXPENSIVE_RATE_LIMIT = "20/minute"

def client_ip(request: Request) -> str:
    """
    The caller's IP, for rate limits. Behind Azure Container Apps every
    request arrives from the ingress proxy (100.100.x.x), so keying on the
    socket address put every visitor in a handful of shared buckets (a few
    people could use up everyone's AI and sign-up allowance). The proxy
    appends the real client IP to X-Forwarded-For, so the rightmost entry is
    the one to trust; anything left of it is whatever the client sent, and
    keying on that would let anyone dodge limits by making it up.
    """
    forwarded = request.headers.get("x-forwarded-for", "")
    hops = [h.strip() for h in forwarded.split(",") if h.strip()]
    return hops[-1] if hops else get_remote_address(request)


# key_style="endpoint" (rather than slowapi's default "url") scopes each
# limit bucket to the route *handler*, not the literal request path -- so
# e.g. /standings/PIT and /standings/BOS share one bucket per client
# instead of each path parameter value getting its own fresh allowance,
# which would otherwise let someone bypass the limit just by cycling
# through team abbreviations or player ids.
limiter = Limiter(key_func=client_ip, default_limits=[DEFAULT_RATE_LIMIT], key_style="endpoint")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
# Added before CORSMiddleware so CORS ends up as the outermost layer
# (Starlette wraps middleware in reverse registration order) -- otherwise
# a 429 response would be missing Access-Control-Allow-Origin, and the
# browser would surface it to the frontend as an opaque CORS/network
# failure instead of a readable rate-limit response.
app.add_middleware(SlowAPIMiddleware)

# /players/leaders is ~1.18 MB of JSON and ~91 KB gzipped (full view);
# ?view=table (the Players page) is ~0.5 MB raw / ~34 KB gzipped.
app.add_middleware(GZipMiddleware, minimum_size=1000)

# Data that changes once a day (after the 2 AM run) can be cached by the
# browser for a few minutes, and served stale while it refreshes. Live data
# (games, schedules, scenarios) is left alone.
DAILY_DATA_PREFIXES = ("/standings", "/playoff-odds", "/playoff-line", "/players", "/teams", "/season-sim", "/predictions", "/digest",
                       "/news", "/injuries", "/transactions", "/fantasy")  # news is cached ~15 min upstream anyway
DAILY_CACHE_CONTROL = "public, max-age=300, stale-while-revalidate=3600"


def _daily_cacheable(path):
    if path.startswith("/teams/") and not path.endswith("/roster"):
        return False  # /teams/{abbrev}/schedule is live
    if path.startswith("/season-sim/"):
        return False
    return path.startswith(DAILY_DATA_PREFIXES)


@app.middleware("http")
async def daily_cache_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")  # JSON is never sniffed as HTML
    if request.method == "GET" and response.status_code == 200 and _daily_cacheable(request.url.path):
        response.headers.setdefault("Cache-Control", DAILY_CACHE_CONTROL)
    return response

# Only the deployed frontend (and local dev) can call this API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://puckpulse.io",
        "https://www.puckpulse.io",
        "https://ashy-sky-01e4eba1e.7.azurestaticapps.net",  # Azure's default address, still served
        "http://localhost:5173",  # local Vite dev server
    ],
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type", "Accept"],
)


# Connection pool. Opening a Neon connection costs ~0.5s (TLS + auth), more
# than most queries, so connections are reused. Neon drops idle ones after
# about 5 minutes (and suspends the database), so anything idle longer than
# POOL_IDLE_SECONDS is thrown away instead of reused.
#
# Connections are autocommit: the database is in AWS us-east-1 and the API
# in Azure West US 2, so every round trip crosses the country, and a
# transaction's separate BEGIN and ROLLBACK tripled them. The API only
# reads, plus single-statement push-subscription writes.
POOL_MAX_IDLE = 8
POOL_IDLE_SECONDS = 240
_pool: list = []          # (connection, returned_at), most recent last
_pool_lock = threading.Lock()


class PooledConnection:
    """A psycopg2 connection whose close() returns it to the pool."""

    def __init__(self, conn):
        self._conn = conn

    def __getattr__(self, name):
        return getattr(self._conn, name)

    def __enter__(self):
        self._conn.__enter__()
        return self

    def __exit__(self, *exc):
        return self._conn.__exit__(*exc)

    def close(self):
        conn, self._conn = self._conn, None
        if conn is None or conn.closed:
            return
        if conn.info.transaction_status != psycopg2.extensions.TRANSACTION_STATUS_IDLE:
            conn.close()  # broken (UNKNOWN), or mid-transaction: don't hand it to the next request
            return
        with _pool_lock:
            if len(_pool) < POOL_MAX_IDLE:
                _pool.append((conn, time.monotonic()))
                return
        conn.close()


def _checkout():
    """A pooled connection fresh enough to trust, or None."""
    now = time.monotonic()
    with _pool_lock:
        while _pool:
            conn, returned_at = _pool.pop()
            if not conn.closed and now - returned_at < POOL_IDLE_SECONDS:
                return conn
            try:
                conn.close()
            except psycopg2.Error:
                pass
    return None


def get_connection():
    conn = _checkout()
    if conn is not None:
        return PooledConnection(conn)
    try:
        conn = psycopg2.connect(API_DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)
        conn.autocommit = True
        return PooledConnection(conn)
    except Exception:
        logger.error("Failed to connect to the database", exc_info=True)
        raise


@app.get("/", response_model=RootResponse)
def root():
    return {"status": "ok", "message": "NHL Stats Dashboard API is running", "version": "0.1.0"}


@app.get("/health", response_model=HealthResponse)
@limiter.exempt
def health():
    """
    Actually exercises the database connection (unlike GET /), for Azure
    Container Apps' liveness/readiness probes and any external uptime
    monitor -- both of which may poll far more often than the 60/minute
    default rate limit, hence the exemption.

    Note: get_connection() itself is inside the try block here, unlike
    every other endpoint in this file -- elsewhere a connection failure
    is allowed to bubble up as a plain 500, but the entire point of this
    endpoint is to turn "can't connect" into a clean, deliberate 503
    rather than a generic error.
    """
    conn = None
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
    except Exception:
        logger.error("Health check failed: database unreachable", exc_info=True)
        raise HTTPException(status_code=503, detail="Database unreachable")
    finally:
        if conn:
            conn.close()
    return {"status": "ok", "database": "connected", "commit": GIT_SHA}


@app.get("/games/today")
def games_today():
    """Live, scheduled, and completed NHL games for today."""
    try:
        return {"games": today_games()}
    except NHLGamesUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/games/date/{game_date}")
def games_by_date(game_date: date):
    """NHL games for a specific calendar date, useful for historical lookup."""
    try:
        return {"games": games_on_date(game_date)}
    except NHLGamesUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/games/calendar/{year_month}")
def games_calendar(year_month: str = Path(..., pattern=r"^\d{4}-(0[1-9]|1[0-2])$")):
    """
    Season bounds and per-day game counts for one month (YYYY-MM), for the
    Scores page's date picker: only days with games in the current season
    are selectable.
    """
    year, month = (int(part) for part in year_month.split("-"))
    try:
        return month_calendar(year, month)
    except NHLGamesUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/games/{game_id}/boxscore")
def game_box_score(game_id: int = Path(..., gt=0)):
    """Detailed NHL gamecenter box score for a selected game."""
    try:
        return game_boxscore(game_id)
    except NHLGamesUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def _team_names():
    return daily_cache.get_or_compute(("team_names",), lambda: _query_team_names())


def _query_team_names():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT team_abbrev, team_name FROM teams")
            return {r["team_abbrev"]: r["team_name"] for r in cur.fetchall()}
    finally:
        conn.close()


def _lineup(game_id, away, home, day):
    """NHL.com's projected lineup for a game (projected_lineups.py), or None before it's posted. Cached 10 minutes."""
    def fetch():
        names = _team_names()
        if away not in names or home not in names:
            return None
        try:
            return projected_lineups.lineup(names[away], names[home], day)
        except requests.RequestException:
            logger.warning(f"NHL.com lineup for {game_id} unavailable", exc_info=True)
            return None
    return daily_cache.get_or_compute(("lineup", game_id), fetch)


@app.get("/games/{game_id}/lineup")
def game_lineup(game_id: int = Path(..., gt=0)):
    """
    Tonight's projected lineups from NHL.com for one game: each team's
    forward lines, defense pairs, goalies (the projected starter first),
    scratches, and injuries. {"available": false} until NHL.com posts them,
    a few hours before puck drop.
    """
    try:
        game = game_boxscore(game_id)
    except NHLGamesUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    away, home = (game.get("awayTeam") or {}).get("abbrev"), (game.get("homeTeam") or {}).get("abbrev")
    try:
        day = date.fromisoformat(str(game.get("gameDate")))
    except ValueError:
        return {"available": False}
    found = _lineup(game_id, away, home, day)
    if not found:
        return {"available": False}
    return {"available": True, "source": "NHL.com", "url": found["url"], "published": found["published"],
            "away": {"abbrev": away, **found["away"]}, "home": {"abbrev": home, **found["home"]}}


def _pregame_goals(game_id):
    """(home win prob, home goals, away goals) logged before the game, or None."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT home_win_prob, home_goals, away_goals FROM game_predictions WHERE game_id = %s", (game_id,))
            row = cur.fetchone()
    finally:
        conn.close()
    if not row:
        return None
    half = goal_model.LEAGUE_TOTAL / 2
    return (float(row["home_win_prob"]), float(row["home_goals"] or half), float(row["away_goals"] or half))


@app.get("/games/{game_id}/win-probability")
def game_win_probability(game_id: int = Path(..., gt=0)):
    """
    The home team's chance to win through the game (win_probability.py):
    {"available", "points": [[game second, P(home)]], "goals": [...],
    "swing": the goal that moved it most}. Starts at the pregame chance we
    logged; {"available": false} for games we didn't predict or that
    haven't started. Updates with the play-by-play (cached 15s while live).
    """
    try:
        return _win_curve(game_id)
    except NHLGamesUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def _win_curve(game_id):
    """game_win_probability's result. Raises NHLGamesUnavailable."""
    pbp = game_play_by_play(game_id)
    if pbp.get("gameState") in ("FUT", "PRE") or not pbp.get("plays"):
        return {"available": False}
    pregame = daily_cache.get_or_compute(("pregame_goals", game_id), lambda: _pregame_goals(game_id))
    if not pregame:
        return {"available": False}

    def compute():
        prob, home_goals, away_goals = pregame
        playoff = pbp.get("gameType") == 3
        home_mu, away_mu = win_probability.anchor(home_goals, away_goals, prob, playoff)
        curve = win_probability.series(pbp, home_mu, away_mu, playoff)
        return {"available": True, "pregame": prob, "playoff": playoff, **curve,
                "swing": win_probability.biggest_swing(curve["goals"])}

    key = ("win_probability", game_id, pbp.get("gameState"), len(pbp["plays"]), pbp["plays"][-1].get("eventId"))
    return daily_cache.get_or_compute(key, compute)


def _share_curve(game):
    """The win probability curve for a live or final game's preview, or None (it's optional there)."""
    if game.get("gameState") not in ("LIVE", "CRIT", "FINAL", "OFF"):
        return None
    try:
        return _win_curve(game["id"])
    except NHLGamesUnavailable:
        return None


def _share_game(game_id):
    """(NHL game dict, the logged home-win chance or None) for a game's link preview."""
    try:
        game = game_boxscore(game_id)
    except NHLGamesUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if not (game.get("awayTeam") or {}).get("abbrev"):
        raise HTTPException(status_code=404, detail="No such game")
    prob = None
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT home_win_prob FROM game_predictions WHERE game_id = %s", (game_id,))
            row = cur.fetchone()
            prob = float(row["home_win_prob"]) if row else None
    finally:
        conn.close()
    return game, prob


@app.get("/og/game/{game_id}.png")
def game_preview_image(game_id: int = Path(..., gt=0)):
    """The game's link preview image (og_image.py): win chances before it, the score once it's on. 1200x630 PNG."""
    game, prob = _share_game(game_id)
    curve = _share_curve({**game, "id": game_id})
    last = curve["points"][-1] if curve and curve.get("points") else None
    key = ("og", game_id, game.get("gameState"), game["awayTeam"].get("score"), game["homeTeam"].get("score"), prob, last)
    png = daily_cache.get_or_compute(key, lambda: og_image.render_game(game, prob, curve))
    return Response(content=png, media_type="image/png", headers={"Cache-Control": "public, max-age=600"})


@app.get("/games/{game_id}/share")
def game_share(game_id: int = Path(..., gt=0)):
    """Title, description, and image for a game's link preview (served by the site's /g/{id} share page)."""
    game, prob = _share_game(game_id)
    title, description = og_image.share_text(game, prob, _share_curve({**game, "id": game_id}))
    return {"title": title, "description": description, "url": f"https://puckpulse.io/games/{game_id}",
            "image": f"https://nhl-dashboard-api.bravecoast-a5240643.westus2.azurecontainerapps.io/og/game/{game_id}.png"}


@app.get("/teams/{team_abbrev}/share")
def team_share(team_abbrev: str = Path(..., pattern=r"^[A-Za-z]{3}$")):
    """Title and description for a team's link preview (served by the site's /t/{abbrev} share page)."""
    abbrev = team_abbrev.upper()
    if abbrev not in og_image.TEAM_COLORS:
        raise HTTPException(status_code=404, detail="No such team")
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT t.team_name, s.wins, s.losses, s.ot_losses, s.points
                FROM teams t
                LEFT JOIN standings_snapshots s ON s.team_abbrev = t.team_abbrev
                    AND s.snapshot_date = (SELECT MAX(snapshot_date) FROM standings_snapshots)
                WHERE t.team_abbrev = %s
                """,
                (abbrev,),
            )
            team = cur.fetchone()
            cur.execute(
                """
                SELECT playoff_pct FROM playoff_odds
                WHERE team_abbrev = %s
                  AND season_id = (SELECT MAX(season_id) FROM playoff_odds)
                ORDER BY as_of_date DESC LIMIT 1
                """,
                (abbrev,),
            )
            odds = cur.fetchone()
    finally:
        conn.close()
    if not team:
        raise HTTPException(status_code=404, detail="No such team")
    title, description = og_image.team_share_text(
        abbrev, team, float(odds["playoff_pct"]) if odds and odds.get("playoff_pct") is not None else None
    )
    return {"title": title, "description": description, "url": f"https://puckpulse.io/teams/{abbrev}"}


@app.get("/teams/{team_abbrev}/schedule")
def team_schedule_summary(team_abbrev: str = Path(..., pattern=r"^[A-Za-z]{3}$")):
    """
    One team's live game (if any), last 5 results, and next 3 games this
    season, from the NHL's club schedule (cached; see nhl_games.py). Powers
    the "My team" card.
    """
    try:
        return team_schedule(team_abbrev)
    except NHLGamesUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/teams", response_model=List[Team])
@daily_cached
def list_teams():
    """List all teams we have data for."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM teams ORDER BY team_name")
            return cur.fetchall()
    except Exception:
        logger.error("Failed to fetch teams", exc_info=True)
        raise
    finally:
        conn.close()


@app.get("/playoff-odds", response_model=List[PlayoffOdds])
@limiter.limit(EXPENSIVE_RATE_LIMIT)
@daily_cached
def playoff_odds(request: Request):
    """
    Monte Carlo playoff-odds simulation results for every team, as of the
    most recently computed snapshot. See simulate_playoff_odds.py.
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT po.*, t.team_name, t.division, t.conference, t.logo_url
                FROM playoff_odds po
                JOIN teams t ON t.team_abbrev = po.team_abbrev
                WHERE po.as_of_date = (SELECT MAX(as_of_date) FROM playoff_odds WHERE season_id = po.season_id)
                  AND po.season_id = (SELECT MAX(season_id) FROM playoff_odds)
                ORDER BY po.playoff_pct DESC
                """
            )
            return cur.fetchall()
    except Exception:
        logger.error("Failed to fetch playoff odds", exc_info=True)
        raise
    finally:
        conn.close()


@app.get("/playoff-odds/history", response_model=PlayoffOddsHistory)
@limiter.limit(EXPENSIVE_RATE_LIMIT)
@daily_cached
def playoff_odds_history(request: Request, season_id: Optional[int] = Query(None, ge=19171918, le=99999999)):
    """
    Every odds snapshot for one season (default: the latest season with
    odds), oldest first -- one point per team per simulated day. Also lists
    which seasons have odds, so the page can offer a season switch.
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT DISTINCT season_id FROM playoff_odds ORDER BY season_id DESC")
            seasons = [row["season_id"] for row in cur.fetchall()]
            if season_id is None:
                season_id = seasons[0] if seasons else None
            points = []
            if season_id in seasons:
                cur.execute(
                    """
                    SELECT as_of_date, team_abbrev, playoff_pct
                    FROM playoff_odds
                    WHERE season_id = %s
                    ORDER BY as_of_date, team_abbrev
                    """,
                    (season_id,),
                )
                points = cur.fetchall()
            return {"season_id": season_id, "available_seasons": seasons, "points": points}
    except Exception:
        logger.error("Failed to fetch playoff odds history", exc_info=True)
        raise
    finally:
        conn.close()


@app.get("/season-sim")
@limiter.limit(EXPENSIVE_RATE_LIMIT)
@daily_cached
def season_sim_inputs(request: Request):
    """
    Inputs for the in-browser season simulator, for the latest season: the
    game model's constants, each team's record and strength rating, and the
    remaining schedule. Written by the daily simulate_playoff_odds.py run.
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT payload FROM season_sim_inputs ORDER BY season_id DESC LIMIT 1")
            row = cur.fetchone()
    except Exception:
        logger.error("Failed to fetch season simulator inputs", exc_info=True)
        raise
    finally:
        conn.close()
    if row is None:
        raise HTTPException(status_code=404, detail="The season simulator hasn't run yet.")
    # Player values are for the roster-change endpoint; the browser doesn't need them.
    return {k: v for k, v in row["payload"].items() if k != "players"}


@app.get("/playoff-odds/why")
@daily_cached
def playoff_odds_why():
    """
    "Why these odds?": each team's rating split into this season's goals,
    this season's xG, and last season's carryover (all in goals/game, adding
    up to the rating), plus how its remaining schedule helps or hurts. From
    the latest daily run; see simulate_playoff_odds.odds_explanations().
    """
    payload = _latest_sim_inputs()
    return {
        "season_id": payload["season_id"],
        "as_of_date": payload["as_of_date"],
        "model_version": payload.get("model", {}).get("version"),
        "teams": payload.get("why", {}),
    }


def _fallback_cutline(teams, full_season):
    """
    No simulated line (an older payload): project the current last wild card
    in each conference to a full season (`full_season` games) at its points %. Pure arithmetic on the
    payload -- no queries. Returns {conference: {p25, p50, p75}} (all equal,
    there's no spread) or {} if no team has played yet.
    """
    by_conf = {}
    for abbrev, t in teams.items():
        by_conf.setdefault(t["conference"], []).append(t)
    out = {}
    for conf, conf_teams in by_conf.items():
        ranked = sorted(conf_teams, key=lambda t: (-t["points"], -t.get("regulation_wins", 0), -t["wins"]))
        if len(ranked) < 8:
            continue
        wc2 = ranked[7]  # 8th in points; close enough to the last playoff spot for a fallback
        gp = wc2["wins"] + wc2.get("losses", 0) + wc2.get("ot_losses", 0)
        if gp == 0:
            continue
        line = round(wc2["points"] / (2 * gp) * 2 * full_season)
        out[conf] = {"p25": line, "p50": line, "p75": line}
    return out


@app.get("/playoff-line")
@daily_cached
def playoff_line():
    """
    The playoff line (points of the last wild card at season's end) per
    conference from the latest daily sim -- median and p25-p75 range -- plus
    each team's record, for the "points pace" row on the My Team card.
    `source` is "sim", or "projection" when an older payload has no sim line
    (then p25 = p50 = p75). 404 before the first sim run. One small read of
    the latest sim payload; nothing is simulated per request.
    """
    payload = _latest_sim_inputs()
    teams = payload.get("teams", {})
    full_season = season_games(payload.get("season_id"))
    # Each team's games still to play, from the remaining schedule (exact even
    # with postponements, unlike season length minus games played).
    games_left = {}
    for _, home, away, *_ in payload.get("games", []):
        games_left[home] = games_left.get(home, 0) + 1
        games_left[away] = games_left.get(away, 0) + 1
    cutline = payload.get("cutline") or {}
    source = "sim"
    if not cutline:
        cutline = _fallback_cutline(teams, full_season)
        source = "projection" if cutline else None
    out_teams = {}
    for abbrev, t in teams.items():
        gp = t["wins"] + t.get("losses", 0) + t.get("ot_losses", 0)
        out_teams[abbrev] = {
            "conference": t["conference"],
            "gp": gp,
            "pts": t["points"],
            "otl": t.get("ot_losses", 0),
            "point_pctg": round(t["points"] / (2 * gp), 4) if gp else None,
            "games_left": games_left.get(abbrev, 0),
        }
    return {
        "season_id": payload.get("season_id"),
        "as_of_date": payload.get("as_of_date"),
        "games_remaining": len(payload.get("games", [])),
        "season_games": full_season,
        "source": source,
        "cutline": cutline,
        "teams": out_teams,
    }


@app.get("/digest/latest")
@daily_cached
def latest_digest():
    """
    The most recent morning digest: AI-written text (or null if the AI was
    unavailable), the facts it was written from, and which model wrote it.
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT digest_date, text, model, facts, created_at FROM daily_digest ORDER BY digest_date DESC LIMIT 1")
            row = cur.fetchone()
    except Exception:
        logger.error("Failed to fetch the digest", exc_info=True)
        raise
    finally:
        conn.close()
    if row is None:
        raise HTTPException(status_code=404, detail="No digest yet.")
    return row


@app.get("/predictions/track-record")
@daily_cached
def prediction_track_record():
    """
    How the model's game predictions have done this season: how often its
    favorite won, its Brier score against a coin flip, calibration buckets,
    and the most recent graded games. See game_predictions.py.
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT game_id, game_date, home_abbrev, away_abbrev, home_win_prob, home_score, away_score, "
                "ended, home_won, model_version, source FROM game_predictions "
                "WHERE season_id = (SELECT MAX(season_id) FROM game_predictions)"
            )
            rows = cur.fetchall()
            cur.execute("SELECT COUNT(*) AS n FROM game_predictions WHERE home_won IS NULL "
                        "AND season_id = (SELECT MAX(season_id) FROM game_predictions)")
            pending = cur.fetchone()["n"]
    except Exception:
        logger.error("Failed to fetch the prediction track record", exc_info=True)
        raise
    finally:
        conn.close()
    return {**track_record(rows), "pending": pending}


# "What if" simulations (NHL Intelligence's scenario tools). A few seconds of
# CPU each, so results are cached per day's inputs: the same question asked
# again (by anyone) is free until the next morning's run.
_SCENARIO_CACHE: OrderedDict = OrderedDict()
_SCENARIO_CACHE_SIZE = 256


def _latest_sim_inputs():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT payload FROM season_sim_inputs ORDER BY season_id DESC LIMIT 1")
            row = cur.fetchone()
    finally:
        conn.close()
    if row is None:
        raise HTTPException(status_code=404, detail="The season simulator hasn't run yet.")
    return row["payload"]


def _played_since_snapshot(payload, team):
    """
    The team's games that finished after the morning snapshot, from the live
    schedule (cached), as (date, home, away) -- so "its next 4 games" skips
    tonight's game once it's over. Best effort: if the NHL feed is down, the
    snapshot is used as is.
    """
    try:
        recent = team_schedule(team)["recent"]
    except NHLGamesUnavailable:
        return frozenset()
    return frozenset(
        (g["date"], team if g["home"] else g["opponent"], g["opponent"] if g["home"] else team)
        for g in recent if g["date"] >= payload["as_of_date"]
    )


def _cached_scenario(key, compute, team):
    payload = _latest_sim_inputs()
    played = _played_since_snapshot(payload, team.upper())
    key = (payload["as_of_date"], len(played), *key)
    if key in _SCENARIO_CACHE:
        _SCENARIO_CACHE.move_to_end(key)
        return _SCENARIO_CACHE[key]
    try:
        result = compute(payload, played)
    except season_scenarios.UnknownTeam as exc:
        raise HTTPException(status_code=404, detail=f"Unknown team '{exc}'.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _SCENARIO_CACHE[key] = result
    while len(_SCENARIO_CACHE) > _SCENARIO_CACHE_SIZE:
        _SCENARIO_CACHE.popitem(last=False)
    return result


@app.get("/season-sim/scenario")
@limiter.limit(EXPENSIVE_RATE_LIMIT)
def season_sim_scenario(
    request: Request,
    team: str = Query(..., pattern=r"^[A-Za-z]{3}$"),
    games: int = Query(..., ge=1, le=30),
    wins: int = Query(..., ge=0, le=30),
    ot_losses: int = Query(0, ge=0, le=30),
):
    """
    A team's playoff odds and projected points if it goes wins-losses(-OT)
    over its next `games`, next to its odds as things stand (same simulated
    seasons, so the difference is the scenario, not noise).
    """
    return _cached_scenario(
        ("scenario", team.upper(), games, wins, ot_losses),
        lambda payload, played: season_scenarios.scenario(payload, team, games, wins, ot_losses, played=played),
        team,
    )


@app.get("/season-sim/path")
@limiter.limit(EXPENSIVE_RATE_LIMIT)
def season_sim_path(
    request: Request,
    team: str = Query(..., pattern=r"^[A-Za-z]{3}$"),
    games: int = Query(10, ge=1, le=15),
):
    """A team's playoff odds for every possible record over its next `games`: what it needs."""
    return _cached_scenario(
        ("path", team.upper(), games),
        lambda payload, played: season_scenarios.playoff_path(payload, team, games, played=played),
        team,
    )


MOVE_PATTERN = r"^\d{7}:([A-Za-z]{3}|NONE)$"


@app.get("/season-sim/roster-change")
@limiter.limit(EXPENSIVE_RATE_LIMIT)
def season_sim_roster_change(
    request: Request,
    move: List[str] = Query(..., min_length=1, max_length=4, description="PLAYER_ID:TEAM, or PLAYER_ID:NONE if he's just gone"),
):
    """
    "What if they traded X?": each affected team's playoff odds with and
    without the moves, from player values in goals/game (player_values.py).
    A player moved to NONE leaves for an unknown return (or is out for the
    season); his minutes go to a replacement-level player.
    """
    for m in move:
        if not re.match(MOVE_PATTERN, m):
            raise HTTPException(status_code=422, detail=f"Bad move '{m}': use PLAYER_ID:TEAM or PLAYER_ID:NONE.")
    parsed = [(int(pid), None if to.upper() == "NONE" else to.upper()) for pid, to in (m.split(":") for m in move)]
    moves = tuple(sorted(parsed, key=lambda m: (m[0], m[1] or "")))
    if len({pid for pid, _ in moves}) != len(moves):
        raise HTTPException(status_code=422, detail="Each player can only move once.")
    payload = _latest_sim_inputs()
    key = (payload["as_of_date"], "roster", moves)
    if key in _SCENARIO_CACHE:
        _SCENARIO_CACHE.move_to_end(key)
        return _SCENARIO_CACHE[key]
    try:
        result = season_scenarios.roster_change(payload, list(moves))
    except season_scenarios.UnknownPlayer as exc:
        raise HTTPException(status_code=404, detail=f"No value for player {exc} (goalie, or not on a roster).") from exc
    except season_scenarios.UnknownTeam as exc:
        raise HTTPException(status_code=404, detail=f"Unknown team '{exc}'.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _SCENARIO_CACHE[key] = result
    while len(_SCENARIO_CACHE) > _SCENARIO_CACHE_SIZE:
        _SCENARIO_CACHE.popitem(last=False)
    return result


@app.get("/season-sim/injury")
@limiter.limit(EXPENSIVE_RATE_LIMIT)
def season_sim_injury(
    request: Request,
    player: int = Query(..., gt=0, description="The injured player's NHL id"),
    back: Optional[date] = Query(None, description="His expected return date; without it, only healthy vs. out for the season"),
):
    """
    What an injured player's return is worth: his team's playoff odds
    healthy now, back on `back` (missing the games before it), and out for
    the rest of the season (season_scenarios.injury_return). Not a trade:
    see /season-sim/roster-change for that.
    """
    payload = _latest_sim_inputs()
    key = (payload["as_of_date"], "injury", player, str(back) if back else None)
    if key in _SCENARIO_CACHE:
        _SCENARIO_CACHE.move_to_end(key)
        return _SCENARIO_CACHE[key]
    try:
        result = season_scenarios.injury_return(payload, player, str(back) if back else None)
    except season_scenarios.UnknownPlayer as exc:
        raise HTTPException(status_code=404, detail=f"No value for player {exc} (a goalie, or not on an NHL team).") from exc
    except season_scenarios.UnknownTeam as exc:
        raise HTTPException(status_code=404, detail=f"Unknown team '{exc}'.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _SCENARIO_CACHE[key] = result
    while len(_SCENARIO_CACHE) > _SCENARIO_CACHE_SIZE:
        _SCENARIO_CACHE.popitem(last=False)
    return result


# --- News ------------------------------------------------------------------
#
# Headlines (NHL.com, ESPN, Sportsnet), injuries, and transactions (ESPN),
# fetched live and cached per source in news.py. Headlines link out.

TEAM_FILTER = Query(None, pattern=r"^[A-Za-z]{3}$", description="Team abbreviation, e.g. PIT")


def _team_param(team):
    if team is None:
        return None
    team = team.upper()
    if team not in news.TEAMS:
        raise HTTPException(status_code=404, detail=f"Unknown team '{team}'.")
    return team


@app.get("/news")
def news_headlines(team: Optional[str] = TEAM_FILTER, limit: int = Query(20, ge=1, le=60)):
    """Recent NHL headlines, newest first, each with its source and a link to the original."""
    result = news.headlines(_team_param(team), limit)
    if not result["sources"]:
        raise HTTPException(status_code=503, detail="News sources are unavailable right now.")
    return result


@app.get("/injuries")
def news_injuries(team: Optional[str] = TEAM_FILTER):
    """Injured players by team (ESPN): status, injury, expected return, and a short note."""
    result = news.injuries(_team_param(team))
    if result is None:
        raise HTTPException(status_code=503, detail="Injury data is unavailable right now.")
    return result


@app.get("/transactions")
def news_transactions(team: Optional[str] = TEAM_FILTER, limit: int = Query(25, ge=1, le=100)):
    """Recent signings, trades, recalls, and IR moves (ESPN), newest first."""
    result = news.transactions(_team_param(team), limit)
    if result is None:
        raise HTTPException(status_code=503, detail="Transaction data is unavailable right now.")
    return result


@daily_cached
def _roster_players():
    """
    {news.player_key(name): (team, position code)} for players on a roster
    now. A name two players share maps to None: we can't tell them apart.
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT first_name, last_name, team_abbrev, position_code FROM players WHERE on_roster")
            rows = cur.fetchall()
    finally:
        conn.close()
    players = {}
    for r in rows:
        key = news.player_key(f"{r['first_name']} {r['last_name']}")
        players[key] = (r["team_abbrev"], r["position_code"]) if key not in players else None
    return players


def _roster_lookup():
    try:
        return _roster_players()
    except Exception:
        logger.warning("Couldn't load rosters for matching fantasy updates", exc_info=True)
        return {}


@app.get("/fantasy")
def fantasy_news(limit: int = Query(40, ge=1, le=150)):
    """Fantasy player updates (RotoWire) and fantasy articles (DobberHockey, RotoBaller), newest first. All link out."""
    players = _roster_lookup()
    result = news.fantasy(team_of=lambda name: (players.get(news.player_key(name)) or (None,))[0], limit=limit)
    if not result["sources"]:
        raise HTTPException(status_code=503, detail="Fantasy sources are unavailable right now.")
    return result


# --- Push notifications ------------------------------------------------------
#
# The only endpoints that write to the database. The API's role can change
# push_subscriptions and nothing else (see schema.sql).

SUBSCRIBE_RATE_LIMIT = "10/minute"


@app.get("/push/config")
def push_config():
    """The VAPID public key browsers need to subscribe (empty if push isn't set up)."""
    return {"vapid_public_key": push.VAPID_PUBLIC_KEY, "enabled": bool(push.VAPID_PUBLIC_KEY)}


@app.post("/push/subscriptions", status_code=204)
@limiter.limit(SUBSCRIBE_RATE_LIMIT)
def push_subscribe(request: Request, body: PushSubscriptionIn):
    """
    Save (or update) a browser's push subscription and the teams it
    follows. Only real browser push services are accepted as endpoints,
    and only known team abbreviations.
    """
    if not push.is_allowed_endpoint(body.endpoint):
        raise HTTPException(status_code=400, detail="Not a browser push service endpoint.")
    if not push.valid_keys(body.keys.p256dh, body.keys.auth):
        raise HTTPException(status_code=400, detail="Invalid subscription keys.")
    teams = sorted({t.upper() for t in body.teams})
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT team_abbrev FROM teams WHERE team_abbrev = ANY(%s)", (teams,))
            if len(cur.fetchall()) != len(teams):
                raise HTTPException(status_code=400, detail="Unknown team.")
            cur.execute(
                """
                INSERT INTO push_subscriptions (endpoint, p256dh, auth, teams, notify_goals, notify_finals)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (endpoint) DO UPDATE SET
                    p256dh = EXCLUDED.p256dh,
                    auth = EXCLUDED.auth,
                    teams = EXCLUDED.teams,
                    notify_goals = EXCLUDED.notify_goals,
                    notify_finals = EXCLUDED.notify_finals,
                    updated_at = NOW()
                """,
                (body.endpoint, body.keys.p256dh, body.keys.auth, teams, body.goals, body.finals),
            )
        conn.commit()
    except HTTPException:
        raise
    except Exception:
        logger.error("Failed to save push subscription", exc_info=True)
        raise
    finally:
        conn.close()


@app.delete("/push/subscriptions", status_code=204)
@limiter.limit(SUBSCRIBE_RATE_LIMIT)
def push_unsubscribe(request: Request, body: PushUnsubscribeIn):
    """Forget a subscription. The endpoint itself is the secret that proves ownership."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM push_subscriptions WHERE endpoint = %s", (body.endpoint,))
        conn.commit()
    except Exception:
        logger.error("Failed to delete push subscription", exc_info=True)
        raise
    finally:
        conn.close()


PICKEM_JOIN_RATE_LIMIT = "5/hour"
PICKEM_RATE_LIMIT = "60/minute"


def _pickem_player(cur, key):
    """The player for a key, or 401. Keys are compared by hash."""
    import pickem

    cur.execute("SELECT player_id, display_name FROM pickem_players WHERE key_hash = %s", (pickem.hash_key(key),))
    row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=401, detail="Unknown player key.")
    return row


def _pickem_tables_missing(exc):
    return isinstance(exc, (psycopg2.errors.UndefinedTable, psycopg2.errors.InsufficientPrivilege))


@app.post("/pickem/join")
@limiter.limit(PICKEM_JOIN_RATE_LIMIT)
def pickem_join(request: Request, body: PickemJoinIn):
    """
    Join the pick'em with a display name. Returns the player's key once;
    the browser keeps it and shows it as a recovery code. 409 if the name
    is taken (names are unique regardless of case).
    """
    import uuid

    import pickem

    name = body.name.strip()
    problem = pickem.name_problem(name)
    if problem:
        raise HTTPException(status_code=400, detail=problem)
    key = pickem.new_key()
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO pickem_players (player_id, key_hash, display_name) VALUES (%s, %s, %s)",
                (str(uuid.uuid4()), pickem.hash_key(key), name),
            )
        conn.commit()
    except psycopg2.errors.UniqueViolation:
        conn.rollback()
        raise HTTPException(status_code=409, detail="That name is taken.")
    except psycopg2.Error as exc:
        conn.rollback()
        if _pickem_tables_missing(exc):
            raise HTTPException(status_code=503, detail="Pick'em isn't set up yet.")
        logger.error("Failed to create pick'em player", exc_info=True)
        raise
    finally:
        conn.close()
    return {"name": name, "key": key}


@app.post("/pickem/me")
@limiter.limit(PICKEM_RATE_LIMIT)
def pickem_me(request: Request, body: PickemMeIn):
    """A player's name, record (and PuckPulse's on the same games), and picks for a day."""
    import pickem
    from daily_digest import today_eastern

    day = body.day or today_eastern()
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            player = _pickem_player(cur, body.key)
            record = pickem.player_record(cur, player["player_id"])
            cur.execute("SELECT game_id, pick FROM pickem_picks WHERE player_id = %s AND game_date = %s",
                        (player["player_id"], day))
            picks = {str(r["game_id"]): r["pick"] for r in cur.fetchall()}
        return {
            "name": player["display_name"],
            "record": {"correct": record["correct"], "graded": record["graded"], "pending": record["pending"]},
            "vs_puckpulse": {"you": record["correct"], "puckpulse": record["model_correct"], "games": record["model_games"]},
            "date": str(day),
            "picks": picks,
        }
    except psycopg2.Error as exc:
        conn.rollback()
        if _pickem_tables_missing(exc):
            raise HTTPException(status_code=503, detail="Pick'em isn't set up yet.")
        raise
    finally:
        conn.close()


@app.post("/pickem/pick")
@limiter.limit(PICKEM_RATE_LIMIT)
def pickem_pick(request: Request, body: PickemPickIn):
    """
    Pick (or change) a game's winner. The server checks the game hasn't
    started, by both its state and its start time, so a late pick can't
    slip through a cached scoreboard.
    """
    import pickem

    team = body.team.upper()
    try:
        game = game_boxscore(body.game_id)
    except NHLGamesUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if not game or not game.get("homeTeam"):
        raise HTTPException(status_code=404, detail="No such game.")
    problem = pickem.pick_problem(game, team)
    if problem:
        raise HTTPException(status_code=409, detail=problem)
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            player = _pickem_player(cur, body.key)
            cur.execute(
                """
                INSERT INTO pickem_picks (player_id, game_id, game_date, home_abbrev, away_abbrev, pick)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (player_id, game_id) DO UPDATE SET pick = EXCLUDED.pick, picked_at = NOW()
                """,
                (player["player_id"], body.game_id, game.get("gameDate"), game["homeTeam"]["abbrev"],
                 game["awayTeam"]["abbrev"], team),
            )
        conn.commit()
        return {"game_id": body.game_id, "pick": team}
    except HTTPException:
        raise
    except psycopg2.Error as exc:
        conn.rollback()
        if _pickem_tables_missing(exc):
            raise HTTPException(status_code=503, detail="Pick'em isn't set up yet.")
        raise
    finally:
        conn.close()


@app.get("/pickem/leaderboard")
def pickem_leaderboard():
    """Players by correct picks, and PuckPulse's record on every graded game as the benchmark."""
    import pickem

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            players, model = pickem.leaderboard(cur)
        return {
            "players": [{"name": p["display_name"], "correct": p["correct"], "graded": p["graded"]} for p in players],
            "puckpulse": {"correct": model["correct"], "graded": model["graded"]},
        }
    except psycopg2.Error as exc:
        conn.rollback()
        if _pickem_tables_missing(exc):
            return {"players": [], "puckpulse": {"correct": 0, "graded": 0}}
        raise
    finally:
        conn.close()


@app.get("/bets")
@daily_cached
def bets_for_day(day: date = Query(..., alias="date")):
    """
    The Bets tab for a date: each game's moneyline, puck line, and total
    from the sportsbooks (the closing snapshot once it's taken, else the
    morning one), next to PuckPulse's fair odds, the edge, and the expected
    value at the best price (bets.py), and each team's projected starting
    goalies (goalie_starts.py). {"date", "games": {game_id: {...}}}.
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT game_id, home_abbrev, away_abbrev, home_win_prob, home_goals, away_goals
                FROM game_predictions WHERE game_date = %s
                """,
                (day,),
            )
            predictions = cur.fetchall()
            try:
                cur.execute(
                    """
                    SELECT DISTINCT ON (game_id) *
                    FROM market_odds WHERE game_date = %s AND source = 'sportsbooks'
                    ORDER BY game_id, (captured = 'close') DESC
                    """,
                    (day,),
                )
                markets = {r["game_id"]: dict(r) for r in cur.fetchall()}
            except psycopg2.errors.UndefinedTable:
                conn.rollback()
                markets = {}
            try:
                cur.execute(
                    """
                    SELECT game_id, team_abbrev, goalie_name, start_prob FROM goalie_projections
                    WHERE game_date = %s ORDER BY game_id, team_abbrev, start_prob DESC
                    """,
                    (day,),
                )
                projections = cur.fetchall()
            except psycopg2.errors.UndefinedTable:
                conn.rollback()  # the daily job hasn't created it yet
                projections = []
            cur.execute("SELECT payload->'games' AS games FROM season_sim_inputs ORDER BY season_id DESC LIMIT 1")
            row = cur.fetchone()
        # The model's schedule rows: [date, home, away, home_b2b, away_b2b].
        b2b = {(g[1], g[2]): (bool(g[3]), bool(g[4])) for g in (row["games"] if row and row["games"] else [])
               if len(g) >= 5 and g[0] == str(day)}
        # NHL.com's projected lineups name the likely starters once posted (a
        # few hours before puck drop); fetched in parallel, each cached.
        with ThreadPoolExecutor(max_workers=8) as pool:
            lineups = dict(zip(
                [p["game_id"] for p in predictions],
                pool.map(lambda p: _lineup(p["game_id"], p["away_abbrev"], p["home_abbrev"], day), predictions),
            ))
        # Beat reporters' starters via RotoWire (news.py), usually ahead of NHL.com.
        players = _roster_lookup()

        def goalie_team(name):
            hit = players.get(news.player_key(name))
            return hit[0] if hit and hit[1] == "G" else None
        reports = news.goalie_reports(day, goalie_team)
        games = {}
        for p in predictions:
            market = markets.get(p["game_id"])
            if market and market.get("captured_at"):
                market["captured_at"] = market["captured_at"].isoformat()
            pred = {"home": p["home_abbrev"], "away": p["away_abbrev"], "home_win_prob": p["home_win_prob"],
                    "home_goals": p["home_goals"], "away_goals": p["away_goals"]}
            board = bets.game_board(pred, market, b2b.get((p["home_abbrev"], p["away_abbrev"]), (False, False)))
            board["goalies"] = {
                side: [{"name": g["goalie_name"], "prob": float(g["start_prob"])} for g in projections
                       if g["game_id"] == p["game_id"] and g["team_abbrev"] == p[f"{side}_abbrev"]]
                for side in ("home", "away")
            }
            lineup = lineups.get(p["game_id"])
            board["nhl_starters"] = ({side: (lineup[side]["goalies"] or [None])[0] for side in ("home", "away")}
                                     if lineup else None)
            board["reported_starters"] = {side: reports.get(p[f"{side}_abbrev"]) for side in ("home", "away")}
            games[str(p["game_id"])] = board
        return {"date": str(day), "games": games}
    except Exception:
        logger.error(f"Failed to build the bets board for {day}", exc_info=True)
        raise
    finally:
        conn.close()


@app.get("/report-card")
@daily_cached
def report_card_summary():
    """
    PuckPulse vs. the sportsbooks on finished games this season and in the
    last 7 days (report_card.py): Brier scores for the moneyline, puck line,
    and total, how the Bets tab's value badges would have done, and the
    biggest disagreements.
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT p.game_id, p.game_date, p.home_abbrev, p.away_abbrev, p.home_win_prob, p.home_goals,
                       p.away_goals, p.home_score, p.away_score
                FROM game_predictions p
                WHERE p.home_won IS NOT NULL AND p.source = 'daily'
                  AND p.season_id = (SELECT MAX(season_id) FROM game_predictions)
                ORDER BY p.game_date
                """
            )
            predictions = cur.fetchall()
            try:
                cur.execute(
                    """
                    SELECT DISTINCT ON (game_id) *
                    FROM market_odds WHERE source = 'sportsbooks' AND game_id = ANY(%s)
                    ORDER BY game_id, (captured = 'close') DESC
                    """,
                    ([p["game_id"] for p in predictions],),
                )
                markets = {r["game_id"]: dict(r) for r in cur.fetchall()}
            except psycopg2.errors.UndefinedTable:
                conn.rollback()
                markets = {}
        games = [{"game_date": p["game_date"], "home": p["home_abbrev"], "away": p["away_abbrev"],
                  "home_win_prob": p["home_win_prob"], "home_goals": p["home_goals"], "away_goals": p["away_goals"],
                  "home_score": p["home_score"], "away_score": p["away_score"], "market": markets.get(p["game_id"])}
                 for p in predictions]
        latest = max((g["game_date"] for g in games), default=None)
        week = [g for g in games if latest and (latest - g["game_date"]).days < 7]
        return {"as_of": str(latest) if latest else None, "week": report_card.summarize(week),
                "season": report_card.summarize(games)}
    except Exception:
        logger.error("Failed to build the report card", exc_info=True)
        raise
    finally:
        conn.close()


def _today_lottery(rows):
    """
    The lottery "if the season ended today": rows are the latest standings
    snapshot. The NHL's own ranks carry its tiebreakers: a team is in a
    playoff spot if it's top 3 in its division or one of the 2 wild cards,
    and the lottery order is the rest, worst league rank first.
    """
    missed = [r for r in rows if not (r["division_sequence"] <= 3 or r["wildcard_sequence"] in (1, 2))]
    missed.sort(key=lambda r: -r["league_sequence"])
    if len(missed) != len(lottery.COMBINATIONS):
        return []
    chances = lottery.pick_chances([r["team_abbrev"] for r in missed])
    return [{"team": r["team_abbrev"], "position": i + 1, "points": r["points"], "games_played": r["games_played"],
             "picks": [round(p, 5) for p in chances[r["team_abbrev"]]]} for i, r in enumerate(missed)]


def _mock_draft(projected, today, standings):
    """
    The first round of a mock draft (draft_board.py) for each lottery view,
    or None before the draft's board exists. A season's draft is the next
    June: in October 2026, the 2027 draft.
    """
    now = date.today()
    board = draft_board.load(now.year + 1 if now.month >= 7 else now.year)
    if not board:
        return None
    prospects = draft_board.consensus(board)
    return {
        "year": board["draft_year"],
        "sources": [{k: s[k] for k in ("name", "url", "as_of")} for s in board["sources"]],
        "projected": draft_board.mock_draft(draft_board.projected_order(projected, standings), prospects) if projected else [],
        "today": draft_board.mock_draft(draft_board.today_order(today, standings), prospects) if today else [],
    }


@app.get("/draft-lottery")
@daily_cached
def draft_lottery():
    """
    Draft lottery odds (lottery.py): "projected" from the daily season
    simulation (where each team might finish, then the lottery), and
    "today" if the season ended with the current standings. Each team's
    picks are its chances at picks 1-16.
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT team_abbrev, points, games_played, league_sequence, division_sequence, wildcard_sequence, snapshot_date
                FROM standings_snapshots
                WHERE snapshot_date = (SELECT MAX(snapshot_date) FROM standings_snapshots)
                """
            )
            standings = cur.fetchall()
            try:
                cur.execute(
                    """
                    SELECT team_abbrev, missed_playoffs_pct, pick_chances, as_of_date FROM draft_lottery_odds
                    WHERE (season_id, as_of_date) = (SELECT season_id, MAX(as_of_date) FROM draft_lottery_odds
                                                     GROUP BY season_id ORDER BY season_id DESC LIMIT 1)
                    """
                )
                projected = cur.fetchall()
            except psycopg2.errors.UndefinedTable:
                conn.rollback()  # the daily job hasn't created it yet
                projected = []
        picks = lambda value: value if isinstance(value, list) else json.loads(value)  # noqa: E731
        projected_rows = sorted(
            ({"team": r["team_abbrev"], "missed_playoffs": float(r["missed_playoffs_pct"]), "picks": picks(r["pick_chances"])}
             for r in projected if float(r["missed_playoffs_pct"]) > 0),
            key=lambda t: -t["picks"][0])
        today = _today_lottery(standings)
        return {
            "as_of": str(projected[0]["as_of_date"]) if projected else None,
            "standings_date": str(standings[0]["snapshot_date"]) if standings else None,
            "projected": projected_rows,
            "today": today,
            "mock": _mock_draft(projected_rows, today, standings),
        }
    except Exception:
        logger.error("Failed to build the draft lottery odds", exc_info=True)
        raise
    finally:
        conn.close()


@app.get("/market-odds")
@daily_cached
def market_odds_for_day(day: date = Query(..., alias="date")):
    """
    The sportsbook consensus for each game on a date (logged before puck
    drop by market_odds.py): the home team's implied win probability with
    the books' margin removed, the median moneylines, and how many books.
    Only sportsbooks: Kalshi's prices are logged for grading, not shown.
    {"date", "games": {game_id: {...}}}; empty before the first daily run.
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            try:
                cur.execute(
                    """
                    SELECT game_id, home_abbrev, away_abbrev, home_prob, home_line, away_line, books, captured_at
                    FROM market_odds WHERE game_date = %s AND source = 'sportsbooks' AND captured = 'morning'
                    """,
                    (day,),
                )
                rows = cur.fetchall()
            except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn):
                conn.rollback()  # the daily job hasn't created the table (or columns) yet
                rows = []
        games = {
            str(r["game_id"]): {
                "home": r["home_abbrev"], "away": r["away_abbrev"], "home_prob": float(r["home_prob"]),
                "home_line": r["home_line"], "away_line": r["away_line"], "books": r["books"],
                "as_of": r["captured_at"].isoformat() if r["captured_at"] else None,
            }
            for r in rows
        }
        return {"date": str(day), "games": games}
    except Exception:
        logger.error(f"Failed to fetch market odds for {day}", exc_info=True)
        raise
    finally:
        conn.close()


POSITION_ORDER = {"L": 0, "C": 1, "R": 2}


def _wing_center_wing(line, positions):
    """A forward line in the usual left wing, center, right wing order (shift charts don't know positions)."""
    pairs = sorted(zip(line.get("players", []), line.get("player_ids", [])),
                   key=lambda pair: POSITION_ORDER.get(positions.get(pair[1]), 1))
    return {**line, "players": [p for p, _ in pairs], "player_ids": [i for _, i in pairs]}


@app.get("/teams/{team_abbrev}/lines")
@daily_cached
def team_lines_today(team_abbrev: str = Path(..., pattern=r"^[A-Za-z]{3}$")):
    """
    The team's forward lines and defense pairs from its last completed game
    (worked out from NHL shift charts by team_lines.py), with which game
    that was. Not tonight's confirmed lineup. game is null and the lists
    are empty before the team's first game or the first daily run.
    """
    abbrev = team_abbrev.upper()
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM teams WHERE team_abbrev = %s", (abbrev,))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail=f"No team found with abbreviation '{team_abbrev}'")
            try:
                cur.execute(
                    "SELECT game_id, game_date, opponent, home, payload FROM team_lines WHERE team_abbrev = %s",
                    (abbrev,),
                )
                row = cur.fetchone()
            except psycopg2.errors.UndefinedTable:
                conn.rollback()  # the daily job hasn't created the table yet
                row = None
        if not row:
            return {"team": abbrev, "game": None, "lines": [], "pairs": []}
        payload = row["payload"] if isinstance(row["payload"], dict) else json.loads(row["payload"])
        game = {"id": row["game_id"], "date": str(row["game_date"]), "opponent": row["opponent"], "home": row["home"]}
        lines = payload.get("lines", [])
        ids = [pid for line in lines for pid in line.get("player_ids", [])]
        positions = {}
        if ids:
            with conn.cursor() as cur:
                cur.execute("SELECT player_id, position_code FROM players WHERE player_id = ANY(%s)", (ids,))
                positions = {r["player_id"]: r["position_code"] for r in cur.fetchall()}
        return {"team": abbrev, "game": game, "lines": [_wing_center_wing(line, positions) for line in lines],
                "pairs": payload.get("pairs", [])}
    except HTTPException:
        raise
    except Exception:
        logger.error(f"Failed to fetch lines for {abbrev}", exc_info=True)
        raise
    finally:
        conn.close()


@app.get("/teams/{team_abbrev}/roster", response_model=List[RosterPlayer])
@daily_cached
def team_roster(team_abbrev: str = Path(..., max_length=3)):
    """
    Current roster for one team, with each player's latest season stats.

    404s if team_abbrev isn't a real team. Returns an empty 200 list (not
    a 404) for a real team that simply has no roster rows loaded yet.
    """
    abbrev = team_abbrev.upper()
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM teams WHERE team_abbrev = %s", (abbrev,))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail=f"No team found with abbreviation '{team_abbrev}'")

            cur.execute(
                """
                SELECT p.*, s.season_id, s.games_played, s.goals, s.assists, s.points,
                       s.plus_minus, s.pim, s.shots, s.shooting_pctg,
                       s.power_play_goals, s.power_play_points,
                       s.shorthanded_goals, s.shorthanded_points,
                       s.game_winning_goals, s.ot_goals,
                       s.wins, s.losses, s.ot_losses, s.goals_against_avg,
                       s.save_pctg, s.shutouts, s.avg_toi_seconds
                FROM players p
                LEFT JOIN LATERAL (
                    SELECT * FROM player_season_stats pss
                    WHERE pss.player_id = p.player_id
                      AND pss.season_id = (SELECT MAX(season_id) FROM standings_snapshots)
                    ORDER BY pss.season_id DESC
                    LIMIT 1
                ) s ON true
                WHERE p.team_abbrev = %s
                  AND p.on_roster
                ORDER BY COALESCE(s.points, 0) DESC, COALESCE(s.wins, 0) DESC
                """,
                (abbrev,),
            )
            return cur.fetchall()
    except HTTPException:
        raise
    except Exception:
        logger.error(f"Failed to fetch roster for team '{team_abbrev}'", exc_info=True)
        raise
    finally:
        conn.close()


_LEADER_TABLE_ADAPTER = TypeAdapter(List[PlayerLeaderTableRow])


@app.get("/players/leaders", response_model=List[PlayerLeader])
@limiter.limit(EXPENSIVE_RATE_LIMIT)
@daily_cached
def player_leaders(request: Request, view: Literal["full", "table"] = Query("full")):
    """
    Every rostered player with their latest season stats, for the league
    leaderboard. Must be registered before /players/{player_id} so this
    literal path wins the match instead of being parsed as a player id.

    view=full (default) returns every PlayerLeader field; the intelligence
    service and evals rely on that, so the default must not change.
    view=table returns only the PlayerLeaderTableRow fields the Players page
    renders (same rows, same order). Any other value is a 422.
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT p.*, t.team_name, t.logo_url AS team_logo_url,
                       s.season_id, s.games_played, s.goals, s.assists, s.points,
                       s.plus_minus, s.pim, s.shots, s.shooting_pctg,
                       s.power_play_goals, s.power_play_points,
                       s.shorthanded_goals, s.shorthanded_points,
                       s.game_winning_goals, s.ot_goals,
                       s.wins, s.losses, s.ot_losses, s.goals_against_avg,
                       s.save_pctg, s.shutouts, s.avg_toi_seconds
                FROM players p
                JOIN teams t ON t.team_abbrev = p.team_abbrev
                LEFT JOIN LATERAL (
                    SELECT * FROM player_season_stats pss
                    WHERE pss.player_id = p.player_id
                      AND pss.season_id = (SELECT MAX(season_id) FROM standings_snapshots)
                    ORDER BY pss.season_id DESC
                    LIMIT 1
                ) s ON true
                ORDER BY COALESCE(s.points, 0) DESC
                """
            )
            rows = cur.fetchall()
        if view == "table":
            return JSONResponse(
                _LEADER_TABLE_ADAPTER.dump_python(_LEADER_TABLE_ADAPTER.validate_python(rows), mode="json")
            )
        return rows
    except Exception:
        logger.error("Failed to fetch player leaders", exc_info=True)
        raise
    finally:
        conn.close()


def _goalie_advanced(cur, player_id):
    """
    This season's goalie_advanced_stats row with GSAx worked out, or None.
    Tolerates the table not existing yet (schema.sql not applied): the
    connection is autocommit, so a failed query doesn't poison it.
    """
    try:
        cur.execute(
            """
            SELECT * FROM goalie_advanced_stats
            WHERE player_id = %s AND season_id = (SELECT MAX(season_id) FROM standings_snapshots)
            """,
            (player_id,),
        )
        row = cur.fetchone()
    except psycopg2.errors.UndefinedTable:
        return None
    if not row:
        return None
    row = dict(row)
    xga, ga = row.get("xgoals_against"), row.get("goals_allowed")
    if xga is not None and ga is not None:
        row["gsax"] = round(float(xga) - ga, 2)
        hours = (row.get("icetime_seconds") or 0) / 3600
        row["gsax_per_60"] = round(row["gsax"] / hours, 2) if hours else None
    hd_x, hd_g = row.get("high_danger_xgoals"), row.get("high_danger_goals")
    if hd_x is not None and hd_g is not None:
        row["high_danger_gsax"] = round(float(hd_x) - hd_g, 2)
    return row


@app.get("/goalies/advanced")
@daily_cached
def goalies_advanced():
    """
    This season's goalies by goals saved above expected (GSAx = xG against
    minus goals allowed, from PuckPulse's xG), best first, with per-60 and
    high-danger GSAx. For PuckPulse AI's "who's the best goalie?"
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            try:
                cur.execute(
                    """
                    SELECT g.player_id, p.first_name, p.last_name, p.team_abbrev, g.games_played, g.icetime_seconds,
                           g.shots_faced, g.goals_allowed, g.xgoals_against, g.high_danger_goals, g.high_danger_xgoals
                    FROM goalie_advanced_stats g JOIN players p USING (player_id)
                    WHERE g.season_id = (SELECT MAX(season_id) FROM standings_snapshots)
                    """
                )
                rows = cur.fetchall()
            except psycopg2.errors.UndefinedTable:
                return {"goalies": []}
    finally:
        conn.close()
    goalies = []
    for r in rows:
        if r["xgoals_against"] is None or r["goals_allowed"] is None:
            continue
        gsax = float(r["xgoals_against"]) - r["goals_allowed"]
        hours = (r["icetime_seconds"] or 0) / 3600
        goalies.append({
            "player_id": r["player_id"], "name": f"{r['first_name']} {r['last_name']}", "team": r["team_abbrev"],
            "games_played": r["games_played"], "gsax": round(gsax, 2), "gsax_per_60": round(gsax / hours, 2) if hours else None,
            "high_danger_gsax": round(float(r["high_danger_xgoals"]) - r["high_danger_goals"], 2)
            if r["high_danger_xgoals"] is not None and r["high_danger_goals"] is not None else None,
            "save_pct": round(1 - r["goals_allowed"] / r["shots_faced"], 3) if r["shots_faced"] else None,
        })
    goalies.sort(key=lambda g: -g["gsax"])
    return {"goalies": goalies}


@app.get("/players/{player_id}", response_model=PlayerDetail)
def player_detail(player_id: int):
    """
    Bio plus season-by-season stats for one player.

    404s (not an empty body) when player_id doesn't exist.
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT p.*, t.team_name, t.logo_url AS team_logo_url
                FROM players p
                JOIN teams t ON t.team_abbrev = p.team_abbrev
                WHERE p.player_id = %s
                """,
                (player_id,),
            )
            player = cur.fetchone()
            if not player:
                raise HTTPException(status_code=404, detail=f"No player found with id '{player_id}'")

            cur.execute(
                """
                SELECT * FROM player_season_stats
                WHERE player_id = %s
                  AND season_id = (SELECT MAX(season_id) FROM standings_snapshots)
                ORDER BY season_id DESC
                """,
                (player_id,),
            )
            player["season_stats"] = cur.fetchall()

            cur.execute(
                """
                SELECT * FROM player_advanced_stats
                WHERE player_id = %s
                  AND season_id = (SELECT MAX(season_id) FROM standings_snapshots)
                ORDER BY season_id DESC
                LIMIT 1
                """,
                (player_id,),
            )
            player["advanced_stats"] = cur.fetchone()
            player["advanced_percentiles"] = (
                _advanced_percentiles(player["advanced_stats"], player.get("position_code"))
                if player["advanced_stats"] and player.get("position_code") != "G" else None
            )
            player["goalie_advanced_stats"] = _goalie_advanced(cur, player_id) if player.get("position_code") == "G" else None

            cur.execute(
                "SELECT * FROM player_career_totals WHERE player_id = %s",
                (player_id,),
            )
            career_rows = cur.fetchall()
            by_season_type = {row["season_type"]: row for row in career_rows}
            player["career_totals"] = {
                "regular_season": by_season_type.get("regular_season"),
                "playoffs": by_season_type.get("playoffs"),
            }

            cur.execute(
                "SELECT * FROM player_season_history WHERE player_id = %s ORDER BY season_id DESC, season_type DESC",
                (player_id,),
            )
            player["season_history"] = cur.fetchall()
            return player
    except HTTPException:
        raise
    except Exception:
        logger.error(f"Failed to fetch player detail for id '{player_id}'", exc_info=True)
        raise
    finally:
        conn.close()


def _ixg60(row):
    """Individual expected goals per 60 minutes at 5-on-5."""
    seconds = row.get("icetime_seconds") or 0
    return float(row["individual_xgoals"]) * 3600 / seconds if seconds and row.get("individual_xgoals") is not None else None


def _peer_stats(season_id):
    """
    {"F": [...], "D": [...]}: this season's skaters with enough 5-on-5 ice
    time to compare (a third of the median), each {corsi, xg, ixg60}.
    Cached: the advanced stats change once a day.
    """
    def load():
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT a.corsi_for_pct, a.xgoals_for_pct, a.individual_xgoals, a.icetime_seconds, p.position_code
                    FROM player_advanced_stats a JOIN players p ON p.player_id = a.player_id
                    WHERE a.season_id = %s AND p.position_code <> 'G' AND a.icetime_seconds > 0
                    """,
                    (season_id,),
                )
                rows = cur.fetchall()
        finally:
            conn.close()
        times = sorted(r["icetime_seconds"] for r in rows)
        floor = times[len(times) // 2] / 3 if times else 0
        groups = {"F": [], "D": []}
        for r in rows:
            if r["icetime_seconds"] >= floor:
                groups["D" if r["position_code"] == "D" else "F"].append(
                    {"corsi": r["corsi_for_pct"], "xg": r["xgoals_for_pct"], "ixg60": _ixg60(r)})
        return {"floor_seconds": floor, **groups}
    return daily_cache.get_or_compute(("peer_stats", season_id), load)


def _percentile(value, values):
    """Share of values below this one (ties count half), 0-100."""
    values = [v for v in values if v is not None]
    if value is None or not values:
        return None
    below = sum(v < value for v in values)
    ties = sum(v == value for v in values)
    return round(100 * (below + 0.5 * ties) / len(values))


def _advanced_percentiles(stats, position_code):
    """
    Where a skater's 5-on-5 numbers rank among his position group this
    season: {"group", "peers", "corsi", "xg", "ixg60", "ixg60_value"}, or
    {"too_few_minutes": True} below the ice-time floor.
    """
    peers = _peer_stats(stats["season_id"])
    if (stats.get("icetime_seconds") or 0) < peers["floor_seconds"]:
        return {"too_few_minutes": True}
    group = "D" if position_code == "D" else "F"
    pool = peers[group]
    ixg60 = _ixg60(stats)
    return {
        "group": "defensemen" if group == "D" else "forwards",
        "peers": len(pool),
        "corsi": _percentile(stats.get("corsi_for_pct"), [p["corsi"] for p in pool]),
        "xg": _percentile(stats.get("xgoals_for_pct"), [p["xg"] for p in pool]),
        "ixg60": _percentile(ixg60, [p["ixg60"] for p in pool]),
        "ixg60_value": round(ixg60, 2) if ixg60 is not None else None,
    }


# Maps a ?sort_by= value to a safe SQL column expression -- never
# interpolate the raw query param into ORDER BY directly, since it comes
# straight from the client. Covers the original standings columns plus
# the team_advanced_stats fields joined in below; "ta." columns are NULL
# for any team MoneyPuck ingestion hasn't covered yet, so every sort uses
# NULLS LAST to keep those teams at the bottom regardless of direction
# rather than jumbling them in wherever NULL happens to sort by default.
STANDINGS_SORT_FIELDS = {
    "points": "s.points",
    "wins": "s.wins",
    "losses": "s.losses",
    "goal_differential": "s.goal_differential",
    "point_pctg": "s.point_pctg",
    "corsi_for_pct": "ta.corsi_for_pct",
    "fenwick_for_pct": "ta.fenwick_for_pct",
    "xgoals_for_pct": "ta.xgoals_for_pct",
    "xgoals_for": "ta.xgoals_for",
    "xgoals_against": "ta.xgoals_against",
    "shots_on_goal_for": "ta.shots_on_goal_for",
    "shots_on_goal_against": "ta.shots_on_goal_against",
    "pdo": "ta.pdo",
}


@app.get("/standings/latest", response_model=List[StandingsLatestRow])
@daily_cached
def latest_standings(sort_by: Optional[str] = None, sort_dir: str = "desc"):
    """
    Most recent day's standings for every team, joined with this season's
    5-on-5 advanced stats (corsi/fenwick/xG%, xG/shots for and against,
    PDO -- see ingest_advanced_stats.py), ranked by league position by
    default.

    ?sort_by=<field>&sort_dir=asc|desc overrides the default ordering --
    see STANDINGS_SORT_FIELDS for the allowed field names. A 400 is raised
    for an unrecognized sort_by or sort_dir rather than silently falling
    back to the default, since a typo'd field name silently doing nothing
    would be a confusing way to fail.
    """
    if sort_by is not None and sort_by not in STANDINGS_SORT_FIELDS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid sort_by '{sort_by}'. Must be one of: {', '.join(sorted(STANDINGS_SORT_FIELDS))}",
        )
    if sort_dir not in ("asc", "desc"):
        raise HTTPException(status_code=400, detail="Invalid sort_dir. Must be 'asc' or 'desc'.")

    order_clause = (
        f"{STANDINGS_SORT_FIELDS[sort_by]} {sort_dir.upper()} NULLS LAST"
        if sort_by
        else "s.league_sequence ASC"
    )

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT s.*, t.team_name, t.common_name, t.division, t.conference, t.logo_url,
                       ta.corsi_for_pct, ta.fenwick_for_pct, ta.xgoals_for_pct,
                       ta.xgoals_for, ta.xgoals_against,
                       ta.shots_on_goal_for, ta.shots_on_goal_against, ta.pdo
                FROM standings_snapshots s
                JOIN teams t ON t.team_abbrev = s.team_abbrev
                LEFT JOIN team_advanced_stats ta
                    ON ta.team_abbrev = s.team_abbrev AND ta.season_id = s.season_id
                WHERE s.snapshot_date = (SELECT MAX(snapshot_date) FROM standings_snapshots)
                ORDER BY {order_clause}
                """
            )
            return cur.fetchall()
    except HTTPException:
        raise
    except Exception:
        logger.error("Failed to fetch latest standings", exc_info=True)
        raise
    finally:
        conn.close()


@app.get("/standings/{team_abbrev}/seasons", response_model=List[SeasonFinalStanding])
@daily_cached
def team_season_history(team_abbrev: str = Path(..., max_length=3)):
    """
    Final standings for one team across past completed seasons, e.g.
    /standings/PIT/seasons. Ordered oldest to newest.

    Note: relocated/renamed franchises (e.g. Arizona Coyotes -> Utah) are
    tracked under their historical abbreviation, so this only covers the
    seasons played under the given team_abbrev.

    Returns an empty 200 list (not a 404) for an unknown/dataless
    team_abbrev -- see SeasonFinalStanding's docstring for the cross-endpoint
    404-vs-empty-list inconsistency.
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM season_final_standings
                WHERE team_abbrev = %s
                ORDER BY season_id ASC
                """,
                (team_abbrev.upper(),),
            )
            return cur.fetchall()
    except Exception:
        logger.error(f"Failed to fetch season history for team '{team_abbrev}'", exc_info=True)
        raise
    finally:
        conn.close()


@app.get("/standings/{team_abbrev}", response_model=List[StandingsHistoryRow])
@daily_cached
def team_history(
    team_abbrev: str = Path(..., max_length=3), start: Optional[date] = None, end: Optional[date] = None
):
    """
    Full snapshot history for one team, e.g. /standings/PIT
    Optionally filter with ?start=2026-01-01&end=2026-04-01

    404s if team_abbrev isn't a real team. Returns an empty 200 list (not
    a 404) for a real team that simply has no snapshot rows yet (or none
    in the given start/end range).
    """
    abbrev = team_abbrev.upper()
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM teams WHERE team_abbrev = %s", (abbrev,))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail=f"No team found with abbreviation '{team_abbrev}'")

            query = """
                SELECT s.*, t.team_name
                FROM standings_snapshots s
                JOIN teams t ON t.team_abbrev = s.team_abbrev
                WHERE s.team_abbrev = %s
            """
            params = [abbrev]

            if start:
                query += " AND s.snapshot_date >= %s"
                params.append(start)
            if end:
                query += " AND s.snapshot_date <= %s"
                params.append(end)

            query += " ORDER BY s.snapshot_date ASC"

            cur.execute(query, params)
            return cur.fetchall()
    except HTTPException:
        raise
    except Exception:
        logger.error(f"Failed to fetch standings history for team '{team_abbrev}'", exc_info=True)
        raise
    finally:
        conn.close()
