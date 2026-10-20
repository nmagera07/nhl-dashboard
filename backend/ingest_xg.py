"""
PuckPulse xG for every completed game: each team's expected goals for and
against, from NHL play-by-play scored by xg_model.py. Runs in the daily job
before the playoff odds, which use these totals (falling back to MoneyPuck
when a game is missing).

Each run looks from the latest stored game date (or the season's start on
the first run) through yesterday, and scores only finished games that
aren't stored yet: a couple of score calls and ~16 play-by-play calls on a
typical night.

Also stores each goalie's xG and goals against per game (goalie_game_xg).

Usage:
    python ingest_xg.py                 # the daily run
    python ingest_xg.py --since 2026-10-07
    python ingest_xg.py --season 20252026 --goalies-from-cache ~/.cache/puckpulse/pbp
"""

import argparse
import os
import time
from collections import defaultdict
from datetime import date, timedelta

import psycopg2
import requests
from dotenv import load_dotenv

import goalie_starts
import xg_model as xm
from logging_config import setup_logging
from seasons import current_season_id

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
logger = setup_logging("ingest_xg")

SCORE_URL = "https://api-web.nhle.com/v1/score/{date}"
PBP_URL = "https://api-web.nhle.com/v1/gamecenter/{game_id}/play-by-play"
HEADERS = {"User-Agent": "nhl-dashboard (personal project)"}
FINAL_STATES = {"OFF", "FINAL"}
SEASON_START = "{year}-09-01"  # 84-game seasons open in late September (2026-27: Sept 29)

TABLE_SQL = """
CREATE TABLE IF NOT EXISTS team_game_xg (
    game_id                 BIGINT NOT NULL,
    team_abbrev             VARCHAR(3) NOT NULL,
    season_id               INTEGER NOT NULL,
    game_date               DATE NOT NULL,
    game_type               SMALLINT NOT NULL,        -- 2 regular season, 3 playoffs
    is_home                 BOOLEAN NOT NULL,
    xg_for                  NUMERIC(6,3) NOT NULL,
    xg_against              NUMERIC(6,3) NOT NULL,
    goals_for               SMALLINT NOT NULL,        -- unblocked-shot goals (no shootout)
    goals_against           SMALLINT NOT NULL,
    shots_for               SMALLINT NOT NULL,        -- unblocked shot attempts
    shots_against           SMALLINT NOT NULL,
    model_version           SMALLINT NOT NULL,
    computed_at             TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (game_id, team_abbrev)
)
"""
# The team's starting goalie (in net for the first shot it faced), for the
# projected starters (goalie_starts.py).
STARTER_SQL = "ALTER TABLE team_game_xg ADD COLUMN IF NOT EXISTS starting_goalie_id INTEGER"

