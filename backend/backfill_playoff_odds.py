"""
Backfill weekly playoff odds for a past season, so the playoff race chart
has a full season to show (the daily job only adds today's odds).

Uses the production model exactly as it would have run on each date: the
standings as of that date, last season's xG as the prior, and this season's
xG *up to that date* from MoneyPuck's game-by-game team file (no peeking at
later games). The file is free for non-commercial use with credit:
https://moneypuck.com/data.htm ("All Teams" game-by-game CSV).

Usage:
    python backfill_playoff_odds.py --season 20252026 --xg-file all_teams.csv
"""

import argparse
import time
from collections import defaultdict
from datetime import date, timedelta

import simulate_playoff_odds as sim
import psycopg2
from backtest_playoff_odds import load_xg
from logging_config import setup_logging

logger = setup_logging("backfill_playoff_odds")


def xgd_as_of(season_games, as_of):
    """{team: (xG for - xG against, games played)} over games on or before as_of."""
    totals, gp = defaultdict(float), defaultdict(int)
    for d, team, xgf, xga, *_ in season_games:
        if d <= as_of:
            totals[team] += xgf - xga
            gp[team] += 1
    return {t: (totals[t], gp[t]) for t in totals}


def backfill_dates(games, every_days):
    """Weekly dates from a week after opening night through the final regular-season day."""
    played = sorted(g["date"] for g in games)
    first, last = date.fromisoformat(played[0]), date.fromisoformat(played[-1])
    dates, d = [], first + timedelta(days=every_days)
    while d < last:
        dates.append(d)
        d += timedelta(days=every_days)
    return dates + [last]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--xg-file", required=True, help="MoneyPuck game-by-game all_teams.csv")
    parser.add_argument("--every-days", type=int, default=7)
    parser.add_argument("--trials", type=int, default=sim.DEFAULT_TRIALS)
    parser.add_argument("--no-save", action="store_true")
    parser.add_argument("--replace", action="store_true",
                        help="Delete the season's existing odds first, so stray dates from older runs don't linger")
    args = parser.parse_args()

    start = args.season // 10000
    xg = load_xg(args.xg_file)
    if not xg.get(start) or not xg.get(start - 1):
        raise SystemExit(f"{args.xg_file} has no xG for {start} and {start - 1}")
    previous = xgd_as_of(xg[start - 1], "9999-12-31")

    teams = list(sim.fetch_standings_as_of(f"{start}-12-01"))
    games = sim.fetch_season_games(teams, args.season)
    if args.replace and not args.no_save:
        with psycopg2.connect(sim.DATABASE_URL) as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM playoff_odds WHERE season_id = %s", (args.season,))
            logger.info(f"Deleted {cur.rowcount} existing odds rows for {args.season}")

    for as_of in backfill_dates(games, args.every_days):
        standings = sim.fetch_standings_as_of(str(as_of))
        ratings = sim.xg_model_ratings(
            standings, args.season,
            fetch=lambda year: xgd_as_of(xg[start], str(as_of)) if year == start else previous,
        )
        if ratings is None:
            raise SystemExit(f"No xG ratings for {as_of}")
        _, remaining = sim.split_games(games, as_of)
        odds = sim.simulate(standings, remaining, args.trials, ratings)
        if not args.no_save:
            sim.save_odds(odds, args.season, as_of, args.trials)
        leader = max(odds, key=odds.get)
        logger.info(f"{as_of}: {len(remaining)} games left, {leader} {odds[leader]:.0%}")
        time.sleep(1)  # be polite to the NHL API


if __name__ == "__main__":
    main()
