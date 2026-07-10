"""
Advanced Stats (Corsi/Fenwick) Ingestion Script

Computes 5-on-5 Corsi and Fenwick for/against per player ourselves, from the
NHL API's official play-by-play and shift-chart endpoints. We're not using
MoneyPuck or Natural Stat Trick here -- both actively block automated access
(MoneyPuck's Cloudflare bot check demands a paid data license for scraping;
Natural Stat Trick's robots.txt explicitly disallows Claude/GPT/etc bots
outright). This recomputes the same underlying stat from public, unrestricted
NHL data instead.

How it works, per game:
  1. Pull play-by-play -- gives every shot attempt (goal/shot/miss/block)
     with a timestamp, the shooting team, and a situationCode.
  2. Pull the shift chart -- gives every player's on-ice intervals per period.
  3. For each shot attempt at 5-on-5 (situationCode "1551": both goalies in,
     5 skaters a side -- see README note below), find every player whose
     shift interval covers that moment. Credit the shooter's teammates with
     a Corsi-For (and Fenwick-For unless the shot was blocked), and the
     other team's on-ice players with a Corsi/Fenwick-Against.

situationCode isn't documented by the NHL, so "1551" was verified empirically
against a sample game: it's the only code where the two middle digits match
(equal skaters both sides) and both outer digits are 1 (both goalies in net),
consistently occurring during plain 5v5 play and never during PP/SH/OT/EN
sequences observed in that sample.

Setup:
    pip install requests psycopg2-binary python-dotenv

Environment variables expected (put these in a .env file):
    DATABASE_URL=postgresql://user:password@host:port/dbname

Usage:
    python ingest_advanced_stats.py --team PIT   # validate against one team
    python ingest_advanced_stats.py              # full league backfill
"""

import argparse
import os
import time

import psycopg2
import requests
from dotenv import load_dotenv

from logging_config import setup_logging

load_dotenv()

SCHEDULE_URL = "https://api-web.nhle.com/v1/club-schedule-season/{team}/{season}"
PLAY_BY_PLAY_URL = "https://api-web.nhle.com/v1/gamecenter/{game_id}/play-by-play"
SHIFT_CHART_URL = "https://api.nhle.com/stats/rest/en/shiftcharts?cayenneExp=gameId={game_id}"
DATABASE_URL = os.environ["DATABASE_URL"]
DEFAULT_SEASON = 20252026

logger = setup_logging("ingest_advanced_stats")

SHOT_ATTEMPT_TYPES = {"missed-shot", "shot-on-goal", "goal", "blocked-shot"}
EVEN_STRENGTH_5V5 = "1551"
# A recently-finished game shows "FINAL"; once the season wraps up it flips
# to "OFF" -- both mean the game is complete and safe to process.
COMPLETED_GAME_STATES = {"FINAL", "OFF"}
REQUEST_DELAY_SECONDS = 0.2
CHECKPOINT_EVERY = 50  # games


def time_to_seconds(mmss):
    minutes, seconds = mmss.split(":")
    return int(minutes) * 60 + int(seconds)


def fetch_team_game_ids(team_abbrev, season_id):
    url = SCHEDULE_URL.format(team=team_abbrev, season=season_id)
    response = requests.get(url, timeout=15)
    response.raise_for_status()
    games = response.json()["games"]
    return [g["id"] for g in games if g["gameType"] == 2 and g["gameState"] in COMPLETED_GAME_STATES]


def fetch_play_by_play(game_id):
    url = PLAY_BY_PLAY_URL.format(game_id=game_id)
    response = requests.get(url, timeout=20)
    response.raise_for_status()
    return response.json()


def fetch_shifts(game_id):
    url = SHIFT_CHART_URL.format(game_id=game_id)
    response = requests.get(url, timeout=20)
    response.raise_for_status()
    return response.json()["data"]


def build_shifts_by_period(shifts):
    """(period) -> list of (player_id, start_sec, end_sec)."""
    by_period = {}
    for shift in shifts:
        if not shift.get("startTime") or not shift.get("endTime"):
            continue
        try:
            start = time_to_seconds(shift["startTime"])
            end = time_to_seconds(shift["endTime"])
        except (ValueError, AttributeError):
            continue
        by_period.setdefault(shift["period"], []).append((shift["playerId"], start, end))
    return by_period


