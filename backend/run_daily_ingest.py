"""
Entry point for the daily Azure Container Apps Job (nhl-standings-ingest).

Runs each ingestion script in its own process, in order:
  1. ingest_standings.py    -- standings snapshot (also sets the current
                               season that player stats are scoped to)
  2. ingest_player_stats.py -- rosters + season stats, including marking
                               cut/released players off-roster

simulate_playoff_odds.py and ingest_advanced_stats.py are still run by
hand while they get cleaned up; add them here (playoff odds right after
standings, since it reads them) once they're ready to run unattended.

A failure in one script doesn't stop the next, since a standings outage
shouldn't also leave rosters stale. The process exits non-zero if any
script failed, so the job execution shows as Failed and the job's retry
kicks in (re-running is safe, everything is upserts).
"""

import subprocess
import sys

from logging_config import setup_logging

logger = setup_logging("run_daily_ingest")

SCRIPTS = [
    "ingest_standings.py",
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


def main():
    failed = run_all()
    if failed:
        logger.error(f"Daily ingest finished with failures: {', '.join(failed)}")
        sys.exit(1)
    logger.info("Daily ingest finished successfully")


if __name__ == "__main__":
    main()
