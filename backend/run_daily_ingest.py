"""
Entry point for the daily Azure Container Apps Job (nhl-standings-ingest).

Runs each ingestion script in its own process, in order:
  1. ingest_standings.py      -- standings snapshot (also sets the current
                                 season that player stats are scoped to)
  2. simulate_playoff_odds.py -- Monte Carlo playoff odds (v2) from today's
                                 standings
  3. ingest_player_stats.py   -- rosters + season stats, including marking
                                 cut/released players off-roster

ingest_advanced_stats.py is still run by hand while it gets cleaned up.

A failure in one script doesn't stop the next, since e.g. a playoff-odds
problem shouldn't also leave rosters stale. The process exits non-zero if any
script failed, so the job execution shows as Failed and the job's retry
kicks in (re-running is safe, everything is upserts).

Heartbeat: if HEALTHCHECK_URL is set (a healthchecks.io ping URL), the
run pings /start when it begins, the bare URL on success, and /fail on
failure. healthchecks.io emails if a run fails, takes too long, or never
happens at all -- the last one is the case log-based alerts can't see.
"""

import os
import subprocess
import sys

import requests

from logging_config import setup_logging

logger = setup_logging("run_daily_ingest")

HEALTHCHECK_URL = (os.environ.get("HEALTHCHECK_URL") or "").rstrip("/")

SCRIPTS = [
    "ingest_standings.py",
    "simulate_playoff_odds.py",
    "ingest_player_stats.py",
]


def run_all(scripts=SCRIPTS, runner=subprocess.run):
    failed = []
    for script in scripts:
        logger.info(f"Starting {script}")
        result = runner([sys.executable, script])
        if result.returncode == 0:
            logger.info(f"Finished {script}")
        else:
            logger.error(f"{script} exited with code {result.returncode}")
            failed.append(script)
    return failed


def ping(suffix="", body=None, post=None):
    """Best-effort heartbeat. Never lets a monitoring hiccup fail the run."""
    if not HEALTHCHECK_URL:
        return
    try:
        (post or requests.post)(f"{HEALTHCHECK_URL}{suffix}", data=body, timeout=10)
    except requests.RequestException as e:
        logger.warning(f"Healthcheck ping{suffix or ''} failed: {e}")


def main():
    ping("/start")
    failed = run_all()
    if failed:
        message = f"Daily ingest finished with failures: {', '.join(failed)}"
        logger.error(message)
        ping("/fail", body=message)
        sys.exit(1)
    logger.info("Daily ingest finished successfully")
    ping()


if __name__ == "__main__":
    main()
