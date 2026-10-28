"""
PuckPulse xG for every completed game: each team's expected goals for and
against, from NHL play-by-play scored by xg_model.py. Runs in the daily job
before the playoff odds, which use these totals (falling back to MoneyPuck
when a game is missing).

Each run looks from the latest stored game date (or the season's start on
the first run) through yesterday, and scores only finished games that
aren't stored yet: a couple of score calls and ~16 play-by-play calls on a
typical night.

Also stores each goalie's xG and goals against per game (goalie_game_xg),
and each game's 5-on-5 team and skater rows (team_game_5v5,
player_game_5v5; skaters from the shift chart, or the HTML time-on-ice
reports when the NHL never posts one) for ingest_advanced_stats.py.

Usage:
    python ingest_xg.py                 # the daily run
    python ingest_xg.py --since 2026-10-07
    python ingest_xg.py --retry-days 30  # also retry older games still missing on-ice xG
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
import rapm_stints as rs
import xg_model as xm
from logging_config import setup_logging
from seasons import current_season_id

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
logger = setup_logging("ingest_xg")

SCORE_URL = "https://api-web.nhle.com/v1/score/{date}"
PBP_URL = "https://api-web.nhle.com/v1/gamecenter/{game_id}/play-by-play"
SHIFTS_URL = "https://api.nhle.com/stats/rest/en/shiftcharts?cayenneExp=gameId={game_id}"
MIN_SHIFTS = 100  # a full game has ~700; fewer means the chart isn't posted (or the NHL never posts it)
SHIFT_RETRY_DAYS = 14  # keep checking for a late shift chart this long (2026-10-13's never came)
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
GOALIE_DANGER_SQL = """
ALTER TABLE goalie_game_xg ADD COLUMN IF NOT EXISTS hd_shots SMALLINT;
ALTER TABLE goalie_game_xg ADD COLUMN IF NOT EXISTS hd_goals SMALLINT;
ALTER TABLE goalie_game_xg ADD COLUMN IF NOT EXISTS hd_xg NUMERIC(6,3)
"""

# 5-on-5 per game, for the advanced stats (ingest_advanced_stats.py): each
# team's shot attempts, unblocked attempts, shots, goals and xG for and
# against, and each skater's own xG and on-ice xG (from the shift chart).
FIVE_ON_FIVE_SQL = """
CREATE TABLE IF NOT EXISTS team_game_5v5 (
    game_id     BIGINT NOT NULL,
    team_abbrev VARCHAR(3) NOT NULL,
    season_id   INTEGER NOT NULL,
    game_type   SMALLINT NOT NULL,
    cf SMALLINT NOT NULL, ca SMALLINT NOT NULL, ff SMALLINT NOT NULL, fa SMALLINT NOT NULL,
    sf SMALLINT NOT NULL, sa SMALLINT NOT NULL, gf SMALLINT NOT NULL, ga SMALLINT NOT NULL,
    xgf NUMERIC(6,3) NOT NULL, xga NUMERIC(6,3) NOT NULL,
    has_shifts BOOLEAN NOT NULL,  -- whether player_game_5v5 has its on-ice xG
    PRIMARY KEY (game_id, team_abbrev)
);
CREATE TABLE IF NOT EXISTS player_game_5v5 (
    game_id     BIGINT NOT NULL,
    player_id   INTEGER NOT NULL,
    team_abbrev VARCHAR(3) NOT NULL,
    season_id   INTEGER NOT NULL,
    game_type   SMALLINT NOT NULL,
    ixg         NUMERIC(6,3) NOT NULL,
    onice_xgf   NUMERIC(6,3),             -- NULL without the game's shift chart
    onice_xga   NUMERIC(6,3),
    PRIMARY KEY (game_id, player_id)
);
GRANT SELECT ON team_game_5v5 TO nhl_api_readonly;
GRANT SELECT ON player_game_5v5 TO nhl_api_readonly
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
                                              "xg_against": 0.0, "goals_against": 0, "shots_against": 0,
                                              "hd_shots": 0, "hd_goals": 0, "hd_xg": 0.0})
        xg = xm.predict(shot, model)
        g["xg_against"] += xg
        g["goals_against"] += shot["goal"]
        g["shots_against"] += 1
        if xg >= HIGH_DANGER_XG:
            g["hd_shots"] += 1
            g["hd_goals"] += shot["goal"]
            g["hd_xg"] += xg
    return [{**g, "xg_against": round(g["xg_against"], 3), "hd_xg": round(g["hd_xg"], 3)} for g in faced.values()]


