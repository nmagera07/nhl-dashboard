"""
One-time setup for the "Beat PuckPulse" pick'em. Run from backend/ (after
the release that adds pickem.py):

    .venv/bin/python scripts/setup_pickem.py

Creates pickem_players, pickem_picks and game_results, and lets the API's
read-only role read and write the pick'em tables (and read results). Safe
to re-run.
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

import pickem  # noqa: E402

with psycopg2.connect(env["DATABASE_URL"]) as conn, conn.cursor() as cur:
    cur.execute(pickem.TABLES_SQL)
    cur.execute(pickem.GRANTS_SQL)
print("Done: pickem_players, pickem_picks and game_results are ready.")
