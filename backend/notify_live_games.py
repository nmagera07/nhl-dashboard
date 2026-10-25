"""
Goal and final-score push notifications. Run every minute during game
hours by the puckpulse-live-notifier Azure Function (notifier_function/).

Each run reads the NHL's live scoreboard (one request covers every game),
turns new goals and finals into events, claims each event in the database
(so overlapping runs never double-send), and pushes it to everyone
following either team. Most runs find nothing new and exit in a second or
two without touching the database.
"""

import logging
import os
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from urllib.parse import urlparse

import psycopg2
import psycopg2.extras
import requests
from dotenv import load_dotenv

import push
from logging_config import setup_logging

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

# Console only: neither the function nor the old job keeps local files.
logger = setup_logging("notify_live_games", log_to_file=False)

SCORE_URL = "https://api-web.nhle.com/v1/score/now"
SWING_URL = "https://nhl-dashboard-api.bravecoast-a5240643.westus2.azurecontainerapps.io/swing-of-the-night?date={day}"
EASTERN = ZoneInfo("America/New_York")
REMINDER_HOURS = range(10, 14)  # ET: the morning after, once the nightly run has finished
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
    # Keyed by the score it made, not its clock time: the NHL corrects a
    # goal's time a few seconds after posting it (17:49 -> 17:50), and a
    # time-based key sent the corrected goal again as a new one.
    score = f"{goal.get('awayScore')}-{goal.get('homeScore')}"
    return {
        "key": f"goal:{game['id']}:{goal.get('teamAbbrev')}:{score}",
        "kind": "goals",
        # An idle Android phone can hold even high-urgency pushes until it's
        # picked up; past the TTL the push service drops them and the alert
        # never shows (two goals on 2026-10-16). A late alert beats none.
        "ttl": 60 * 60,
        "teams": [away, home],
        "payload": {
            "title": f"🚨 {goal.get('teamAbbrev')} goal! {_scoreline(away, home, goal.get('awayScore'), goal.get('homeScore'))}",
            "body": " · ".join(filter(None, [credit, strength, when])),
            "url": f"/games/{game['id']}",
            # One notification per goal (they stack, grouped under the app):
            # a shared per-game tag replaced the last goal, and Android often
            # played the replacement silently, so it felt like one alert a game.
            "tag": f"goal-{game['id']}-{score}",
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
        # For pick'em scoring: recorded when the final is first seen.
        "result": {"game_id": game["id"], "home_won": home.get("score", 0) > away.get("score", 0),
                   "home_score": home.get("score"), "away_score": away.get("score")},
        "ttl": 3 * 60 * 60,  # still worth seeing when the phone wakes up
        "teams": [away["abbrev"], home["abbrev"]],
        "payload": {
            "title": f"Final{suffix}: {_scoreline(away['abbrev'], home['abbrev'], away.get('score'), home.get('score'))}",
            "body": f"{winner['abbrev']} wins. Tap for the box score.",
            "url": f"/games/{game['id']}",
            "tag": f"final-{game['id']}",
        },
    }


def events_for(games, now):
    """
    New-event candidates from the scoreboard. Per game, only the newest
    goal is a candidate: two goals inside one minute is rare, and an alert
    for a goal that's already been followed by another one is stale. The
    older ones are still claimed, so they're never sent late.
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


def record_results(cur, results):
    """
    Final scores into game_results, so pick'em picks are scored minutes
    after a game ends (the nightly grading is the fallback). Best effort:
    a missing table (pick'em not set up) mustn't stop the alerts.
    """
    if not results:
        return
    try:
        cur.execute("SAVEPOINT results")
        for r in results:
            cur.execute(
                """
                INSERT INTO game_results (game_id, home_won, home_score, away_score)
                VALUES (%s, %s, %s, %s) ON CONFLICT (game_id) DO NOTHING
                """,
                (r["game_id"], r["home_won"], r["home_score"], r["away_score"]),
            )
        cur.execute("RELEASE SAVEPOINT results")
    except psycopg2.Error as exc:
        cur.execute("ROLLBACK TO SAVEPOINT results")
        logger.warning(f"Couldn't record game results ({exc.__class__.__name__}); pick'em scoring waits for the nightly grade")


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
        record_results(cur, [e["result"] for e in candidates if e["key"] in fresh and e.get("result")])
        conn.commit()
        for event in (e for e in candidates if e["key"] in fresh):
            statuses = []
            for sub in subscribers(cur, event["teams"], event["kind"]):
                try:
                    status = push.send(sub, event["payload"], ttl=event["ttl"])
                    statuses.append(f"{urlparse(sub['endpoint']).hostname}:{status}")
                    sent += 1 if status and status < 300 else 0
                except push.SubscriptionGone:
                    statuses.append(f"{urlparse(sub['endpoint']).hostname}:gone")
                    cur.execute("DELETE FROM push_subscriptions WHERE endpoint = %s", (sub["endpoint"],))
            # Which push services accepted it (e.g. fcm.googleapis.com:201), for tracing a missed alert.
            logger.info("%s -> %s [%s]", event["key"], event["payload"]["title"], ", ".join(statuses) or "no subscribers")
        cur.execute("DELETE FROM push_events_sent WHERE sent_at < NOW() - INTERVAL '3 days'")
    return sent


def creators(cur):
    """The site owner's devices (push_subscriptions.is_creator), for the morning post reminder."""
    cur.execute("SELECT endpoint, p256dh, auth FROM push_subscriptions WHERE is_creator")
    return [{"endpoint": e, "p256dh": p, "auth": a} for e, p, a in cur.fetchall()]


def creator_reminder(now=None, fetch=None):
    """
    The morning after a game night, once: "Swing of the Night is ready, tap
    to post", to the creator's devices only, opening the site's post kit
    (the card, the post text, Post on X). Called every few minutes in the
    morning; push_events_sent makes it once a day. Returns pushes sent.
    """
    now = now or datetime.now(timezone.utc)
    et = now.astimezone(EASTERN)
    if et.hour not in REMINDER_HOURS:
        return 0
    day = (et.date() - timedelta(days=1)).isoformat()
    key = f"swing-ready:{day}"
    with psycopg2.connect(DATABASE_URL) as conn, conn.cursor() as cur:
        cur.execute("SELECT 1 FROM push_events_sent WHERE event_key = %s", (key,))
        if cur.fetchone():
            return 0
        try:
            swing = (fetch or (lambda d: requests.get(SWING_URL.format(day=d), timeout=30).json()))(day)
        except (requests.RequestException, ValueError) as exc:
            logger.warning("Swing of the Night for %s unavailable (%s); trying again next run", day, exc.__class__.__name__)
            return 0
        if not claim(cur, [key]):
            return 0
        conn.commit()
        if not swing.get("available"):
            return 0  # no games that night: nothing to post
        g = swing["goal"]
        payload = {
            "title": "Swing of the Night is ready",
            "body": f"{g['scorer'] or g['team']} {g['effect']} with {g['when']} · {g['team']} "
                    f"{round(g['before'] * 100)}% → {round(g['after'] * 100)}%. Tap to post it.",
            "url": f"/post-kit?date={day}",
            "tag": f"swing-ready-{day}",
        }
        sent = 0
        for sub in creators(cur):
            try:
                status = push.send(sub, payload, ttl=6 * 3600, urgency="normal")
                sent += 1 if status and status < 300 else 0
            except push.SubscriptionGone:
                cur.execute("DELETE FROM push_subscriptions WHERE endpoint = %s", (sub["endpoint"],))
        logger.info("%s -> %d creator device(s)", key, sent)
        return sent


if __name__ == "__main__":
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logger.info("Sent %d notifications", run())
