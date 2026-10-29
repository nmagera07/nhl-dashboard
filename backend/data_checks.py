"""
The morning data check: did last night's 2 AM run (run_daily_ingest.py)
produce everything the site needs? Plain code, no AI: a check has to be
right every time.

- Freshness: each nightly table was updated today.
- Last night's games: every finished game has its xG, WAR v2 stints,
  5-on-5 shift data, recorded result, and graded prediction.
- Today's games: each has a pregame prediction.
- Swing of the Night is saved for last night.
- Sanity: playoff odds add up to 16 teams; last night's xG is in a normal range.

Each run stores its results in data_checks, and anything that failed is
pushed to the creator's devices (once a day). A clean run sends nothing.
Runs on the notifier function (function_app.py) after the 2 AM job.
"""

import json
import logging
import os
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta

import psycopg2
import psycopg2.extras
import requests
from dotenv import load_dotenv

import notify_live_games as nlg
from logging_config import setup_logging

load_dotenv()
logger = setup_logging("data_checks")

DATABASE_URL = os.getenv("DATABASE_URL")
SCORE_URL = "https://api-web.nhle.com/v1/score/{date}"
GAME_TYPES = (2, 3)  # regular season and playoffs; the nightly run skips preseason
XG_RANGE = (0.3, 9.0)  # one team's xG in one game; outside this, the model or the feed is off
PLAYOFF_SPOTS = 16

TABLE_SQL = """
CREATE TABLE IF NOT EXISTS data_checks (
    run_date    DATE PRIMARY KEY,
    ok          BOOLEAN NOT NULL,
    results     JSONB NOT NULL,   -- [{name, ok, detail}]
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
)
"""

# (label, table, date column): each should have today's date after the 2 AM run.
FRESH = [
    ("Standings", "standings_snapshots", "snapshot_date"),
    ("Playoff odds", "playoff_odds", "as_of_date"),
    ("WAR", "player_war", "as_of_date"),
    ("Season sim inputs", "season_sim_inputs", "as_of_date"),
    ("Morning digest", "daily_digest", "digest_date"),
    ("Player stats", "player_season_stats", "updated_at"),
    ("Advanced stats", "player_advanced_stats", "updated_at"),
]


@dataclass
class Result:
    name: str
    ok: bool
    detail: str = ""


def games_on(day: date, get=requests.get) -> list[dict]:
    """[{id, away, home, state}] for a day's regular-season and playoff games."""
    response = get(SCORE_URL.format(date=day.isoformat()), timeout=30)
    response.raise_for_status()
    return [{"id": g["id"], "away": g["awayTeam"]["abbrev"], "home": g["homeTeam"]["abbrev"], "state": g.get("gameState")}
            for g in response.json().get("games", []) if g.get("gameType") in GAME_TYPES]


def _label(game: dict) -> str:
    return f"{game['away']} @ {game['home']} ({game['id']})"


def check_fresh(cur, today: date) -> list[Result]:
    out = []
    for label, table, column in FRESH:
        cur.execute(f'SELECT MAX("{column}")::date AS latest FROM "{table}"')  # names are ours, not input
        latest = cur.fetchone()["latest"]
        out.append(Result(f"{label} updated", latest == today, "" if latest == today else f"last updated {latest}"))
    return out


def _ids(cur, sql, ids) -> set:
    cur.execute(sql, (list(ids),))
    return {row["game_id"] for row in cur.fetchall()}


def check_last_night(cur, finals: list[dict]) -> list[Result]:
    """Every finished game from last night has each nightly product."""
    if not finals:
        return []
    ids = [g["id"] for g in finals]
    have = {
        "xG": _ids(cur, "SELECT game_id FROM team_game_xg WHERE game_id = ANY(%s) GROUP BY game_id HAVING COUNT(*) = 2", ids),
        "WAR v2 stints": _ids(cur, "SELECT game_id FROM war_v2_games WHERE game_id = ANY(%s) AND has_stints", ids),
        "5-on-5 shift data": _ids(cur, "SELECT game_id FROM team_game_5v5 WHERE game_id = ANY(%s) "
                                       "GROUP BY game_id HAVING COUNT(*) = 2 AND BOOL_AND(has_shifts)", ids),
        "Result": _ids(cur, "SELECT game_id FROM game_results WHERE game_id = ANY(%s)", ids),
    }
    out = []
    for name, found in have.items():
        missing = [_label(g) for g in finals if g["id"] not in found]
        out.append(Result(f"Last night: {name}", not missing, "missing " + ", ".join(missing) if missing else ""))
    cur.execute("SELECT game_id FROM game_predictions WHERE game_id = ANY(%s) AND graded_at IS NULL", (ids,))
    ungraded = {row["game_id"] for row in cur.fetchall()}
    missing = [_label(g) for g in finals if g["id"] in ungraded]
    out.append(Result("Last night: predictions graded", not missing, "ungraded " + ", ".join(missing) if missing else ""))
    return out


