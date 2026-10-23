"""
One-time setup for the site's feedback form. Run from backend/:

    .venv/bin/python scripts/setup_feedback.py

Creates the feedback table and lets the API's role insert into it (only
insert: it can't read feedback back). Safe to re-run.
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

import feedback  # noqa: E402

with psycopg2.connect(env["DATABASE_URL"]) as conn, conn.cursor() as cur:
    cur.execute(feedback.TABLE_SQL)
    cur.execute(feedback.GRANTS_SQL)
print("Done: feedback is ready.")
