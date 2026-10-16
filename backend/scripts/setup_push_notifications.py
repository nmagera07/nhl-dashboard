"""
One-time setup for goal/final push notifications. Run from backend/ with
the Azure CLI logged in:

    .venv/bin/python scripts/setup_push_notifications.py

Reads secrets from backend/.env (DATABASE_URL, VAPID_PUBLIC_KEY,
VAPID_PRIVATE_KEY) so nothing secret is typed or printed. Safe to re-run.

1. Creates push_subscriptions + push_events_sent and lets the API's
   read-only role write push_subscriptions (and nothing else).
2. Gives the API the VAPID *public* key (not a secret).

The notifier itself is an Azure Function now: scripts/setup_notifier_function.py.
"""

import subprocess
import sys
from pathlib import Path

import psycopg2
from dotenv import dotenv_values

RG = "nhl-dashboard-rg"
API_APP = "nhl-dashboard-api"

env = dotenv_values(Path(__file__).resolve().parent.parent / ".env")
for name in ("DATABASE_URL", "VAPID_PUBLIC_KEY", "VAPID_PRIVATE_KEY"):
    if not env.get(name):
        sys.exit(f"{name} is missing from backend/.env")


def az(*args):
    result = subprocess.run(["az", *args, "-o", "none"], capture_output=True, text=True)
    if result.returncode != 0:
        sys.exit(f"az {' '.join(args[:3])} failed:\n{result.stderr.strip()}")


print("1/2 Database tables and grant...")
schema = (Path(__file__).resolve().parent.parent / "schema.sql").read_text()
start = schema.index("CREATE TABLE IF NOT EXISTS push_subscriptions")
with psycopg2.connect(env["DATABASE_URL"]) as conn, conn.cursor() as cur:
    cur.execute(schema[start:])
    cur.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON push_subscriptions TO nhl_api_readonly")

print("2/2 VAPID public key on the API...")
az("containerapp", "update", "--name", API_APP, "--resource-group", RG,
   "--set-env-vars", f"VAPID_PUBLIC_KEY={env['VAPID_PUBLIC_KEY']}")
print("Done. Set up the notifier with scripts/setup_notifier_function.py.")