FIVE_ON_FIVE = "1551"
ATTEMPTS = {"goal", "shot-on-goal", "missed-shot", "blocked-shot"}
HIGH_DANGER_XG = 0.20  # MoneyPuck's line for a high-danger shot


def _clock(text):
    minutes, seconds = (text or "0:00").split(":")
    return int(minutes) * 60 + int(seconds)


def team_5v5(pbp, model):
    """
    {team: {cf, ca, ff, fa, sf, sa, gf, ga, xgf, xga}} at 5-on-5: shot
    attempts (Corsi, blocked ones too), unblocked attempts (Fenwick), shots
    on goal, goals, and xG. A blocked shot counts for the shooter's team.
    """
    home, away = pbp["homeTeam"], pbp["awayTeam"]
    abbrev = {home["id"]: home["abbrev"], away["id"]: away["abbrev"]}
    team_of = {r["playerId"]: r["teamId"] for r in pbp.get("rosterSpots", [])}
    out = {a: dict.fromkeys(("cf", "ca", "ff", "fa", "sf", "sa", "gf", "ga", "xgf", "xga"), 0) for a in abbrev.values()}

    def credit(team, other, key, value=1):
        out[team][key + "f"] += value
        out[other][key + "a"] += value

    for play in pbp.get("plays", []):
        if play.get("typeDescKey") not in ATTEMPTS or str(play.get("situationCode") or "").zfill(4) != FIVE_ON_FIVE:
            continue
        if (play.get("periodDescriptor") or {}).get("periodType") == "SO":
            continue
        d = play.get("details") or {}
        team_id = team_of.get(d.get("shootingPlayerId") or d.get("scoringPlayerId"), d.get("eventOwnerTeamId"))
        if team_id not in abbrev:
            continue
        team, other = abbrev[team_id], next(a for i, a in abbrev.items() if i != team_id)
        credit(team, other, "c")
        if play["typeDescKey"] in ("goal", "shot-on-goal"):
            credit(team, other, "s")
        if play["typeDescKey"] == "goal":
            credit(team, other, "g")
    for shot in xm.shots_from_game(pbp):
        if shot["situation"] == FIVE_ON_FIVE:
            team = home["abbrev"] if shot["team_is_home"] else away["abbrev"]
            other = away["abbrev"] if shot["team_is_home"] else home["abbrev"]
            credit(team, other, "f")
            credit(team, other, "xg", xm.predict(shot, model))
    return {t: {k: round(v, 3) if k.startswith("xg") else v for k, v in row.items()} for t, row in out.items()}


def on_ice(shifts, skaters):
    """{(period, second): {player ids}}-style lookup: who was on the ice at a moment (start < t <= end)."""
    by_period = defaultdict(list)
    for s in shifts:
        if s.get("playerId") in skaters and s.get("startTime") and s.get("endTime"):
            by_period[s["period"]].append((_clock(s["startTime"]), _clock(s["endTime"]), s["playerId"]))
    return lambda period, t: {pid for start, end, pid in by_period.get(period, ()) if start < t <= end}


