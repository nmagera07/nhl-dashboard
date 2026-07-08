"""
NHL Stats Dashboard — API layer

A thin FastAPI service that reads from the standings_snapshots table
and serves it up as JSON, ready for a frontend to consume.

Setup:
    pip install fastapi uvicorn[standard] psycopg2-binary python-dotenv --break-system-packages

Run locally:
    uvicorn api:app --reload

Then visit http://127.0.0.1:8000/docs for interactive API docs (FastAPI
generates this automatically from the code below).
"""

import os
from datetime import date
from typing import Optional

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

DATABASE_URL = os.environ["DATABASE_URL"]

app = FastAPI(
    title="NHL Stats Dashboard API",
    description="Serves NHL standings data collected from the NHL public API.",
    version="0.1.0",
)

# Allow a frontend running on a different port/origin to call this API.
# Tighten this to your actual frontend URL once you deploy.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


def get_connection():
    return psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)


@app.get("/")
def root():
    return {"status": "ok", "message": "NHL Stats Dashboard API is running"}


@app.get("/teams")
def list_teams():
    """List all teams we have data for."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM teams ORDER BY team_name")
            return cur.fetchall()
    finally:
        conn.close()


@app.get("/standings/latest")
def latest_standings():
    """Most recent day's standings for every team, ranked by league position."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT s.*, t.team_name, t.common_name, t.division, t.conference
                FROM standings_snapshots s
                JOIN teams t ON t.team_abbrev = s.team_abbrev
                WHERE s.snapshot_date = (SELECT MAX(snapshot_date) FROM standings_snapshots)
                ORDER BY s.league_sequence ASC
                """
            )
            return cur.fetchall()
    finally:
        conn.close()


@app.get("/standings/{team_abbrev}")
def team_history(team_abbrev: str, start: Optional[date] = None, end: Optional[date] = None):
    """
    Full snapshot history for one team, e.g. /standings/PIT
    Optionally filter with ?start=2026-01-01&end=2026-04-01
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            query = """
                SELECT s.*, t.team_name
                FROM standings_snapshots s
                JOIN teams t ON t.team_abbrev = s.team_abbrev
                WHERE s.team_abbrev = %s
            """
            params = [team_abbrev.upper()]

            if start:
                query += " AND s.snapshot_date >= %s"
                params.append(start)
            if end:
                query += " AND s.snapshot_date <= %s"
                params.append(end)

            query += " ORDER BY s.snapshot_date ASC"

            cur.execute(query, params)
            rows = cur.fetchall()
            if not rows:
                raise HTTPException(status_code=404, detail=f"No data found for team '{team_abbrev}'")
            return rows
    finally:
        conn.close()