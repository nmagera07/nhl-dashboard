"""
One-time setup for the goal/final notifier as an Azure Function (Flex
Consumption). Run from backend/ with the Azure CLI logged in:

    .venv/bin/python scripts/setup_notifier_function.py
    .venv/bin/python scripts/setup_notifier_function.py --retire-job

Reads DATABASE_URL, the VAPID keys, and ODDS_API_KEY (optional; the
closing-odds snapshot's sportsbook prices) from backend/.env so nothing
secret is typed or printed. Safe to re-run.

1. A storage account (Flex Consumption keeps its code and timer state there).
2. Application Insights on the existing Log Analytics workspace, for logs.
3. The function app: Python 3.12, 512 MB instances, secrets as app settings.
4. Deploys the code. After that, every backend deploy redeploys it.

--retire-job deletes the old nhl-live-notifier Container Apps Job. Run it
once the function's logs show runs ("Sent N notifications"). Until then
both run safely: each alert is claimed in the database before it's sent.
"""

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from dotenv import dotenv_values

sys.path.insert(0, str(Path(__file__).resolve().parent))
import package_notifier  # noqa: E402

RG = "nhl-dashboard-rg"
LOCATION = "westus2"
APP = "puckpulse-live-notifier"
INSIGHTS = "puckpulse-live-notifier"
WORKSPACE = "workspace-nhldashboardrg78I6"
OLD_JOB = "nhl-live-notifier"

os.environ.setdefault("AZURE_EXTENSION_USE_DYNAMIC_INSTALL", "yes_without_prompt")


def az(*args, capture=False):
    result = subprocess.run(["az", *args, "-o", "json" if capture else "none"], capture_output=True, text=True)
    if result.returncode != 0:
        sys.exit(f"az {' '.join(args[:3])} failed:\n{result.stderr.strip()}")
    return json.loads(result.stdout) if capture and result.stdout.strip() else None


def exists(*args):
    return subprocess.run(["az", *args, "-o", "none"], capture_output=True).returncode == 0


if "--retire-job" in sys.argv:
    if exists("containerapp", "job", "show", "--name", OLD_JOB, "--resource-group", RG):
        az("containerapp", "job", "delete", "--name", OLD_JOB, "--resource-group", RG, "--yes")
        print(f"Deleted the {OLD_JOB} Container Apps Job.")
    else:
        print(f"{OLD_JOB} is already gone.")
    sys.exit()

env = dotenv_values(Path(__file__).resolve().parent.parent / ".env")
for name in ("DATABASE_URL", "VAPID_PUBLIC_KEY", "VAPID_PRIVATE_KEY"):
    if not env.get(name):
        sys.exit(f"{name} is missing from backend/.env")

subscription = az("account", "show", capture=True)["id"]
storage = "ppnotifier" + hashlib.sha256(subscription.encode()).hexdigest()[:8]  # globally unique, stable per subscription

print(f"1/4 Storage account {storage}...")
if not exists("storage", "account", "show", "--name", storage, "--resource-group", RG):
    az("storage", "account", "create", "--name", storage, "--resource-group", RG, "--location", LOCATION,
       "--sku", "Standard_LRS", "--kind", "StorageV2", "--https-only", "true",
       "--min-tls-version", "TLS1_2", "--allow-blob-public-access", "false")

print("2/4 Application Insights...")
if not exists("monitor", "app-insights", "component", "show", "--app", INSIGHTS, "--resource-group", RG):
    workspace = az("monitor", "log-analytics", "workspace", "show", "--workspace-name", WORKSPACE,
                   "--resource-group", RG, capture=True)["id"]
    az("monitor", "app-insights", "component", "create", "--app", INSIGHTS, "--resource-group", RG,
       "--location", LOCATION, "--workspace", workspace, "--application-type", "web")

print(f"3/4 Function app {APP}...")
if not exists("functionapp", "show", "--name", APP, "--resource-group", RG):
    az("functionapp", "create", "--name", APP, "--resource-group", RG, "--storage-account", storage,
       "--flexconsumption-location", LOCATION, "--runtime", "python", "--runtime-version", "3.12",
       "--instance-memory", "512", "--app-insights", INSIGHTS)
settings = [f"DATABASE_URL={env['DATABASE_URL']}", f"VAPID_PRIVATE_KEY={env['VAPID_PRIVATE_KEY']}",
            f"VAPID_PUBLIC_KEY={env['VAPID_PUBLIC_KEY']}"]
if env.get("ODDS_API_KEY"):
    settings.append(f"ODDS_API_KEY={env['ODDS_API_KEY']}")
else:
    print("   (no ODDS_API_KEY in .env: closing odds will be Kalshi only)")
az("functionapp", "config", "appsettings", "set", "--name", APP, "--resource-group", RG, "--settings", *settings)

print("4/4 Deploying the code (remote build, a minute or two)...")
with tempfile.TemporaryDirectory() as tmp:
    package = package_notifier.build(Path(tmp) / "notifier.zip")
    az("functionapp", "deployment", "source", "config-zip", "--name", APP, "--resource-group", RG,
       "--src", str(package), "--build-remote", "true")

functions = az("functionapp", "function", "list", "--name", APP, "--resource-group", RG, capture=True) or []
print(f"Done. Functions: {', '.join(f['name'].split('/')[-1] for f in functions) or 'none listed yet'}.")
print("Check the logs after a minute in game hours, then run with --retire-job.")