def player_5v5(pbp, shifts, model):
    """
    {player_id: {team, ixg, onice_xgf, onice_xga}} for skaters at 5-on-5:
    xG of his own unblocked shots, and of every unblocked shot for and
    against while he was on the ice (from the game's shift chart; None
    for both without one, shifts=None).
    """
    home, away = pbp["homeTeam"], pbp["awayTeam"]
    abbrev = {home["id"]: home["abbrev"], away["id"]: away["abbrev"]}
    skaters = {r["playerId"]: abbrev.get(r["teamId"]) for r in pbp.get("rosterSpots", []) if r.get("positionCode") != "G"}
    who = on_ice(shifts, skaters) if shifts else None
    out = {}

    def row(pid):
        return out.setdefault(pid, {"team": skaters[pid], "ixg": 0.0, "onice_xgf": 0.0, "onice_xga": 0.0})

    for shot in xm.shots_from_game(pbp):
        if shot["situation"] != FIVE_ON_FIVE:
            continue
        xg = xm.predict(shot, model)
        shooting = home["abbrev"] if shot["team_is_home"] else away["abbrev"]
        if shot["shooter"] in skaters:
            row(shot["shooter"])["ixg"] += xg
        for pid in who(shot["period"], shot["time"]) if who else ():
            row(pid)["onice_xgf" if skaters[pid] == shooting else "onice_xga"] += xg
    rounded = {pid: {k: round(v, 3) if k != "team" else v for k, v in r.items()} for pid, r in out.items()}
    if not who:
        for r in rounded.values():
            r["onice_xgf"] = r["onice_xga"] = None
    return rounded


def store_goalies(cur, game_id, season_id, game_type, pbp, model):
    for g in goalie_totals(pbp, model):
        cur.execute(
            """
            INSERT INTO goalie_game_xg (game_id, goalie_id, team_abbrev, season_id, game_type, xg_against,
                                        goals_against, shots_against, model_version, hd_shots, hd_goals, hd_xg)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (game_id, goalie_id) DO UPDATE SET
                xg_against = EXCLUDED.xg_against, goals_against = EXCLUDED.goals_against,
                shots_against = EXCLUDED.shots_against, model_version = EXCLUDED.model_version,
                hd_shots = EXCLUDED.hd_shots, hd_goals = EXCLUDED.hd_goals, hd_xg = EXCLUDED.hd_xg
            """,
            (game_id, g["goalie"], g["team"], season_id, game_type, g["xg_against"], g["goals_against"],
             g["shots_against"], model.get("version", 1), g["hd_shots"], g["hd_goals"], g["hd_xg"]),
        )


def store_5v5(cur, game_id, season_id, game_type, pbp, shifts, model):
    """
    The game's 5-on-5 team and skater rows. Without its shift chart the
    skaters' on-ice xG is left NULL (has_shifts false) for fill_5v5 to
    retry. Returns whether the on-ice xG is in.
    """
    has_shifts = len(shifts or ()) >= MIN_SHIFTS
    for team, r in team_5v5(pbp, model).items():
        cur.execute(
            """
            INSERT INTO team_game_5v5 (game_id, team_abbrev, season_id, game_type, cf, ca, ff, fa, sf, sa, gf, ga, xgf, xga,
                                       has_shifts)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (game_id, team_abbrev) DO UPDATE SET has_shifts = EXCLUDED.has_shifts
            """,
            (game_id, team, season_id, game_type, r["cf"], r["ca"], r["ff"], r["fa"], r["sf"], r["sa"],
             r["gf"], r["ga"], r["xgf"], r["xga"], has_shifts),
        )
    for pid, r in player_5v5(pbp, shifts if has_shifts else None, model).items():
        cur.execute(
            """
            INSERT INTO player_game_5v5 (game_id, player_id, team_abbrev, season_id, game_type, ixg, onice_xgf, onice_xga)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (game_id, player_id) DO UPDATE SET onice_xgf = EXCLUDED.onice_xgf, onice_xga = EXCLUDED.onice_xga
            """,
            (game_id, pid, r["team"], season_id, game_type, r["ixg"], r["onice_xgf"], r["onice_xga"]),
        )
    return has_shifts


