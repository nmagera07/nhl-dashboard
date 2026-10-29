"""
Pregame briefs: asks NHL Intelligence's brief agent (POST /briefs/write)
to research and write up each of today's games that hasn't started, and
stores them for the game page.

Runs twice a day on the notifier function (function_app.py): late morning,
and again late afternoon once most starting goalies are confirmed. Each run
rewrites every game still to start; a run whose brief fails the agent's
checks (text null) or can't reach the service keeps the earlier brief.
About 2 x 16 briefs on a busy day, well under the service's 60/hour limit.
"""

import json
import logging
import os
from datetime import datetime
from zoneinfo import ZoneInfo

import psycopg2
import requests
from dotenv import load_dotenv

from logging_config import setup_logging

load_dotenv()
logger = setup_logging("pregame_briefs")

DATABASE_URL = os.getenv("DATABASE_URL")
INTELLIGENCE_URL = (os.getenv("INTELLIGENCE_URL") or "").rstrip("/")
DIGEST_TOKEN = os.getenv("DIGEST_TOKEN", "")  # the same job token the morning digest uses
SCORE_URL = "https://api-web.nhle.com/v1/score/{date}"
NOT_STARTED = ("FUT", "PRE")
TIMEOUT = 120  # the service scales to zero, and the agent makes several tool calls

TABLE_SQL = """
CREATE TABLE IF NOT EXISTS game_briefs (
    game_id     BIGINT PRIMARY KEY,
    game_date   DATE NOT NULL,
    text        TEXT NOT NULL,
    model       VARCHAR(80),
    tools       JSONB,         -- what the agent looked up, for debugging
    written_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
GRANT SELECT ON game_briefs TO nhl_api_readonly
"""


def today_eastern(now=None) -> str:
    return (now or datetime.now(ZoneInfo("America/New_York"))).strftime("%Y-%m-%d")


def games_to_brief(day: str, get=requests.get) -> list[dict]:
    """Today's games that haven't started: [{game_id, away, home, date}]."""
    response = get(SCORE_URL.format(date=day), timeout=30)
    response.raise_for_status()
    return [{"game_id": g["id"], "away": g["awayTeam"]["abbrev"], "home": g["homeTeam"]["abbrev"], "date": day}
            for g in response.json().get("games", []) if g.get("gameState") in NOT_STARTED]


def write(game: dict, post=requests.post) -> dict | None:
    """The agent's brief ({text, model, problems, tools}), or None if the service couldn't be reached."""
    try:
        response = post(f"{INTELLIGENCE_URL}/briefs/write", json=game, headers={"X-Digest-Token": DIGEST_TOKEN},
                        timeout=TIMEOUT)
        response.raise_for_status()
        return response.json()
    except (requests.RequestException, ValueError) as exc:
        logger.warning(f"Game {game['game_id']}: couldn't get a brief ({exc})")
        return None


def save(cur, game: dict, brief: dict) -> None:
    cur.execute(
        """
        INSERT INTO game_briefs (game_id, game_date, text, model, tools, written_at)
        VALUES (%s, %s, %s, %s, %s, NOW())
        ON CONFLICT (game_id) DO UPDATE SET
            text = EXCLUDED.text, model = EXCLUDED.model, tools = EXCLUDED.tools, written_at = NOW()
        """,
        (game["game_id"], game["date"], brief["text"], brief.get("model"), json.dumps(brief.get("tools") or [])),
    )


def run(conn, day: str | None = None, get=requests.get, post=requests.post) -> tuple[int, int]:
    """Brief today's games that haven't started. Returns (written, kept or missing)."""
    day = day or today_eastern()
    games = games_to_brief(day, get)
    with conn.cursor() as cur:
        cur.execute(TABLE_SQL)
    conn.commit()
    written = skipped = 0
    for game in games:
        brief = write(game, post)
        if not brief or not brief.get("text"):
            if brief:
                logger.info(f"Game {game['game_id']}: no brief passed the checks ({'; '.join(brief.get('problems') or [])})")
            skipped += 1
            continue
        with conn.cursor() as cur:
            save(cur, game, brief)
        conn.commit()  # one game at a time: a later failure keeps the briefs already written
        written += 1
    return written, skipped


def main():
    if not DATABASE_URL:
        raise SystemExit("DATABASE_URL is not set")
    if not (INTELLIGENCE_URL and DIGEST_TOKEN):
        logger.warning("INTELLIGENCE_URL/DIGEST_TOKEN not set; no briefs")
        return
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    with psycopg2.connect(DATABASE_URL) as conn:
        written, skipped = run(conn)
    logger.info(f"Pregame briefs: {written} written, {skipped} kept from earlier or missing")


if __name__ == "__main__":
    main()
