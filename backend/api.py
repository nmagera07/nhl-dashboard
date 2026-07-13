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

import os
from datetime import date
from typing import List, Optional

import psycopg2
import psycopg2.extras
import sentry_sdk
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Path, Request
from fastapi.middleware.cors import CORSMiddleware
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
    RosterPlayer,
    PlayerLeader,
    PlayerDetail,
    StandingsLatestRow,
    StandingsHistoryRow,
    SeasonFinalStanding,
)

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
        traces_sample_rate=0.1,
    )

# Azure Container Apps already captures stdout/stderr, and the container's
# filesystem is ephemeral, so skip the rotating file handler here -- just
# reuse the same shared setup with file logging disabled.
logger = setup_logging(__name__, log_to_file=False)

app = FastAPI(
    title="NHL Stats Dashboard API",
    description="Serves NHL standings data collected from the NHL public API.",
    version="0.1.0",
)

# Coarse per-IP abuse/scraping guard. 60/minute is generous for normal
# frontend usage (a page load fires a handful of requests, well under
# this in any burst) while still bounding a naive scraper hammering the
# API. The two join-heavy endpoints (player_leaders, playoff_odds) get a
# tighter override below via @limiter.limit(...) -- retune either string
# here if real usage patterns call for it.
DEFAULT_RATE_LIMIT = "60/minute"
EXPENSIVE_RATE_LIMIT = "20/minute"

# key_style="endpoint" (rather than slowapi's default "url") scopes each
# limit bucket to the route *handler*, not the literal request path -- so
# e.g. /standings/PIT and /standings/BOS share one bucket per client
# instead of each path parameter value getting its own fresh allowance,
# which would otherwise let someone bypass the limit just by cycling
# through team abbreviations or player ids.
limiter = Limiter(key_func=get_remote_address, default_limits=[DEFAULT_RATE_LIMIT], key_style="endpoint")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
# Added before CORSMiddleware so CORS ends up as the outermost layer
# (Starlette wraps middleware in reverse registration order) -- otherwise
# a 429 response would be missing Access-Control-Allow-Origin, and the
# browser would surface it to the frontend as an opaque CORS/network
# failure instead of a readable rate-limit response.
app.add_middleware(SlowAPIMiddleware)

# Only the deployed frontend (and local dev) can call this API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://ashy-sky-01e4eba1e.7.azurestaticapps.net",
        "http://localhost:5173",  # local Vite dev server
    ],
    allow_methods=["GET"],
    allow_headers=["Content-Type", "Accept"],
)


def get_connection():
    try:
        return psycopg2.connect(API_DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)
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
    return {"status": "ok", "database": "connected"}


@app.get("/teams", response_model=List[Team])
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


@app.get("/teams/{team_abbrev}/roster", response_model=List[RosterPlayer])
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
                       s.save_pctg, s.shutouts
                FROM players p
                LEFT JOIN LATERAL (
                    SELECT * FROM player_season_stats pss
                    WHERE pss.player_id = p.player_id
                    ORDER BY pss.season_id DESC
                    LIMIT 1
                ) s ON true
                WHERE p.team_abbrev = %s
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


@app.get("/players/leaders", response_model=List[PlayerLeader])
@limiter.limit(EXPENSIVE_RATE_LIMIT)
def player_leaders(request: Request):
    """
    Every rostered player with their latest season stats, for the league
    leaderboard. Must be registered before /players/{player_id} so this
    literal path wins the match instead of being parsed as a player id.
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
                       s.save_pctg, s.shutouts
                FROM players p
                JOIN teams t ON t.team_abbrev = p.team_abbrev
                LEFT JOIN LATERAL (
                    SELECT * FROM player_season_stats pss
                    WHERE pss.player_id = p.player_id
                    ORDER BY pss.season_id DESC
                    LIMIT 1
                ) s ON true
                ORDER BY COALESCE(s.points, 0) DESC
                """
            )
            return cur.fetchall()
    except Exception:
        logger.error("Failed to fetch player leaders", exc_info=True)
        raise
    finally:
        conn.close()


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
                "SELECT * FROM player_season_stats WHERE player_id = %s ORDER BY season_id DESC",
                (player_id,),
            )
            player["season_stats"] = cur.fetchall()

            cur.execute(
                "SELECT * FROM player_advanced_stats WHERE player_id = %s ORDER BY season_id DESC",
                (player_id,),
            )
            player["advanced_stats"] = cur.fetchall()

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
            return player
    except HTTPException:
        raise
    except Exception:
        logger.error(f"Failed to fetch player detail for id '{player_id}'", exc_info=True)
        raise
    finally:
        conn.close()


@app.get("/standings/latest", response_model=List[StandingsLatestRow])
def latest_standings():
    """Most recent day's standings for every team, ranked by league position."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT s.*, t.team_name, t.common_name, t.division, t.conference, t.logo_url
                FROM standings_snapshots s
                JOIN teams t ON t.team_abbrev = s.team_abbrev
                WHERE s.snapshot_date = (SELECT MAX(snapshot_date) FROM standings_snapshots)
                ORDER BY s.league_sequence ASC
                """
            )
            return cur.fetchall()
    except Exception:
        logger.error("Failed to fetch latest standings", exc_info=True)
        raise
    finally:
        conn.close()


@app.get("/standings/{team_abbrev}/seasons", response_model=List[SeasonFinalStanding])
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