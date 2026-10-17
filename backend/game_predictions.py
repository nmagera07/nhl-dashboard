"""
The model's game-by-game track record.

Every morning (in the daily job, right after the playoff-odds run) this:
  1. logs today's games with the model's home-win probability, before any
     of them start, and each team's expected goals (goal_model.py: the
     total from team scoring rates, split so the score distribution agrees
     with the win probability; the puck line and total follow), and
  2. grades every earlier prediction whose game has since gone final.

A logged prediction is never changed (re-runs skip games already logged),
so the record can't be quietly improved after the fact. The API scores
the graded rows with prediction_record.track_record().

    python game_predictions.py                         # log today + grade (the daily job)
    python game_predictions.py --backfill-from-digest  # one-time: the digests' pre-game odds
"""

import argparse
import logging
import math
import os
from datetime import date

import psycopg2
from dotenv import load_dotenv

import goal_model
import nhl_games
import simulate_playoff_odds as sim
from daily_digest import today_eastern
from logging_config import setup_logging

load_dotenv()
logger = setup_logging("game_predictions")

DATABASE_URL = os.getenv("DATABASE_URL")
NOT_STARTED = {"FUT", "PRE"}
FINAL_STATES = {"FINAL", "OFF"}


# The goal model's team ratings: half goals, half xG per game, shrunk toward
# last season (pulled 30% toward the league) with 40 pseudo-games.
SCORING_XG_WEIGHT = 0.5
SCORING_PRIOR_GAMES = 40
SCORING_CARRYOVER = 0.7


def scoring_ratings(prior: dict, seen: dict) -> tuple[dict, float]:
    """
    ({team: {"offense", "defense"}}, league average): goals scored and
    allowed per game. prior: {team: (games, goals for, goals against)} last
    season; seen: {team: (games, goals for, goals against, xG for, xG
    against)} this season so far. Both count empty-netters and overtime
    goals, not shootouts.
    """
    prior_league = (sum(f for _, f, _ in prior.values()) / max(sum(n for n, _, _ in prior.values()), 1)) or 3.0
    goals = sum(v[1] for v in seen.values())
    xg = sum(v[3] for v in seen.values())
    xg_scale = goals / xg if goals and xg else 1.0  # xG on the goals scale
    ratings = {}
    for team in set(prior) | set(seen):
        pn, pf, pa = prior.get(team, (0, 0, 0))
        base_for = prior_league + SCORING_CARRYOVER * (pf / pn - prior_league) if pn else prior_league
        base_against = prior_league + SCORING_CARRYOVER * (pa / pn - prior_league) if pn else prior_league
        n, gf, ga, xf, xa = seen.get(team, (0, 0, 0, 0.0, 0.0))
        w = SCORING_XG_WEIGHT
        ratings[team] = {
            "offense": ((1 - w) * gf + w * xf * xg_scale + SCORING_PRIOR_GAMES * base_for) / (n + SCORING_PRIOR_GAMES),
            "defense": ((1 - w) * ga + w * xa * xg_scale + SCORING_PRIOR_GAMES * base_against) / (n + SCORING_PRIOR_GAMES),
        }
    league = sum(r["offense"] + r["defense"] for r in ratings.values()) / (2 * max(len(ratings), 1))
    return ratings, league


def load_scoring_ratings(cur, season_id: int, day: date) -> tuple[dict, float]:
    cur.execute("SELECT team_abbrev, games_played, goal_for, goal_against FROM season_final_standings WHERE season_id = %s",
                (season_id - 10001,))
    prior = {t: (n, f, a) for t, n, f, a in cur.fetchall()}
    cur.execute(
        """
        SELECT team_abbrev, COUNT(*), SUM(goals_for), SUM(goals_against), SUM(xg_for), SUM(xg_against)
        FROM team_game_xg WHERE season_id = %s AND game_type = 2 AND game_date < %s GROUP BY team_abbrev
        """,
        (season_id, day),
    )
    seen = {t: (n, gf, ga, float(xf), float(xa)) for t, n, gf, ga, xf, xa in cur.fetchall()}
    return scoring_ratings(prior, seen)


def expected_goals(home: str, away: str, home_win_prob: float, b2b, scoring) -> tuple:
    """(home goals, away goals) for the goal model, or (None, None) without ratings for both teams."""
    ratings, league = scoring or ({}, 0)
    if home not in ratings or away not in ratings:
        return None, None
    total = goal_model.expected_total(ratings[home], ratings[away], league, *b2b)
    return goal_model.split_for_win_prob(total, home_win_prob)


def predictions(games: list[dict], payload: dict, day: date, scoring=None) -> list[dict]:
    """Today's not-yet-started games with the model's home-win probability and expected goals."""
    teams = payload.get("teams", {})
    model = payload.get("model", {})
    scale = model.get("scale", sim.SCALE)
    # Back-to-back flags ride along in the saved schedule ([date, home, away, home_b2b, away_b2b]).
    b2b = {(row[0], row[1], row[2]): row[3:5] for row in payload.get("games", []) if len(row) >= 5}
    rows = []
    for g in games:
        if g.get("gameState") not in NOT_STARTED:
            continue
        home, away = g["homeTeam"]["abbrev"], g["awayTeam"]["abbrev"]
        if home not in teams or away not in teams:  # e.g. an exhibition against a non-NHL team
            continue
        hr, ar = teams[home]["rating"], teams[away]["rating"]
        flags = tuple(b2b.get((str(day), home, away), ()))
        p = round(1 / (1 + math.exp(-(hr - ar + sim.home_margin(*flags, model=model)) / scale)), 4)
        home_goals, away_goals = expected_goals(home, away, p, flags or (False, False), scoring)
        rows.append({
            "game_id": g["id"], "season_id": payload["season_id"], "game_date": day,
            "home_abbrev": home, "away_abbrev": away,
            "home_win_prob": p, "home_goals": home_goals, "away_goals": away_goals,
            "home_rating": hr, "away_rating": ar,
            "model_version": model.get("version", sim.MODEL_VERSION), "source": "daily",
        })
    return rows