# Each goalie's xG and goals against per game, on the unblocked shots he
# faced: goals saved above expected for the playoff odds' goaltending
# (player_values.our_season_goalies).
GOALIE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS goalie_game_xg (
    game_id                 BIGINT NOT NULL,
    goalie_id               INTEGER NOT NULL,
    team_abbrev             VARCHAR(3) NOT NULL,
    season_id               INTEGER NOT NULL,
    game_type               SMALLINT NOT NULL,
    xg_against              NUMERIC(6,3) NOT NULL,
    goals_against           SMALLINT NOT NULL,
    shots_against           SMALLINT NOT NULL,
    model_version           SMALLINT NOT NULL,
    PRIMARY KEY (game_id, goalie_id)
)
"""


def _get(url):
    for attempt in range(4):
        response = requests.get(url, headers=HEADERS, timeout=30)
        if response.status_code != 429:
            response.raise_for_status()
            return response.json()
        time.sleep(5 * (attempt + 1))
    response.raise_for_status()


def game_totals(pbp, model):
    """[{team, is_home, xg_for, xg_against, goals_*, shots_*}] for both teams in one game."""
    sides = defaultdict(lambda: {"xg": 0.0, "goals": 0, "shots": 0})
    for shot in xm.shots_from_game(pbp):
        side = sides[shot["team_is_home"]]
        side["xg"] += xm.predict(shot, model)
        side["goals"] += shot["goal"]
        side["shots"] += 1
    out = []
    for is_home, team in ((True, pbp["homeTeam"]["abbrev"]), (False, pbp["awayTeam"]["abbrev"])):
        mine, theirs = sides[is_home], sides[not is_home]
        out.append({"team": team, "is_home": is_home,
                    "xg_for": round(mine["xg"], 3), "xg_against": round(theirs["xg"], 3),
                    "goals_for": mine["goals"], "goals_against": theirs["goals"],
                    "shots_for": mine["shots"], "shots_against": theirs["shots"]})
    return out


def goalie_totals(pbp, model):
    """[{goalie, team, xg_against, goals_against, shots_against}] for each goalie who faced a shot."""
    teams = {True: pbp["homeTeam"]["abbrev"], False: pbp["awayTeam"]["abbrev"]}
    faced = {}
    for shot in xm.shots_from_game(pbp):
        if not shot["goalie"]:
            continue  # into an empty net
        g = faced.setdefault(shot["goalie"], {"goalie": shot["goalie"], "team": teams[not shot["team_is_home"]],
                                              "xg_against": 0.0, "goals_against": 0, "shots_against": 0})
        g["xg_against"] += xm.predict(shot, model)
        g["goals_against"] += shot["goal"]
        g["shots_against"] += 1
    return [{**g, "xg_against": round(g["xg_against"], 3)} for g in faced.values()]


def store_goalies(cur, game_id, season_id, game_type, pbp, model):
    for g in goalie_totals(pbp, model):
        cur.execute(
            """
            INSERT INTO goalie_game_xg (game_id, goalie_id, team_abbrev, season_id, game_type, xg_against,
                                        goals_against, shots_against, model_version)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (game_id, goalie_id) DO NOTHING
            """,
            (game_id, g["goalie"], g["team"], season_id, game_type, g["xg_against"], g["goals_against"],
             g["shots_against"], model.get("version", 1)),
        )


def finished_games(since, until, get=_get):
    """[(game_id, date, game_type)] for finished regular-season and playoff games."""
    out, day = [], since
    while day <= until:
        for g in get(SCORE_URL.format(date=day)).get("games", []):
            if g.get("gameState") in FINAL_STATES and g.get("gameType") in (2, 3):
                out.append((g["id"], str(day), g["gameType"]))
        day += timedelta(days=1)
    return out


def update(cur, season_id, since=None, today=None, get=_get, model=None):
    """Score and store finished games not stored yet. Returns games added."""
    model = model or xm.load_model()
    cur.execute(TABLE_SQL)
    cur.execute(STARTER_SQL)
    cur.execute(GOALIE_TABLE_SQL)
    cur.execute("GRANT SELECT ON team_game_xg TO nhl_api_readonly")
    cur.execute("GRANT SELECT ON goalie_game_xg TO nhl_api_readonly")
    cur.execute("SELECT game_id, MAX(game_date) FROM team_game_xg WHERE season_id = %s GROUP BY game_id", (season_id,))
    rows = cur.fetchall()
    stored = {r[0] for r in rows}
    latest = max((r[1] for r in rows), default=None)
    today = today or date.today()
    start = since or (latest - timedelta(days=1) if latest else date.fromisoformat(SEASON_START.format(year=season_id // 10000)))
    added = 0
    for game_id, day, game_type in finished_games(start, today - timedelta(days=1), get=get):
        if game_id in stored:
            continue
        try:
            pbp = get(PBP_URL.format(game_id=game_id))
            totals = game_totals(pbp, model)
            starters = goalie_starts.starters(pbp)
        except requests.RequestException as exc:
            logger.warning(f"Game {game_id}: no play-by-play ({exc}); will retry next run")
            continue
        for t in totals:
            cur.execute(
                """
                INSERT INTO team_game_xg (game_id, team_abbrev, season_id, game_date, game_type, is_home, xg_for, xg_against,
                                          goals_for, goals_against, shots_for, shots_against, model_version,
                                          starting_goalie_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (game_id, team_abbrev) DO NOTHING
                """,
                (game_id, t["team"], season_id, day, game_type, t["is_home"], t["xg_for"], t["xg_against"],
                 t["goals_for"], t["goals_against"], t["shots_for"], t["shots_against"], model.get("version", 1),
                 starters.get(t["team"])),
            )
        store_goalies(cur, game_id, season_id, game_type, pbp, model)
        added += 1
        time.sleep(0.3)  # polite to the NHL API
    fill_starters(cur, season_id, get=get)
    fill_goalies(cur, season_id, get=get, model=model)
    return added


def fill_goalies(cur, season_id, get=_get, model=None):
    """Games stored before goalie_game_xg existed: fetch their play-by-play once and store their goalies."""
    cur.execute(
        """
        SELECT DISTINCT t.game_id, t.game_type FROM team_game_xg t
        WHERE t.season_id = %s AND NOT EXISTS (SELECT 1 FROM goalie_game_xg g WHERE g.game_id = t.game_id)
        """,
        (season_id,),
    )
    model = model or xm.load_model()
    filled = 0
    for game_id, game_type in cur.fetchall():
        try:
            pbp = get(PBP_URL.format(game_id=game_id))
        except requests.RequestException as exc:
            logger.warning(f"Game {game_id}: no play-by-play for its goalies ({exc}); will retry next run")
            continue
        store_goalies(cur, game_id, season_id, game_type, pbp, model)
        filled += 1
        time.sleep(0.3)
    if filled:
        logger.info(f"Stored goalie xG for {filled} earlier games")
    return filled


def backfill_goalies_from_cache(cur, season_id, cache_dir, model=None):
    """
    A past season's goalie xG from cached play-by-play ({cache_dir}/{season}/{game_id}.json.gz,
    train_xg.py's cache), for the goaltending prior's last two seasons. Regular season only.
    """
    import glob
    import gzip
    import json

    model = model or xm.load_model()
    cur.execute(GOALIE_TABLE_SQL)
    cur.execute("GRANT SELECT ON goalie_game_xg TO nhl_api_readonly")
    games = 0
    for path in sorted(glob.glob(os.path.join(cache_dir, str(season_id), "*.json.gz"))):
        with gzip.open(path) as f:
            pbp = json.load(f)
        if pbp.get("gameType") == 2:
            store_goalies(cur, pbp["id"], season_id, 2, pbp, model)
            games += 1
    return games


def fill_starters(cur, season_id, get=_get):
    """Games stored before starters were recorded: fetch their play-by-play once and fill them in."""
    cur.execute("SELECT DISTINCT game_id FROM team_game_xg WHERE season_id = %s AND starting_goalie_id IS NULL",
                (season_id,))
    filled = 0
    for (game_id,) in cur.fetchall():
        try:
            starters = goalie_starts.starters(get(PBP_URL.format(game_id=game_id)))
        except requests.RequestException as exc:
            logger.warning(f"Game {game_id}: no play-by-play for its starters ({exc}); will retry next run")
            continue
        for team, goalie in starters.items():
            cur.execute("UPDATE team_game_xg SET starting_goalie_id = %s WHERE game_id = %s AND team_abbrev = %s",
                        (goalie, game_id, team))
        filled += 1
        time.sleep(0.3)
    if filled:
        logger.info(f"Filled in starting goalies for {filled} earlier games")
    return filled


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--since", type=date.fromisoformat, default=None)
    parser.add_argument("--season", type=int, default=None)
    parser.add_argument("--goalies-from-cache", default=None, metavar="DIR",
                        help="Backfill --season's goalie xG from cached play-by-play instead of the daily run")
    args = parser.parse_args()
    if not DATABASE_URL:
        raise SystemExit("DATABASE_URL is not set")
    season_id = args.season or current_season_id()
    with psycopg2.connect(DATABASE_URL) as conn, conn.cursor() as cur:
        if args.goalies_from_cache:
            games = backfill_goalies_from_cache(cur, season_id, args.goalies_from_cache)
            logger.info(f"Stored goalie xG for {games} games of {season_id} from the cache")
            return
        added = update(cur, season_id, since=args.since)
    logger.info(f"Scored xG for {added} new games")


if __name__ == "__main__":
    main()
