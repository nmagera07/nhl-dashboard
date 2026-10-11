"""
One-time setup for the prediction track record. Run from backend/ (after
the release that adds game_predictions.py):

    .venv/bin/python scripts/setup_prediction_log.py

1. Creates the game_predictions table; the API's read-only role can read it.
2. Backfills the games the morning digests predicted before this existed
   (their pre-game odds, rounded to whole percents) and grades the ones
   that are final. Safe to re-run: logged predictions are never changed.
"""

import sys
from pathlib import Path

import psycopg2
from dotenv import dotenv_values

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))
env = dotenv_values(BACKEND / ".env")
if not env.get("DATABASE_URL"):
    sys.exit("DATABASE_URL is missing from backend/.env")

import game_predictions as gp  # noqa: E402
from daily_digest import today_eastern  # noqa: E402

schema = (BACKEND / "schema.sql").read_text()
start = schema.index("CREATE TABLE IF NOT EXISTS game_predictions")
end = schema.index("WHERE home_won IS NULL;", start) + len("WHERE home_won IS NULL;")

with psycopg2.connect(env["DATABASE_URL"]) as conn, conn.cursor() as cur:
    print("1/2 Table and grant...")
    cur.execute(schema[start:end])
    cur.execute("GRANT SELECT ON game_predictions TO nhl_api_readonly")
    print("2/2 Backfill from the morning digests...")
    added = gp.backfill_from_digest(cur)
    graded = gp.grade(cur, today_eastern())
print(f"Done: {added} predictions backfilled, {graded} graded. The daily job logs the rest from tomorrow.")
