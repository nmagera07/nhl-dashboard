"""
Projected starting goalies: each goalie's chance to start a team's next
game, from who has been starting.

  weight = PRIOR_GAMES x his share of the team's starts last season
         + his starts this season, the latest counting most (each start's
           weight halves every HALF_LIFE team games back)
  On the second night of a back-to-back, the goalie who started the night
  before keeps only B2B_SAME of his weight: teams usually give the backup
  the second night (the #1 starts 64% of normal nights, 35% of second
  nights, 2022-26).
Chances are the weights normalized over the candidates (the team's
current goalies), with a small floor so a goalie without starts still
gets one.

Daily (run_daily_ingest.py, after the prediction log): for each team
playing today, its current goalies (the NHL's roster, which leaves out
injured reserve), this season's starters (team_game_xg, recorded by
ingest_xg.py), last night's starter, and last season's split (the NHL's
club stats), stored in goalie_projections for the API.

    python goalie_starts.py

Fit on 2022-26 (10,112 team-games) by backtest_goalie_starts.py: the top
projected goalie started 65.6% of the time (log loss 0.78; it was 0.87
with gentler back-to-back and prior settings), and the chances are
calibrated within a few points. NHL teams announce starters
only shortly before puck drop (and the NHL's own feed only once the game
starts), so these are labeled "projected".
"""

import os
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import psycopg2
import requests
from dotenv import load_dotenv

from logging_config import setup_logging
from seasons import current_season_id

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
logger = setup_logging("goalie_starts")

SCORE_URL = "https://api-web.nhle.com/v1/score/{date}"
ROSTER_URL = "https://api-web.nhle.com/v1/roster/{team}/current"
CLUB_STATS_URL = "https://api-web.nhle.com/v1/club-stats/{team}/{season}/2"
HEADERS = {"User-Agent": "nhl-dashboard (personal project)"}
NOT_STARTED = {"FUT", "PRE"}
EASTERN = ZoneInfo("America/New_York")

TABLE_SQL = """
CREATE TABLE IF NOT EXISTS goalie_projections (
    game_id                 BIGINT NOT NULL,
    game_date               DATE NOT NULL,
    team_abbrev             VARCHAR(3) NOT NULL,
    goalie_id               INTEGER NOT NULL,
    goalie_name             VARCHAR(60) NOT NULL,
    start_prob              NUMERIC(4,3) NOT NULL,
    computed_at             TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (game_id, goalie_id)
)
"""

PRIOR_GAMES = 0.5  # last season's split only matters until a few starts are in
HALF_LIFE = 8.0
B2B_SAME = 0.05   # starting both nights of a back-to-back is rare
FLOOR = 0.3
RECENT_GAMES = 20  # how far back a goalie still counts as a candidate in the backtest


def start_probabilities(candidates, season_starters, prior_split, started_last_night=None):
    """
    {goalie: chance to start}. candidates: the team's goalies to choose
    from; season_starters: this season's starters, oldest first;
    prior_split: {goalie: share of last season's starts};
    started_last_night: the goalie who started the night before, if the
    team played then.
    """
    weights = {g: FLOOR + PRIOR_GAMES * prior_split.get(g, 0.0) for g in candidates}
    for back, goalie in enumerate(reversed(season_starters)):
        if goalie in weights:
            weights[goalie] += 0.5 ** (back / HALF_LIFE)
    if started_last_night in weights and len(weights) > 1:
        weights[started_last_night] *= B2B_SAME
    total = sum(weights.values())
    return {g: w / total for g, w in weights.items()}


SHOT_EVENTS = ("shot-on-goal", "goal", "missed-shot", "blocked-shot")


def starters(pbp):
    """{team abbrev: goalie id in net for the first shot that team faced} from a game's play-by-play."""
    home, away = pbp["homeTeam"], pbp["awayTeam"]
    out = {}
    for play in pbp.get("plays", []):
        details = play.get("details") or {}
        goalie = details.get("goalieInNetId")
        if not goalie or play.get("typeDescKey") not in SHOT_EVENTS:
            continue
        defending = away["abbrev"] if details.get("eventOwnerTeamId") == home["id"] else home["abbrev"]
        out.setdefault(defending, goalie)
        if len(out) == 2:
            break
    return out


def _get(url):
    response = requests.get(url, headers=HEADERS, timeout=20)
    response.raise_for_status()
    return response.json()


def _name(player):
    return f"{player['firstName']['default']} {player['lastName']['default']}"


def team_projection(cur, team, season_id, day, get=_get):
    """[(goalie id, name, chance)] for a team's game on `day`, likeliest first."""
    goalies = {g["id"]: _name(g) for g in get(ROSTER_URL.format(team=team)).get("goalies", [])}
    if not goalies:
        return []
    cur.execute(
        """
        SELECT game_date, starting_goalie_id FROM team_game_xg
        WHERE season_id = %s AND team_abbrev = %s AND game_type = 2 AND starting_goalie_id IS NOT NULL AND game_date < %s
        ORDER BY game_date
        """,
        (season_id, team, day),
    )
    history = cur.fetchall()
    last_night = next((g for d, g in history if d == day - timedelta(days=1)), None)
    try:
        last_season = get(CLUB_STATS_URL.format(team=team, season=season_id - 10001)).get("goalies", [])
    except requests.RequestException:
        last_season = []
    started = sum(g.get("gamesStarted") or 0 for g in last_season) or 1
    prior = {g["playerId"]: (g.get("gamesStarted") or 0) / started for g in last_season}
    probs = start_probabilities(set(goalies), [g for _, g in history], prior, started_last_night=last_night)
    return sorted(((g, goalies[g], round(p, 3)) for g, p in probs.items()), key=lambda r: -r[2])


def log_today(day=None, get=_get):
    day = day or datetime.now(EASTERN).date()
    season_id = current_season_id(day)
    games = [g for g in get(SCORE_URL.format(date=day)).get("games", [])
             if g.get("gameState") in NOT_STARTED and g.get("gameType") in (2, 3)]
    logged = 0
    with psycopg2.connect(DATABASE_URL) as conn, conn.cursor() as cur:
        cur.execute(TABLE_SQL)
        cur.execute("GRANT SELECT ON goalie_projections TO nhl_api_readonly")
        for g in games:
            for side in ("homeTeam", "awayTeam"):
                team = g[side]["abbrev"]
                try:
                    rows = team_projection(cur, team, season_id, day, get=get)
                except requests.RequestException as exc:
                    logger.warning(f"{team}: no roster ({exc}); skipping")
                    continue
                for goalie_id, name, prob in rows:
                    cur.execute(
                        """
                        INSERT INTO goalie_projections (game_id, game_date, team_abbrev, goalie_id, goalie_name, start_prob)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        ON CONFLICT (game_id, goalie_id) DO UPDATE
                        SET start_prob = EXCLUDED.start_prob, goalie_name = EXCLUDED.goalie_name, computed_at = NOW()
                        """,
                        (g["id"], day, team, goalie_id, name, prob),
                    )
                logged += 1
                time.sleep(0.2)
    logger.info(f"Projected starting goalies for {logged} teams on {day}")
    return logged


if __name__ == "__main__":
    if not DATABASE_URL:
        raise SystemExit("DATABASE_URL is not set")
    log_today()
