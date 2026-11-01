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
VALUE_URL = "https://nhl-dashboard-api.bravecoast-a5240643.westus2.azurecontainerapps.io/value-of-the-night?date={day}"
EASTERN = ZoneInfo("America/New_York")
REMINDER_HOURS = range(10, 14)  # ET: the morning after, once the nightly run has finished
RECENT = timedelta(hours=6)  # ignore games that started longer ago (yesterday's finals linger in the feed)
GOAL_STATES = {"LIVE", "CRIT", "FINAL"}  # FINAL too: an overtime winner can arrive with the final whistle
FINAL_STATES = {"FINAL", "OFF"}
STRENGTH = {"pp": "power play", "sh": "shorthanded", "en": "empty net"}
# Goals per game that can alert in one run. Normally a run finds one new
# goal; the NHL feed sometimes posts two at once (a late or reviewed goal),
# and both should alert. Past this it's catching up after an outage: the
# newest few still alert, older ones are claimed quietly.
MAX_GOAL_ALERTS_PER_RUN = 3
START_WINDOW_SECONDS = 5 * 60  # puck drop alerts only in the first 5 minutes of the 1st


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
    # Keyed by the score it made and its period, not its clock time: the NHL
    # corrects a goal's time a few seconds after posting it (17:49 -> 17:50),
    # and a time-based key sent the corrected goal again as a new one. The
    # period is there for overturned goals: MTL's 3-2 in the 1st was taken
    # back, and the real 3-2 in the 2nd went unsent as "already sent"
    # (2026-10-31). The feed has no goal ids to key on.
    score = f"{goal.get('awayScore')}-{goal.get('homeScore')}"
    period = (goal.get("periodDescriptor") or {}).get("number", goal.get("period"))
    return {
        "key": f"goal:{game['id']}:{goal.get('teamAbbrev')}:p{period}:{score}",
        "kind": "goals",
        "scorer": goal.get("teamAbbrev"),  # a goal for a subscriber who follows this team, against one who doesn't
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
            "tag": f"goal-{game['id']}-p{period}-{score}",
        },
    }


def start_event(game):
    """'🏒 Puck drop: FLA @ WPG'. Stale after 15 minutes."""
    away, home = game["awayTeam"]["abbrev"], game["homeTeam"]["abbrev"]
    return {
        "key": f"start:{game['id']}",
        "kind": "starts",
        "ttl": 15 * 60,
        "teams": [away, home],
        "payload": {
            "title": f"🏒 Puck drop: {away} @ {home}",
            "body": "It's underway. Tap to follow along live.",
            "url": f"/games/{game['id']}",
            "tag": f"start-{game['id']}",
        },
    }


