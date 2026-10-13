"""
MoneyPuck's playoff odds, logged daily next to ours, so the two models can
be scored head to head when the season is decided.

MoneyPuck (moneypuck.com, free for non-commercial use with credit)
publishes its season simulation as one CSV, updated each morning around
4:30 AM ET. Each row is a team under a scenario for its next game; "ALL"
is the unconditional odds.

Dates line up by information, not by clock: MoneyPuck's update on day D
and our 2 AM run on day D have both seen the games through D-1. Our run
(2 AM) comes before theirs (4:30 AM), so tonight's job picks up their
update from this morning and stores it as this morning's date: the same
as_of_date as our playoff_odds row from the same morning.

Usage:
    python moneypuck_odds.py              # log today's (run by the daily job)
    python moneypuck_odds.py --report     # how the two compare so far
"""

import argparse
import csv
import io
import os
from datetime import date

import psycopg2
import requests
from dotenv import load_dotenv

from logging_config import setup_logging
from seasons import current_season_id

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
logger = setup_logging("moneypuck_odds")

SIMULATIONS_URL = "https://moneypuck.com/moneypuck/simulations/simulations_recent.csv"
UPDATED_URL = "https://moneypuck.com/moneypuck/simulations/update_date.txt"
HEADERS = {"User-Agent": "nhl-dashboard (personal, non-commercial; credits MoneyPuck.com)"}

TABLE_SQL = """
CREATE TABLE IF NOT EXISTS moneypuck_odds (
    season_id               INTEGER NOT NULL,
    as_of_date              DATE NOT NULL,
    team_abbrev             VARCHAR(3) NOT NULL,
    playoff_pct             NUMERIC(6,4) NOT NULL,
    won_cup_pct             NUMERIC(6,4),
    projected_points        NUMERIC(5,1),
    moneypuck_updated_at    TIMESTAMPTZ NOT NULL,
    fetched_at              TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (season_id, as_of_date, team_abbrev)
)
"""


def _get(url):
    response = requests.get(url, headers=HEADERS, timeout=30)
    response.raise_for_status()
    return response.text


def parse_simulations(csv_text):
    """{team: {"playoff_pct", "won_cup_pct", "projected_points"}} from the "ALL" rows."""
    out = {}
    for row in csv.DictReader(io.StringIO(csv_text)):
        if row.get("scenerio") != "ALL":  # sic: MoneyPuck's column name
            continue
        out[row["teamCode"]] = {
            "playoff_pct": float(row["madePlayoffs"]),
            "won_cup_pct": float(row["wonCup"]) if row.get("wonCup") else None,
            "projected_points": float(row["points"]) if row.get("points") else None,
        }
    return out


def parse_updated(text):
    """MoneyPuck's update time ("2026-10-13 04:28:23.55-04:00") -> (timestamp text, its date)."""
    stamp = text.strip()
    return stamp, date.fromisoformat(stamp[:10])


def save(cur, season_id, as_of, updated_at, odds):
    cur.execute(TABLE_SQL)
    for team, o in odds.items():
        cur.execute(
            """
            INSERT INTO moneypuck_odds (season_id, as_of_date, team_abbrev, playoff_pct, won_cup_pct,
                                        projected_points, moneypuck_updated_at, fetched_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (season_id, as_of_date, team_abbrev) DO UPDATE SET
                playoff_pct = EXCLUDED.playoff_pct,
                won_cup_pct = EXCLUDED.won_cup_pct,
                projected_points = EXCLUDED.projected_points,
                moneypuck_updated_at = EXCLUDED.moneypuck_updated_at,
                fetched_at = NOW()
            """,
            (season_id, as_of, team, o["playoff_pct"], o["won_cup_pct"], o["projected_points"], updated_at),
        )


def log_today():
    """
    A MoneyPuck outage only costs one day of comparison, so it logs a
    warning instead of failing the daily job (which would retry every
    step and send a failure alert). Database errors still fail it.
    """
    try:
        updated_at, as_of = parse_updated(_get(UPDATED_URL))
        odds = parse_simulations(_get(SIMULATIONS_URL))
    except (requests.RequestException, ValueError, KeyError) as exc:
        logger.warning(f"MoneyPuck odds unavailable today ({exc}); skipping")
        return
    if len(odds) < 32:
        logger.warning(f"MoneyPuck file has {len(odds)} teams; not saving a partial day")
        return
    season_id = current_season_id(as_of)
    with psycopg2.connect(DATABASE_URL) as conn, conn.cursor() as cur:
        save(cur, season_id, as_of, updated_at, odds)
    logger.info(f"Logged MoneyPuck odds for {len(odds)} teams as of {as_of} (updated {updated_at})")


def brier(pairs):
    return sum((p - a) ** 2 for p, a in pairs) / len(pairs)


def head_to_head(rows, outcomes):
    """
    rows: [(as_of_date, team, ours, theirs)] on dates both models logged.
    outcomes: {team: 1.0 made / 0.0 missed}, empty until the season ends.
    Returns agreement stats now, and Brier scores once outcomes exist.
    """
    result = {
        "days": len({r[0] for r in rows}),
        "mean_abs_diff": round(sum(abs(o - t) for _, _, o, t in rows) / len(rows), 4) if rows else None,
    }
    scored = [(o, t, outcomes[team]) for _, team, o, t in rows if team in outcomes]
    if scored:
        result["brier_ours"] = round(brier([(o, a) for o, _, a in scored]), 4)
        result["brier_moneypuck"] = round(brier([(t, a) for _, t, a in scored]), 4)
    return result


def report(season_id):
    with psycopg2.connect(DATABASE_URL) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT m.as_of_date, m.team_abbrev, o.playoff_pct, m.playoff_pct
            FROM moneypuck_odds m
            JOIN playoff_odds o USING (season_id, as_of_date, team_abbrev)
            WHERE m.season_id = %s ORDER BY m.as_of_date, m.team_abbrev
            """,
            (season_id,),
        )
        rows = [(d, t, float(o), float(m)) for d, t, o, m in cur.fetchall()]
        cur.execute("SELECT team_abbrev, made_playoffs FROM season_final_standings WHERE season_id = %s", (season_id,))
        outcomes = {t: 1.0 if made else 0.0 for t, made in cur.fetchall()}
    if not rows:
        print("No days with both models logged yet.")
        return
    print(head_to_head(rows, outcomes))
    latest = max(r[0] for r in rows)
    print(f"\nBiggest disagreements on {latest} (ours vs MoneyPuck):")
    today = sorted((r for r in rows if r[0] == latest), key=lambda r: -abs(r[2] - r[3]))
    for _, team, ours, theirs in today[:8]:
        print(f"  {team}  {ours:6.1%}  vs  {theirs:6.1%}   ({(ours - theirs) * 100:+.1f})")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", action="store_true")
    parser.add_argument("--season", type=int, default=None)
    args = parser.parse_args()
    if not DATABASE_URL:
        raise SystemExit("DATABASE_URL is not set")
    if args.report:
        report(args.season or current_season_id())
    else:
        log_today()


if __name__ == "__main__":
    main()
