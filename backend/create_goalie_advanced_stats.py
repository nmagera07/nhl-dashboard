"""
One-off: create goalie_advanced_stats on the database in DATABASE_URL
(the owner credential in backend/.env) and let the API's role read it.
Same DDL as schema.sql. Safe to run twice.

    cd backend && .venv/bin/python create_goalie_advanced_stats.py
"""

import os

import psycopg2
from dotenv import load_dotenv

load_dotenv()

DDL = """
CREATE TABLE IF NOT EXISTS goalie_advanced_stats (
    id                      SERIAL PRIMARY KEY,
    player_id               INTEGER NOT NULL REFERENCES players(player_id),
    season_id               INTEGER NOT NULL,
    games_played            INTEGER,
    icetime_seconds         INTEGER,
    shots_faced             INTEGER,
    goals_allowed           INTEGER,
    xgoals_against          NUMERIC(8,3),
    high_danger_shots       INTEGER,
    high_danger_goals       INTEGER,
    high_danger_xgoals      NUMERIC(8,3),
    updated_at              TIMESTAMP DEFAULT NOW(),
    UNIQUE (season_id, player_id)
);
GRANT SELECT ON goalie_advanced_stats TO nhl_api_readonly;
"""

with psycopg2.connect(os.environ["DATABASE_URL"]) as conn:
    with conn.cursor() as cur:
        cur.execute(DDL)
print("goalie_advanced_stats is ready (and readable by nhl_api_readonly).")
