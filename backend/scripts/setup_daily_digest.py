"""
One-time setup for the morning digest. Run from backend/ with the Azure CLI
logged in (after the release that adds daily_digest.py):

    .venv/bin/python scripts/setup_daily_digest.py

1. Creates the daily_digest table; the API's read-only role can read it.
2. Generates a shared DIGEST_TOKEN (saved to backend/.env, never printed) so
   only the daily job can ask NHL Intelligence to write a digest.
3. Gives it to NHL Intelligence (secret + env var) and to the daily job
   (secret + env var, with INTELLIGENCE_URL). Safe to re-run: an existing
   token in .env is reused.
"""

import secrets
import subprocess
import sys
from pathlib import Path

import psycopg2
from dotenv import dotenv_values

RG = "nhl-dashboard-rg"
INTELLIGENCE_APP = "nhl-intelligence"
JOB = "nhl-standings-ingest"
INTELLIGENCE_URL = "https://nhl-intelligence.bravecoast-a5240643.westus2.azurecontainerapps.io"

ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
env = dotenv_values(ENV_FILE)
if not env.get("DATABASE_URL"):
    sys.exit("DATABASE_URL is missing from backend/.env")


def az(*args):
    result = subprocess.run(["az", *args, "-o", "none"], capture_output=True, text=True)
    if result.returncode != 0:
        sys.exit(f"az {' '.join(args[:3])} failed:\n{result.stderr.strip()}")


print("1/3 Database table and grant...")
schema = (Path(__file__).resolve().parent.parent / "schema.sql").read_text()
start = schema.index("CREATE TABLE IF NOT EXISTS daily_digest")
end = schema.index(");", start) + 2
with psycopg2.connect(env["DATABASE_URL"]) as conn, conn.cursor() as cur:
    cur.execute(schema[start:end])
    cur.execute("GRANT SELECT ON daily_digest TO nhl_api_readonly")

print("2/3 Shared digest token...")
token = env.get("DIGEST_TOKEN")
if not token:
    token = secrets.token_urlsafe(32)
    with open(ENV_FILE, "a") as f:
        f.write(f"\n# Shared secret: the daily job -> NHL Intelligence /digest/write\nDIGEST_TOKEN={token}\n")

print("3/3 NHL Intelligence and the daily job...")
az("containerapp", "secret", "set", "--name", INTELLIGENCE_APP, "--resource-group", RG, "--secrets", f"digest-token={token}")
az("containerapp", "update", "--name", INTELLIGENCE_APP, "--resource-group", RG,
   "--set-env-vars", "DIGEST_TOKEN=secretref:digest-token")
az("containerapp", "job", "secret", "set", "--name", JOB, "--resource-group", RG, "--secrets", f"digest-token={token}")
az("containerapp", "job", "update", "--name", JOB, "--resource-group", RG,
   "--set-env-vars", "DIGEST_TOKEN=secretref:digest-token", f"INTELLIGENCE_URL={INTELLIGENCE_URL}")
print("Done. The next daily run (2 AM ET) writes the first digest.")
