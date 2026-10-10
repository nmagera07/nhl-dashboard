"""
Goal and final-score push notifications. Run every minute during game
hours by the nhl-live-notifier Container Apps Job.

Each run reads the NHL's live scoreboard (one request covers every game),
turns new goals and finals into events, claims each event in the database
(so overlapping runs never double-send), and pushes it to everyone
following either team. Most runs find nothing new and exit in a second or
two without touching the database.
"""

import logging
import os
from datetime import datetime, timedelta, timezone

import psycopg2
import psycopg2.extras
import requests
from dotenv import load_dotenv

import push
from logging_config import setup_logging

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

logger = setup_logging("notify_live_games")

SCORE_URL = "https://api-web.nhle.com/v1/score/now"
RECENT = timedelta(hours=6)  # ignore games that started longer ago (yesterday's finals linger in the feed)
GOAL_STATES = {"LIVE", "CRIT", "FINAL"}  # FINAL too: an overtime winner can arrive with the final whistle
FINAL_STATES = {"FINAL", "OFF"}
STRENGTH = {"pp": "power play", "sh": "shorthanded", "en": "empty net"}


def _period(descriptor):
    if not descriptor:
        return ""
    if descriptor.get("periodType") == "SO":
        return "SO"
    if descriptor.get("periodType") == "OT":
        n = descriptor["number"] - descriptor.get("maxRegulationPeriods", 3)
        return "OT" if n <= 1 else f"{n}OT"
    return ["1st", "2nd", "3rd"][descriptor["number"] - 1] if descriptor["number"] <= 3 else f"{descriptor['number']}th"


def _scoreline(away, home, away_score, home_score):
    return f"{away} {away_score}, {home} {home_score}"


def goal_event(game, goal):
    away, home = game["awayTeam"]["abbrev"], game["homeTeam"]["abbrev"]
    scorer = goal.get("name", {}).get("default", "Goal")
    if goal.get("goalsToDate"):
        scorer += f" ({goal['goalsToDate']})"
    assists = [n for n in (a.get("name", {}).get("default") for a in goal.get("assists", [])) if n]
    credit = f"{scorer} from {', '.join(assists)}" if assists else f"{scorer}, unassisted"
    when = f"{_period(goal.get('periodDescriptor'))} {goal.get('timeInPeriod', '')}".strip()
    strength = STRENGTH.get(goal.get("strength"))
    return {
        "key": f"goal:{game['id']}:{goal.get('period')}:{goal.get('timeInPeriod')}:{goal.get('teamAbbrev')}",
        "kind": "goals",
        "teams": [away, home],
        "payload": {
            "title": f"🚨 {goal.get('teamAbbrev')} goal! {_scoreline(away, home, goal.get('awayScore'), goal.get('homeScore'))}",
            "body": " · ".join(filter(None, [credit, strength, when])),
            "url": f"/games/{game['id']}",
            "tag": f"game-{game['id']}",
        },
    }


def final_event(game):
    away, home = game["awayTeam"], game["homeTeam"]
    last = (game.get("gameOutcome") or {}).get("lastPeriodType", "REG")
    suffix = f" ({last})" if last in ("OT", "SO") else ""
    winner = away if away.get("score", 0) > home.get("score", 0) else home
    return {
        "key": f"final:{game['id']}",
        "kind": "finals",
        "teams": [away["abbrev"], home["abbrev"]],
        "payload": {
            "title": f"Final{suffix}: {_scoreline(away['abbrev'], home['abbrev'], away.get('score'), home.get('score'))}",
            "body": f"{winner['abbrev']} wins. Tap for the box score.",
            "url": f"/games/{game['id']}",
            "tag": f"game-{game['id']}",
        },
    }


def events_for(games, now):
    """
    New-event candidates from the scoreboard. Per game, only the newest
    goal is a candidate: two goals inside one minute is rare, and the phone
    would only show the latest anyway (notifications share a per-game tag).
    The older ones are still claimed, so they're never sent late.
    """
    candidates, claim_only = [], []
    for game in games:
        start = game.get("startTimeUTC")
        if not start or now - datetime.fromisoformat(start.replace("Z", "+00:00")) > RECENT:
            continue
        state = game.get("gameState")
        if state in GOAL_STATES and game.get("goals"):
            goals = [goal_event(game, g) for g in game["goals"]]
            candidates.append(goals[-1])
            claim_only.extend(goals[:-1])
        if state in FINAL_STATES:
            candidates.append(final_event(game))
    return candidates, claim_only


def claim(cur, keys):
    """Mark events as sent; returns the ones this run claimed first."""
    if not keys:
        return set()
    rows = psycopg2.extras.execute_values(
        cur,
        "INSERT INTO push_events_sent (event_key) VALUES %s ON CONFLICT DO NOTHING RETURNING event_key",
        [(k,) for k in keys],
        fetch=True,
    )
    return {r[0] for r in rows}


def subscribers(cur, teams, kind):
    column = {"goals": "notify_goals", "finals": "notify_finals"}[kind]
    cur.execute(
        f"SELECT endpoint, p256dh, auth FROM push_subscriptions WHERE teams && %s::text[] AND {column}",
        (teams,),
    )
    return [{"endpoint": e, "p256dh": p, "auth": a} for e, p, a in cur.fetchall()]


def run(now=None, fetch=None):
    now = now or datetime.now(timezone.utc)
    games = (fetch or (lambda: requests.get(SCORE_URL, timeout=15).json()))().get("games", [])
    candidates, claim_only = events_for(games, now)
    if not candidates:
        return 0

    sent = 0
    with psycopg2.connect(DATABASE_URL) as conn, conn.cursor() as cur:
        claim(cur, [e["key"] for e in claim_only])
        fresh = claim(cur, [e["key"] for e in candidates])
        conn.commit()  # claimed before sending: a crash mid-send can't cause a duplicate later
        for event in (e for e in candidates if e["key"] in fresh):
            for sub in subscribers(cur, event["teams"], event["kind"]):
                try:
                    push.send(sub, event["payload"])
                    sent += 1
                except push.SubscriptionGone:
                    cur.execute("DELETE FROM push_subscriptions WHERE endpoint = %s", (sub["endpoint"],))
            logger.info("%s -> %s", event["key"], event["payload"]["title"])
        cur.execute("DELETE FROM push_events_sent WHERE sent_at < NOW() - INTERVAL '3 days'")
    return sent


if __name__ == "__main__":
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logger.info("Sent %d notifications", run())