def outcome(game: dict) -> dict | None:
    """A final game's result, or None if it isn't final yet."""
    if game.get("gameState") not in FINAL_STATES:
        return None
    hs, as_ = game["homeTeam"].get("score"), game["awayTeam"].get("score")
    if hs is None or as_ is None or hs == as_:
        return None
    ended = (game.get("gameOutcome") or {}).get("lastPeriodType") or "REG"
    return {"home_score": hs, "away_score": as_, "ended": ended, "home_won": hs > as_}


# Each team's expected regulation goals, not counting empty-netters (goal_model.py).
COLUMNS_SQL = """
ALTER TABLE game_predictions ADD COLUMN IF NOT EXISTS home_goals NUMERIC(4,3);
ALTER TABLE game_predictions ADD COLUMN IF NOT EXISTS away_goals NUMERIC(4,3);
"""

INSERT = """
    INSERT INTO game_predictions (game_id, season_id, game_date, home_abbrev, away_abbrev, home_win_prob,
                                  home_goals, away_goals, home_rating, away_rating, model_version, source)
    VALUES (%(game_id)s, %(season_id)s, %(game_date)s, %(home_abbrev)s, %(away_abbrev)s, %(home_win_prob)s,
            %(home_goals)s, %(away_goals)s, %(home_rating)s, %(away_rating)s, %(model_version)s, %(source)s)
    ON CONFLICT (game_id) DO NOTHING
"""


def log_today(cur, day: date) -> int:
    cur.execute("SELECT payload FROM season_sim_inputs ORDER BY season_id DESC LIMIT 1")
    row = cur.fetchone()
    payload = row[0] if row else None
    # Stale ratings (the odds run failed today) would log a prediction the
    # model didn't really make today; skip rather than pretend.
    if not payload or payload.get("as_of_date") != day.isoformat():
        logger.warning(f"No simulator inputs for {day}; not logging predictions")
        return 0
    cur.execute(COLUMNS_SQL)
    scoring = load_scoring_ratings(cur, payload["season_id"], day)
    rows = predictions(nhl_games.games_on_date(day), payload, day, scoring)
    for r in rows:
        cur.execute(INSERT, r)
    return len(rows)


def grade(cur, today: date) -> int:
    cur.execute("SELECT DISTINCT game_date FROM game_predictions WHERE home_won IS NULL AND game_date < %s", (today,))
    graded = 0
    for (day,) in cur.fetchall():
        for g in nhl_games.games_on_date(day):
            result = outcome(g)
            if result is None:
                continue
            cur.execute(
                """
                UPDATE game_predictions SET home_score = %(home_score)s, away_score = %(away_score)s,
                    ended = %(ended)s, home_won = %(home_won)s, graded_at = NOW()
                WHERE game_id = %(game_id)s AND home_won IS NULL
                """,
                {**result, "game_id": g["id"]},
            )
            graded += cur.rowcount
    return graded


def digest_predictions(facts: dict, games: list[dict], day: date, season_id: int) -> list[dict]:
    """
    Pre-game odds from a morning digest (rounded to whole percents, stored
    before puck drop), matched to that day's game IDs. Used once, to backfill
    the days before this log existed.
    """
    ids = {(g["homeTeam"]["abbrev"], g["awayTeam"]["abbrev"]): g["id"] for g in games}
    rows = []
    for t in facts.get("tonight", []):
        game_id = ids.get((t["home"], t["away"]))
        if game_id is None or t.get("model_home_win_pct") is None:
            continue
        rows.append({
            "game_id": game_id, "season_id": season_id, "game_date": day,
            "home_abbrev": t["home"], "away_abbrev": t["away"],
            "home_win_prob": round(t["model_home_win_pct"] / 100, 4), "home_goals": None, "away_goals": None,
            "home_rating": None, "away_rating": None, "model_version": sim.MODEL_VERSION, "source": "digest",
        })
    return rows


def backfill_from_digest(cur) -> int:
    cur.execute("SELECT digest_date, facts FROM daily_digest ORDER BY digest_date")
    added = 0
    for day, facts in cur.fetchall():
        season_id = sim.current_season_id(day)
        for r in digest_predictions(facts, nhl_games.games_on_date(day), day, season_id):
            cur.execute(INSERT, r)
            added += cur.rowcount
    return added


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--backfill-from-digest", action="store_true")
    args = parser.parse_args()
    if not DATABASE_URL:
        raise SystemExit("DATABASE_URL is not set")
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    day = today_eastern()
    with psycopg2.connect(DATABASE_URL) as conn, conn.cursor() as cur:
        if args.backfill_from_digest:
            logger.info(f"Backfilled {backfill_from_digest(cur)} predictions from morning digests")
        else:
            logger.info(f"Logged {log_today(cur, day)} predictions for {day}")
        logger.info(f"Graded {grade(cur, day)} predictions")


if __name__ == "__main__":
    main()