def process_game(game_id, totals):
    pbp = fetch_play_by_play(game_id)
    time.sleep(REQUEST_DELAY_SECONDS)
    shifts = fetch_shifts(game_id)
    time.sleep(REQUEST_DELAY_SECONDS)

    team_by_player = {r["playerId"]: r["teamId"] for r in pbp.get("rosterSpots", [])}
    by_period = build_shifts_by_period(shifts)

    for play in pbp.get("plays", []):
        if play.get("typeDescKey") not in SHOT_ATTEMPT_TYPES:
            continue
        if play.get("situationCode") != EVEN_STRENGTH_5V5:
            continue
        details = play.get("details", {})
        shooting_team = details.get("eventOwnerTeamId")
        if shooting_team is None:
            continue

        period = play["periodDescriptor"]["number"]
        elapsed = time_to_seconds(play["timeInPeriod"])
        is_fenwick = play["typeDescKey"] != "blocked-shot"

        for player_id, start, end in by_period.get(period, []):
            if not (start <= elapsed < end):
                continue
            player_team = team_by_player.get(player_id)
            if player_team is None:
                continue

            entry = totals.setdefault(
                player_id, {"cf": 0, "ca": 0, "ff": 0, "fa": 0, "games": set()}
            )
            entry["games"].add(game_id)
            if player_team == shooting_team:
                entry["cf"] += 1
                if is_fenwick:
                    entry["ff"] += 1
            else:
                entry["ca"] += 1
                if is_fenwick:
                    entry["fa"] += 1


def fetch_valid_player_ids():
    with psycopg2.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT player_id FROM players")
            return {r[0] for r in cur.fetchall()}


def save_totals(totals, season_id, valid_player_ids):
    with psycopg2.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            for player_id, t in totals.items():
                if player_id not in valid_player_ids:
                    # Traded/sent down/retired since the roster snapshot was
                    # taken -- not shown anywhere in the app, so skip rather
                    # than violate the FK on players.
                    continue
                cf, ca, ff, fa = t["cf"], t["ca"], t["ff"], t["fa"]
                cf_pct = cf / (cf + ca) if (cf + ca) > 0 else None
                ff_pct = ff / (ff + fa) if (ff + fa) > 0 else None
                cur.execute(
                    """
                    INSERT INTO player_advanced_stats (
                        player_id, season_id, corsi_for, corsi_against, corsi_for_pct,
                        fenwick_for, fenwick_against, fenwick_for_pct, games_processed,
                        updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                    ON CONFLICT (season_id, player_id) DO UPDATE SET
                        corsi_for = EXCLUDED.corsi_for,
                        corsi_against = EXCLUDED.corsi_against,
                        corsi_for_pct = EXCLUDED.corsi_for_pct,
                        fenwick_for = EXCLUDED.fenwick_for,
                        fenwick_against = EXCLUDED.fenwick_against,
                        fenwick_for_pct = EXCLUDED.fenwick_for_pct,
                        games_processed = EXCLUDED.games_processed,
                        updated_at = NOW()
                    """,
                    (player_id, season_id, cf, ca, cf_pct, ff, fa, ff_pct, len(t["games"])),
                )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--team", help="Only process one team's games (validation mode)")
    parser.add_argument("--season", type=int, default=DEFAULT_SEASON)
    args = parser.parse_args()

    if args.team:
        team_abbrevs = [args.team.upper()]
    else:
        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT team_abbrev FROM teams ORDER BY team_abbrev")
                team_abbrevs = [r[0] for r in cur.fetchall()]

    game_ids = set()
    for team in team_abbrevs:
        game_ids.update(fetch_team_game_ids(team, args.season))
        time.sleep(REQUEST_DELAY_SECONDS)

    game_ids = sorted(game_ids)
    logger.info(f"Processing {len(game_ids)} games across {len(team_abbrevs)} team(s)...")

    valid_player_ids = fetch_valid_player_ids()

    totals = {}
    for i, game_id in enumerate(game_ids, start=1):
        try:
            process_game(game_id, totals)
        except Exception as e:
            logger.warning(f"  game {game_id} failed: {e}")
            continue

        if i % CHECKPOINT_EVERY == 0 or i == len(game_ids):
            save_totals(totals, args.season, valid_player_ids)
            logger.info(f"[{i}/{len(game_ids)}] checkpoint saved -- {len(totals)} players so far")

    logger.info(f"Done. {len(totals)} players, {len(game_ids)} games processed.")


if __name__ == "__main__":
    main()
