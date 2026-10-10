"""
One-time setup for goal/final push notifications. Run from backend/ with
the Azure CLI logged in:

    .venv/bin/python scripts/setup_push_notifications.py

Reads secrets from backend/.env (DATABASE_URL, VAPID_PUBLIC_KEY,
VAPID_PRIVATE_KEY) so nothing secret is typed or printed. Safe to re-run.

1. Creates push_subscriptions + push_events_sent and lets the API's
   read-only role write push_subscriptions (and nothing else).
2. Gives the API the VAPID *public* key (not a secret).
3. Creates the nhl-live-notifier job: every minute during game hours,
   0.25 vCPU / 0.5 GiB, using the API image; the VAPID private key and
   database URL are job secrets.
"""

import subprocess
import sys
from pathlib import Path

import psycopg2
from dotenv import dotenv_values

RG = "nhl-dashboard-rg"
API_APP = "nhl-dashboard-api"
ENVIRONMENT = "nhl-dashboard-api-env"
JOB = "nhl-live-notifier"
CRON = "* 0-7,16-23 * * *"  # every minute, noon-4am ET (UTC hours 16-23 and 0-7)

env = dotenv_values(Path(__file__).resolve().parent.parent / ".env")
for name in ("DATABASE_URL", "VAPID_PUBLIC_KEY", "VAPID_PRIVATE_KEY"):
    if not env.get(name):
        sys.exit(f"{name} is missing from backend/.env")


def az(*args):
    result = subprocess.run(["az", *args, "-o", "none"], capture_output=True, text=True)
    if result.returncode != 0:
        sys.exit(f"az {' '.join(args[:3])} failed:\n{result.stderr.strip()}")


print("1/3 Database tables and grant...")
schema = (Path(__file__).resolve().parent.parent / "schema.sql").read_text()
start = schema.index("CREATE TABLE IF NOT EXISTS push_subscriptions")
with psycopg2.connect(env["DATABASE_URL"]) as conn, conn.cursor() as cur:
    cur.execute(schema[start:])
    cur.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON push_subscriptions TO nhl_api_readonly")

print("2/3 VAPID public key on the API...")
az("containerapp", "update", "--name", API_APP, "--resource-group", RG,
   "--set-env-vars", f"VAPID_PUBLIC_KEY={env['VAPID_PUBLIC_KEY']}")

print("3/3 Notifier job...")
image = subprocess.run(
    ["az", "containerapp", "show", "--name", API_APP, "--resource-group", RG,
     "--query", "properties.template.containers[0].image", "-o", "tsv"],
    capture_output=True, text=True, check=True,
).stdout.strip()
exists = subprocess.run(["az", "containerapp", "job", "show", "--name", JOB, "--resource-group", RG, "-o", "none"],
                        capture_output=True).returncode == 0
secrets = [f"database-url={env['DATABASE_URL']}", f"vapid-private-key={env['VAPID_PRIVATE_KEY']}"]
env_vars = ["DATABASE_URL=secretref:database-url", "VAPID_PRIVATE_KEY=secretref:vapid-private-key",
            f"VAPID_PUBLIC_KEY={env['VAPID_PUBLIC_KEY']}"]
if exists:
    az("containerapp", "job", "secret", "set", "--name", JOB, "--resource-group", RG, "--secrets", *secrets)
    az("containerapp", "job", "update", "--name", JOB, "--resource-group", RG, "--image", image,
       "--cron-expression", CRON, "--set-env-vars", *env_vars)
else:
    az("containerapp", "job", "create", "--name", JOB, "--resource-group", RG, "--environment", ENVIRONMENT,
       "--trigger-type", "Schedule", "--cron-expression", CRON,
       "--replica-timeout", "120", "--replica-retry-limit", "0", "--parallelism", "1", "--replica-completion-count", "1",
       "--image", image, "--cpu", "0.25", "--memory", "0.5Gi",
       "--command", "python", "--args", "notify_live_games.py",
       "--secrets", *secrets, "--env-vars", *env_vars)
print(f"Done. {JOB} runs every minute during game hours with {image.rsplit(':', 1)[-1][:7]}.")
