"""
Entry point for the daily Azure Container Apps Job (nhl-standings-ingest).

Runs each ingestion script in its own process, in order:
  1. ingest_standings.py      -- standings snapshot (also sets the current
                                 season that player stats are scoped to)
  2. ingest_xg.py             -- PuckPulse xG for each finished game (NHL
                                 play-by-play), which the odds step uses,
                                 plus per-game goalie and 5-on-5 rows
  3. ingest_advanced_stats.py -- 5-on-5 xG/Corsi/PDO and goalie GSAx for the
                                 Standings page and player cards (step 2's
                                 rows plus the NHL stats API)
  4. simulate_playoff_odds.py -- Monte Carlo playoff odds (v2) from today's
                                 standings
  5. game_predictions.py      -- logs today's game predictions (from the
                                 ratings step 3 just saved) and grades
                                 earlier ones: the model's track record
  5b. goalie_starts.py        -- projected starting goalies for today's games
                                 (from the starters ingest_xg.py recorded)
  6. market_odds.py           -- Kalshi's odds for today's games, logged next
                                 to our predictions (graded later, both ways)
  7. daily_digest.py          -- the morning digest: facts gathered here,
                                 written up by NHL Intelligence (reads the
                                 odds and ratings step 3 just saved)
  8. ingest_player_stats.py   -- rosters + season stats, including marking
                                 cut/released players off-roster
  9. team_lines.py            -- each team's lines from its last game (NHL
                                 shift charts), after rosters
  10. moneypuck_odds.py        -- MoneyPuck's playoff odds, logged next to
                                 ours for a head-to-head score

A failure in one script doesn't stop the next, since e.g. a playoff-odds
problem shouldn't also leave rosters stale. The process exits non-zero if any
script failed, so the job execution shows as Failed and the job's retry
kicks in (re-running is safe, everything is upserts).

Before giving up, the failed scripts get one more try at the end of the
run. Most failures are the NHL API timing out for a few minutes (11-04:
predictions, goalie starts, and odds all failed at 1 AM ET), and by the end
of the run (~25 min) it's usually back. The job's own retry restarts the
whole run instead, which then hits the 30-minute replica timeout before
reaching the steps that failed. A retry is skipped once the run is past
RETRY_UNTIL_SECONDS, so it can't push the run into that timeout.

Heartbeat: if HEALTHCHECK_URL is set (a healthchecks.io ping URL), the
run pings /start when it begins, the bare URL on success, and /fail on
failure. healthchecks.io emails if a run fails, takes too long, or never
happens at all -- the last one is the case log-based alerts can't see.
"""

import os
import subprocess
import sys
import time

import requests

from logging_config import setup_logging

logger = setup_logging("run_daily_ingest")

HEALTHCHECK_URL = (os.environ.get("HEALTHCHECK_URL") or "").rstrip("/")

# The job's replica timeout is 1800s; the scripts that fail on an NHL API
# hiccup take seconds to a minute or two, so leave ~4 minutes of room.
RETRY_UNTIL_SECONDS = 26 * 60

SCRIPTS = [
    "ingest_standings.py",
    "ingest_xg.py",
    "ingest_advanced_stats.py",
    "war.py",
    "simulate_playoff_odds.py",
    "game_predictions.py",
    "goalie_starts.py",
    "market_odds.py",
    "daily_digest.py",
    "ingest_player_stats.py",
    "team_lines.py",
    "moneypuck_odds.py",
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


def retry_failed(failed, started, runner=subprocess.run, clock=time.monotonic):
    """One more try for each failed script, in run order, while there's time. Returns what still failed."""
    still_failed = []
    for script in failed:
        if clock() - started > RETRY_UNTIL_SECONDS:
            logger.warning(f"No time left to retry {script}")
            still_failed.append(script)
            continue
        logger.info(f"Retrying {script}")
        if runner([sys.executable, script]).returncode == 0:
            logger.info(f"Finished {script} on retry")
        else:
            logger.error(f"{script} failed again")
            still_failed.append(script)
    return still_failed


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
    started = time.monotonic()
    failed = run_all()
    if failed:
        failed = retry_failed(failed, started)
    if failed:
        message = f"Daily ingest finished with failures: {', '.join(failed)}"
        logger.error(message)
        ping("/fail", body=message)
        sys.exit(1)
    logger.info("Daily ingest finished successfully")
    ping()


if __name__ == "__main__":
    main()