def store_game_extras(cur, game_id, season_id, game_type, pbp, model, get=_get, get_text=None):
    """
    Goalies and 5-on-5 rows for one game; the skaters' on-ice xG once the
    shift chart is up, or from the HTML time-on-ice reports when it isn't.
    """
    store_goalies(cur, game_id, season_id, game_type, pbp, model)
    try:
        shifts = get(SHIFTS_URL.format(game_id=game_id)).get("data", [])
    except requests.RequestException as exc:
        logger.warning(f"Game {game_id}: no shift chart ({exc})")
        shifts = []
    if len(shifts) < MIN_SHIFTS:  # the NHL skips whole stretches of shift charts (2026-10-13 to 10-19)
        try:
            shifts = rs.html_shifts(pbp, get_text or rs._get_text) or []
        except requests.RequestException as exc:
            logger.warning(f"Game {game_id}: no time-on-ice reports ({exc}); its on-ice xG will retry next run")
    return store_5v5(cur, game_id, season_id, game_type, pbp, shifts, model)


def finished_games(since, until, get=_get):
    """[(game_id, date, game_type)] for finished regular-season and playoff games."""
    out, day = [], since
    while day <= until:
        for g in get(SCORE_URL.format(date=day)).get("games", []):
            if g.get("gameState") in FINAL_STATES and g.get("gameType") in (2, 3):
                out.append((g["id"], str(day), g["gameType"]))
        day += timedelta(days=1)
    return out


def update(cur, season_id, since=None, today=None, get=_get, model=None, get_text=None, retry_days=SHIFT_RETRY_DAYS):
    """Score and store finished games not stored yet. Returns games added."""
    model = model or xm.load_model()
    cur.execute(TABLE_SQL)
    cur.execute(STARTER_SQL)
    cur.execute(GOALIE_TABLE_SQL)
    cur.execute(GOALIE_DANGER_SQL)
    cur.execute(FIVE_ON_FIVE_SQL)
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
        store_game_extras(cur, game_id, season_id, game_type, pbp, model, get=get, get_text=get_text)
        added += 1
        time.sleep(0.3)  # polite to the NHL API
    fill_starters(cur, season_id, get=get)
    fill_5v5(cur, season_id, get=get, model=model, today=today, get_text=get_text, retry_days=retry_days)
    return added


def fill_5v5(cur, season_id, get=_get, model=None, today=None, get_text=None, retry_days=SHIFT_RETRY_DAYS):
    """
    Stored games without 5-on-5 rows (stored before those tables existed),
    or from the last retry_days still missing their shift chart:
    fetch the play-by-play and shift chart once more and store their
    goalies and 5-on-5 rows.
    """
    retry_since = (today or date.today()) - timedelta(days=retry_days)
    cur.execute(
        """
        SELECT DISTINCT t.game_id, t.game_type FROM team_game_xg t
        LEFT JOIN team_game_5v5 f ON f.game_id = t.game_id AND f.team_abbrev = t.team_abbrev
        WHERE t.season_id = %s AND (f.game_id IS NULL OR (NOT f.has_shifts AND t.game_date >= %s))
        """,
        (season_id, retry_since),
    )
    model = model or xm.load_model()
    filled = waiting = 0
    for game_id, game_type in cur.fetchall():
        try:
            pbp = get(PBP_URL.format(game_id=game_id))
        except requests.RequestException as exc:
            logger.warning(f"Game {game_id}: no play-by-play for its 5-on-5 rows ({exc}); will retry next run")
            continue
        if store_game_extras(cur, game_id, season_id, game_type, pbp, model, get=get, get_text=get_text):
            filled += 1
        else:
            waiting += 1
        time.sleep(0.3)
    if filled or waiting:
        logger.info(f"Stored 5-on-5 rows for {filled + waiting} games ({waiting} without a shift chart yet)")
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
    parser.add_argument("--retry-days", type=int, default=SHIFT_RETRY_DAYS,
                        help="Retry on-ice xG for games this many days back that are still missing it")
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
        added = update(cur, season_id, since=args.since, retry_days=args.retry_days)
    logger.info(f"Scored xG for {added} new games")


if __name__ == "__main__":
    main()
