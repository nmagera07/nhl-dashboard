"""
Send a test notification to every device following a team, to check
delivery end to end without waiting for a goal. Run from backend/:

    .venv/bin/python scripts/send_test_push.py PIT

Reads DATABASE_URL and the VAPID keys from backend/.env.
"""

import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import psycopg2  # noqa: E402

import push  # noqa: E402
from notify_live_games import DATABASE_URL  # noqa: E402

team = (sys.argv[1] if len(sys.argv) > 1 else "PIT").upper()
with psycopg2.connect(DATABASE_URL) as conn, conn.cursor() as cur:
    cur.execute("SELECT endpoint, p256dh, auth FROM push_subscriptions WHERE %s = ANY(teams)", (team,))
    subs = [{"endpoint": e, "p256dh": p, "auth": a} for e, p, a in cur.fetchall()]
    if not subs:
        sys.exit(f"No devices follow {team}.")
    for sub in subs:
        host = urlparse(sub["endpoint"]).hostname
        try:
            status = push.send(sub, {
                "title": f"🔔 Test: {team} goal alerts are on",
                "body": "If you can read this, notifications reach this device. Tap to open the app.",
                "url": "/",
                "tag": "test",
            }, ttl=15 * 60)
            print(f"{host}: {status}")
        except push.SubscriptionGone:
            print(f"{host}: gone (the browser unsubscribed); removing")
            cur.execute("DELETE FROM push_subscriptions WHERE endpoint = %s", (sub["endpoint"],))