def _just_started(game):
    """
    In the first minutes of the 1st period, so a restart mid-game doesn't
    announce a start an hour late. Not in the first intermission: the feed
    still says period 1 there, with the intermission's 18:00 countdown on
    the clock, which looked like the opening minutes (2026-10-26, TOR@CGY).
    """
    period = (game.get("periodDescriptor") or {}).get("number") or game.get("period")
    clock = game.get("clock") or {}
    remaining = clock.get("secondsRemaining")
    return (period == 1 and not clock.get("inIntermission") and remaining is not None
            and remaining >= 20 * 60 - START_WINDOW_SECONDS)


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
    New-event candidates from the scoreboard: puck drop, goals, finals.
    Per game, the newest MAX_GOAL_ALERTS_PER_RUN goals are candidates (the
    claim drops ones already sent); older ones are claimed quietly, so an
    outage's backlog is never sent late. Only the newest goal used to be a
    candidate, so a second goal posted in the same minute never alerted.
    """
    candidates, claim_only = [], []
    for game in games:
        start = game.get("startTimeUTC")
        if not start or now - datetime.fromisoformat(start.replace("Z", "+00:00")) > RECENT:
            continue
        state = game.get("gameState")
        if state in ("LIVE", "CRIT") and _just_started(game):
            candidates.append(start_event(game))
        if state in GOAL_STATES and game.get("goals"):
            goals = [goal_event(game, g) for g in game["goals"]]
            candidates.extend(goals[-MAX_GOAL_ALERTS_PER_RUN:])
            claim_only.extend(goals[:-MAX_GOAL_ALERTS_PER_RUN])
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


def deliver(cur, key, sub, payload, ttl, urgency="high"):
    """
    Send one push and record what the push service said in push_deliveries
    (accepted, refused, gone, or no response), so a missed alert can be
    traced without the function's logs. A gone subscription is deleted.
    Returns True if the push service accepted it.
    """
    payload = {**payload, "key": key}  # the service worker sends it back as a receipt (POST /push/receipts)
    try:
        status = push.send(sub, payload, ttl=ttl, urgency=urgency)
        outcome = "accepted" if status and status < 300 else "refused" if status else "no response"
    except push.SubscriptionGone:
        status, outcome = None, "gone"
        cur.execute("DELETE FROM push_subscriptions WHERE endpoint = %s", (sub["endpoint"],))
    try:
        cur.execute("SAVEPOINT delivery")
        cur.execute(
            "INSERT INTO push_deliveries (event_key, device, status, outcome, ttl) VALUES (%s, %s, %s, %s, %s)",
            (key, device_label(sub["endpoint"]), status, outcome, ttl),
        )
        cur.execute("RELEASE SAVEPOINT delivery")
    except psycopg2.Error:  # no table yet: the alert matters more than the log
        cur.execute("ROLLBACK TO SAVEPOINT delivery")
    return outcome == "accepted"


device_label = push.device_label


def subscribers(cur, teams, kind, scorer=None):
    """
    Devices following either team that want this kind of alert (their
    alert settings). A goal is "for" a device that follows the scoring
    team, "against" one that only follows the opponent.
    """
    if kind == "goals":
        cur.execute(
            """
            SELECT endpoint, p256dh, auth FROM push_subscriptions
            WHERE teams && %s::text[]
              AND ((notify_goals AND %s = ANY(teams)) OR (notify_goals_against AND NOT %s = ANY(teams)))
            """,
            (teams, scorer, scorer),
        )
    else:
        column = {"starts": "notify_starts", "finals": "notify_finals"}[kind]
        cur.execute(
            f"SELECT endpoint, p256dh, auth FROM push_subscriptions WHERE teams && %s::text[] AND {column}",
            (teams,),
        )
    return [{"endpoint": e, "p256dh": p, "auth": a} for e, p, a in cur.fetchall()]


# Event keys this instance has claimed (or found claimed). The function app
# keeps its instance warm across the every-minute runs, so a run with
# nothing new skips the database. Neon bills while its compute is awake and
# naps after 5 idle minutes; claiming every goal again each minute kept it
# awake for 6 hours after every puck drop. A new instance starts empty and
# its first claim asks the database, so nothing is sent twice.
_claimed = set()
CLAIMED_MAX = 5000


def run(now=None, fetch=None):
    now = now or datetime.now(timezone.utc)
    games = (fetch or (lambda: requests.get(SCORE_URL, timeout=15).json()))().get("games", [])
    candidates, claim_only = events_for(games, now)
    keys = {e["key"] for e in candidates + claim_only}
    if not candidates or keys <= _claimed:
        return 0

    sent = 0
    with psycopg2.connect(DATABASE_URL) as conn, conn.cursor() as cur:
        claim(cur, [e["key"] for e in claim_only])
        fresh = claim(cur, [e["key"] for e in candidates])
        conn.commit()  # claimed before sending: a crash mid-send can't cause a duplicate later
        if len(_claimed) > CLAIMED_MAX:
            _claimed.clear()
        _claimed.update(keys)
        record_results(cur, [e["result"] for e in candidates if e["key"] in fresh and e.get("result")])
        conn.commit()
        for event in (e for e in candidates if e["key"] in fresh):
            subs = subscribers(cur, event["teams"], event["kind"], event.get("scorer"))
            accepted = sum(deliver(cur, event["key"], sub, event["payload"], event["ttl"]) for sub in subs)
            sent += accepted
            logger.info("%s -> %s [%d of %d accepted]", event["key"], event["payload"]["title"], accepted, len(subs))
        cur.execute("DELETE FROM push_events_sent WHERE sent_at < NOW() - INTERVAL '3 days'")
        cur.execute("SAVEPOINT prune")
        try:
            cur.execute("DELETE FROM push_deliveries WHERE sent_at < NOW() - INTERVAL '14 days'")
            cur.execute("RELEASE SAVEPOINT prune")
        except psycopg2.Error:
            cur.execute("ROLLBACK TO SAVEPOINT prune")
    return sent


def post_draft(cur, day):
    """The drafting agent's X post about `day` (post_drafts.py), or None: not drafted, or no table yet."""
    try:
        cur.execute("SAVEPOINT draft")
        cur.execute("SELECT x_text FROM post_drafts WHERE day = %s", (day,))
        row = cur.fetchone()
        cur.execute("RELEASE SAVEPOINT draft")
    except psycopg2.Error:
        cur.execute("ROLLBACK TO SAVEPOINT draft")
        return None
    return row[0] if row else None


def creators(cur):
    """The site owner's devices (push_subscriptions.is_creator), for the morning post reminder."""
    cur.execute("SELECT endpoint, p256dh, auth FROM push_subscriptions WHERE is_creator")
    return [{"endpoint": e, "p256dh": p, "auth": a} for e, p, a in cur.fetchall()]


def precompute_swing(now=None, get=None):
    """
    Ask the API for last night's Swing of the Night, so it's built (5-11 s)
    and saved once every game is final, before anyone visits. Hourly in the
    early morning; once saved, each later ask is a quick read. Returns
    whether the API answered.
    """
    day = ((now or datetime.now(timezone.utc)).astimezone(EASTERN).date() - timedelta(days=1)).isoformat()
    try:
        (get or requests.get)(SWING_URL.format(day=day), timeout=60).raise_for_status()
    except requests.RequestException as exc:
        logger.warning("Swing of the Night precompute for %s failed (%s)", day, exc.__class__.__name__)
        return False
    return True