def check_today(cur, games: list[dict]) -> list[Result]:
    if not games:
        return []
    found = _ids(cur, "SELECT game_id FROM game_predictions WHERE game_id = ANY(%s)", [g["id"] for g in games])
    missing = [_label(g) for g in games if g["id"] not in found]
    return [Result("Today: predictions logged", not missing, "missing " + ", ".join(missing) if missing else "")]


def check_swing(cur, yesterday: date, finals: list[dict]) -> list[Result]:
    if not finals:
        return []
    cur.execute("SELECT 1 FROM swing_of_the_night WHERE day = %s", (yesterday,))
    ok = cur.fetchone() is not None
    return [Result("Swing of the Night saved", ok, "" if ok else f"none saved for {yesterday}")]


def check_sanity(cur, finals: list[dict]) -> list[Result]:
    out = []
    cur.execute("SELECT SUM(playoff_pct) AS total, COUNT(*) AS teams FROM playoff_odds "
                "WHERE as_of_date = (SELECT MAX(as_of_date) FROM playoff_odds)")
    row = cur.fetchone()
    total = float(row["total"] or 0)
    total = total / 100 if total > 2 * PLAYOFF_SPOTS else total  # stored as percent or as a fraction
    ok = row["teams"] == 32 and abs(total - PLAYOFF_SPOTS) < 0.1
    out.append(Result("Playoff odds add up", ok, "" if ok else f"{row['teams']} teams, odds sum to {total:.2f} spots"))
    if finals:
        cur.execute("SELECT game_id, team_abbrev, xg_for FROM team_game_xg WHERE game_id = ANY(%s) "
                    "AND (xg_for < %s OR xg_for > %s)", ([g["id"] for g in finals], *XG_RANGE))
        odd = [f"{r['team_abbrev']} {float(r['xg_for']):.2f} ({r['game_id']})" for r in cur.fetchall()]
        out.append(Result("Last night's xG in range", not odd, "unusual: " + ", ".join(odd) if odd else ""))
    return out


def run_checks(cur, today: date, get=requests.get) -> list[Result]:
    yesterday = today - timedelta(days=1)
    finals = [g for g in games_on(yesterday, get) if g["state"] in nlg.FINAL_STATES]
    todays = games_on(today, get)
    return (check_fresh(cur, today) + check_last_night(cur, finals) + check_today(cur, todays)
            + check_swing(cur, yesterday, finals) + check_sanity(cur, finals))


def save(cur, today: date, results: list[Result]) -> None:
    cur.execute(TABLE_SQL)
    cur.execute(
        """
        INSERT INTO data_checks (run_date, ok, results, created_at) VALUES (%s, %s, %s, NOW())
        ON CONFLICT (run_date) DO UPDATE SET ok = EXCLUDED.ok, results = EXCLUDED.results, created_at = NOW()
        """,
        (today, all(r.ok for r in results), json.dumps([asdict(r) for r in results])),
    )


def alert(cur, today: date, results: list[Result]) -> int:
    """Push the failures to the creator's devices, once a day. Returns pushes sent."""
    failed = [r for r in results if not r.ok]
    if not failed:
        return 0
    key = f"data-check:{today.isoformat()}"
    if not nlg.claim(cur, [key]):
        return 0
    payload = {
        "title": f"Data check: {len(failed)} problem{'s' if len(failed) != 1 else ''}",
        "body": "; ".join(f"{r.name}: {r.detail}" if r.detail else r.name for r in failed)[:240],
        "url": "/",
        "tag": key.replace(":", "-"),
    }
    return sum(nlg.deliver(cur, key, sub, payload, 12 * 3600) for sub in nlg.creators(cur))


def main(now=None, get=requests.get) -> list[Result]:
    if not DATABASE_URL:
        raise SystemExit("DATABASE_URL is not set")
    today = (now or datetime.now(nlg.EASTERN)).date()
    with psycopg2.connect(DATABASE_URL) as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            results = run_checks(cur, today, get)
            save(cur, today, results)
        conn.commit()
        with conn.cursor() as cur:  # the push helpers read plain tuple rows
            sent = alert(cur, today, results)
    failed = [r for r in results if not r.ok]
    logger.info(f"Data check {today}: {len(results) - len(failed)}/{len(results)} passed"
                + (f"; pushed {sent}: " + "; ".join(f"{r.name} ({r.detail})" for r in failed) if failed else ""))
    return results


if __name__ == "__main__":
    for result in main():
        print(("ok    " if result.ok else "FAIL  ") + result.name + (f" -- {result.detail}" if result.detail else ""))