def creator_reminder(now=None, fetch=None):
    """
    The morning after a game night, once: "Today's post is ready" with the
    drafting agent's post (post_drafts.py), or "Swing of the Night is
    ready" if nothing was drafted, to the creator's devices only, opening
    the site's post kit (the card, the post text, Post on X). Called every few minutes in the
    morning; push_events_sent makes it once a day. Returns pushes sent.
    """
    now = now or datetime.now(timezone.utc)
    et = now.astimezone(EASTERN)
    if et.hour not in REMINDER_HOURS:
        return 0
    day = (et.date() - timedelta(days=1)).isoformat()
    key = f"swing-ready:{day}"
    if key in _claimed:
        return 0  # done this morning: no need to wake the database to ask again
    with psycopg2.connect(DATABASE_URL) as conn, conn.cursor() as cur:
        cur.execute("SELECT 1 FROM push_events_sent WHERE event_key = %s", (key,))
        if cur.fetchone():
            _claimed.add(key)
            return 0
        draft = post_draft(cur, day)
        if draft:
            if not claim(cur, [key]):
                return 0
            conn.commit()
            _claimed.add(key)
            payload = {"title": "Today's post is ready", "body": f"{draft} Tap to review it.", "url": f"/post-kit?date={day}",
                       "tag": f"swing-ready-{day}"}
            sent = sum(deliver(cur, key, sub, payload, 6 * 3600) for sub in creators(cur))
            logger.info("%s (drafted post) -> %d creator device(s)", key, sent)
            return sent
        try:
            swing = (fetch or (lambda d: requests.get(SWING_URL.format(day=d), timeout=30).json()))(day)
        except (requests.RequestException, ValueError) as exc:
            logger.warning("Swing of the Night for %s unavailable (%s); trying again next run", day, exc.__class__.__name__)
            return 0
        if not claim(cur, [key]):
            return 0
        conn.commit()
        _claimed.add(key)
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
        # "high": at "normal" the first one sat unshown in Android's batching.
        sent = sum(deliver(cur, key, sub, payload, 6 * 3600) for sub in creators(cur))
        logger.info("%s -> %d creator device(s)", key, sent)
        return sent


def _value_bet(p):
    """'MTL +142 to win' or 'PIT +1.5 at −175'."""
    team = p["home"] if p["side"] == "home" else p["away"]
    price = f"+{p['price']}" if p["price"] > 0 else f"−{abs(p['price'])}"
    if p["market"] == "puck_line":
        return f"{team} {p['line']:+g} at {price}".replace("-", "−")
    return f"{team} {price} to win"


def value_alert(now=None, fetch=None):
    """
    "💰 Value of the night" to devices that turned it on (notify_value),
    once a day, on nights the pick clears the value bar (value_pick.py;
    the closest-to-value nights stay quiet). The pick comes from the API,
    so a night without one never wakes the database. Called once around
    noon ET, hours before the first puck drop. Returns pushes sent.
    """
    day = (now or datetime.now(timezone.utc)).astimezone(EASTERN).date().isoformat()
    key = f"value:{day}"
    if key in _claimed:
        return 0
    try:
        data = (fetch or (lambda d: requests.get(VALUE_URL.format(day=d), timeout=30).json()))(day)
    except (requests.RequestException, ValueError) as exc:
        logger.warning("Value of the night for %s unavailable (%s)", day, exc.__class__.__name__)
        return 0
    p = data.get("pick") if data.get("available") else None
    if not p or not p.get("value"):
        _claimed.add(key)
        return 0
    with psycopg2.connect(DATABASE_URL) as conn, conn.cursor() as cur:
        if not claim(cur, [key]):
            _claimed.add(key)
            return 0
        conn.commit()
        _claimed.add(key)
        ours, books = round(p["ours"] * 100), round(p["market_prob"] * 100)
        ev = f"{'+' if p['ev'] >= 0 else '−'}{abs(p['ev'] * 100):.1f}%"
        payload = {
            "title": f"💰 Value of the night: {_value_bet(p)}",
            "body": f"{p['away']} @ {p['home']} · fair chance {ours}% vs. the books' {books}%, expected return {ev}"
                    f"{' at ' + p['book'] if p.get('book') else ''}. Morning line: check your price. 21+",
            "url": "/bets",
            "tag": f"value-{day}",
        }
        cur.execute("SELECT endpoint, p256dh, auth FROM push_subscriptions WHERE notify_value")
        subs = [{"endpoint": e, "p256dh": pk, "auth": a} for e, pk, a in cur.fetchall()]
        sent = sum(deliver(cur, key, sub, payload, 6 * 3600) for sub in subs)
        logger.info("%s -> %s [%d of %d accepted]", key, payload["title"], sent, len(subs))
        return sent


if __name__ == "__main__":
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logger.info("Sent %d notifications", run())
