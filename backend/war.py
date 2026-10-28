"""
WAR: each player's wins above replacement this season.

What a player has been worth so far, not a projection (player_values.py
projects; this adds up what happened).

The daily step stores WAR v2 (war_v2.py: skaters from RAPM, finishing,
special teams and penalties; goalies as below). The rest of this module is
v1, kept for the goalies, the backtests, and the comparison:

  Skaters: this season's Game Score minus a replacement-level player's over
    the same games, times GS_TO_GOALS (team goal differential per point of
    team Game Score; player_values.py --calibrate) = goals above replacement.
  Goalies: goals saved above expected (our xG) plus what a replacement-level
    goalie gives up over the same minutes (GOALIE_REPLACEMENT per 60).
  Goals to wins: GOALS_PER_WIN, the slope of team goal differential on team
    wins, both per game (`--calibrate`, 3 seasons of standings).

Checked by `--backtest`: each team's summed WAR, with constants fit on the
other seasons, against how many games it actually won.

Box-score based, so it's an estimate: line-mates and team quality leak
into the on-ice parts, and defense without the puck is mostly invisible.

Usage:
    python war.py                 # store this season's WAR v2 (the daily ingest step)
    python war.py --calibrate     # refit GOALS_PER_WIN
    python war.py --backtest      # team WAR vs. team wins, held out by season
    python war.py --top 20        # this season's leaders
"""

import argparse
import os
from collections import defaultdict
from datetime import date

import psycopg2
import requests
from dotenv import load_dotenv

import player_values as pv
from logging_config import setup_logging
from seasons import current_season_id

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
logger = setup_logging("war")

# From --calibrate on 2023-24 to 2025-26 standings: team goal differential per win, both per game.
GOALS_PER_WIN = 6.15

CACHE = os.path.expanduser("~/.cache/puckpulse")


def skater_war(skaters, gs_to_goals=pv.GS_TO_GOALS, replacement=pv.REPLACEMENT_GS, goals_per_win=GOALS_PER_WIN):
    """{player_id: {"name", "team", "pos", "gp", "gar", "war"}} from player_values.season_skaters()."""
    out = {}
    for pid, p in skaters.items():
        gar = gs_to_goals * (p["gs"] - replacement[pv.position_group(p["pos"])] * p["gp"])
        out[pid] = {"name": p["name"], "team": p["team"], "pos": p["pos"], "gp": p["gp"],
                    "gar": round(gar, 2), "war": round(gar / goals_per_win, 2)}
    return out


def goalie_war(goalies, replacement=pv.GOALIE_REPLACEMENT, goals_per_win=GOALS_PER_WIN):
    """skater_war()'s shape for goalies, from player_values.season_goalies() / our_season_goalies()."""
    out = {}
    for pid, g in goalies.items():
        gar = g["gsax"] - replacement * g["games"]  # replacement is negative: a fringe goalie gives up extra goals
        out[pid] = {"name": g["name"], "team": g["team"], "pos": "G", "gp": g["gp"],
                    "gar": round(gar, 2), "war": round(gar / goals_per_win, 2)}
    return out


# --- the daily step ----------------------------------------------------------------

TABLE_SQL = """
CREATE TABLE IF NOT EXISTS player_war (
    season_id       INTEGER NOT NULL,
    player_id       INTEGER NOT NULL,
    name            VARCHAR(64),
    team_abbrev     VARCHAR(3),
    position_group  CHAR(1) NOT NULL,   -- F, D, or G: WAR is ranked within these
    games_played    SMALLINT NOT NULL,
    gar             NUMERIC(6,2) NOT NULL,
    war             NUMERIC(5,2) NOT NULL,
    as_of_date      DATE NOT NULL,
    PRIMARY KEY (season_id, player_id)
);
GRANT SELECT ON player_war TO nhl_api_readonly;
-- WAR v2 (war_v2.py): each skater's goals above average by part; NULL for goalies.
ALTER TABLE player_war
    ADD COLUMN IF NOT EXISTS ev_offense   NUMERIC(6,2),
    ADD COLUMN IF NOT EXISTS ev_defense   NUMERIC(6,2),
    ADD COLUMN IF NOT EXISTS finishing    NUMERIC(6,2),
    ADD COLUMN IF NOT EXISTS power_play   NUMERIC(6,2),
    ADD COLUMN IF NOT EXISTS penalty_kill NUMERIC(6,2),
    ADD COLUMN IF NOT EXISTS penalties    NUMERIC(6,2);
"""
PARTS = ["ev_offense", "ev_defense", "finishing", "power_play", "penalty_kill", "penalties"]


def season_goalies(season_id):
    """This season's goalie WAR (GSAx from our stored xG); the same in v1 and v2."""
    from simulate_playoff_odds import goalie_season, stored_goalie_xg

    return goalie_war(goalie_season(season_id // 10000, stored_goalie_xg(season_id)))


def season_war(season_id):
    """v1: this season's WAR for every skater and goalie, skater_war() and goalie_war() combined."""
    players = skater_war(pv.season_skaters(season_id // 10000))
    players.update(season_goalies(season_id))
    return players


def store(cur, season_id, players, as_of):
    """Replace the season's rows (a player can drop out of the NHL's reports; stale rows shouldn't linger)."""
    cur.execute(TABLE_SQL)
    cur.execute("DELETE FROM player_war WHERE season_id = %s", (season_id,))
    for pid, p in players.items():
        group = "G" if p["pos"] == "G" else pv.position_group(p["pos"])
        parts = p.get("parts") or {}
        cur.execute(
            f"""
            INSERT INTO player_war (season_id, player_id, name, team_abbrev, position_group, games_played, gar, war,
                                    as_of_date, {", ".join(PARTS)})
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, {", ".join(["%s"] * len(PARTS))})
            """,
            (season_id, pid, p["name"], p["team"] or None, group, p["gp"], p["gar"], p["war"], as_of,
             *[parts.get(k) for k in PARTS]),
        )


# --- calibration and backtest ---------------------------------------------------

NHL_TEAM_SUMMARY_URL = pv.NHL_TEAM_SUMMARY_URL


def team_records(year):
    """{team: (wins, goal differential, games played)} for the regular season starting in `year`."""
    codes = {t["id"]: t["triCode"] for t in requests.get(pv.NHL_TEAMS_URL, timeout=60).json()["data"]}
    response = requests.get(NHL_TEAM_SUMMARY_URL.format(season=f"{year}{year + 1}"), timeout=60)
    response.raise_for_status()
    return {codes[r["teamId"]]: (r["wins"], r["goalsFor"] - r["goalsAgainst"], r["gamesPlayed"])
            for r in response.json()["data"]}


def _slope(xs, ys):
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    syy = sum((y - my) ** 2 for y in ys)
    return sxy / sxx, my - sxy / sxx * mx, sxy / (sxx * syy) ** 0.5


def fit_goals_per_win(records):
    """Goal differential per extra win (both per game), from {year: team_records(year)}."""
    gd = [g / n for rec in records.values() for _, g, n in rec.values()]
    wins = [w / n for rec in records.values() for w, _, n in rec.values()]
    slope, _, r = _slope(gd, wins)
    return round(1 / slope, 2), round(r, 3)


def moneypuck_goalies(year):
    """The cached MoneyPuck goalie season (the backtest's goalie input for past seasons)."""
    with open(os.path.join(CACHE, "moneypuck", f"goalies_{year}.csv")) as f:
        return pv.season_goalies(f.read())


def backtest(years):
    """
    For each held-out season: GS_TO_GOALS, replacement levels, and
    GOALS_PER_WIN fit on the others, then each team's summed WAR (its
    players' WAR for it; a traded player counts for his last team) against
    its wins. A good WAR has team sums that line up with wins, slope ~1.
    """
    skaters = {y: pv.season_skaters(y) for y in years}
    goalies = {y: moneypuck_goalies(y) for y in years}
    records = {y: team_records(y) for y in years}
    rows = []
    for held in years:
        train = [y for y in years if y != held]
        fit = pv.calibrate(train, skaters=lambda y: skaters[y],
                           team_goals=lambda y: {t: (g, n) for t, (_, g, n) in records[y].items()})
        gpw, _ = fit_goals_per_win({y: records[y] for y in train})
        team_war = defaultdict(float)
        for v in skater_war(skaters[held], fit["gs_to_goals"], fit["replacement_gs"], gpw).values():
            team_war[v["team"]] += v["war"]
        for v in goalie_war(goalies[held], goals_per_win=gpw).values():
            team_war[v["team"]] += v["war"]
        for team, (wins, _, n) in records[held].items():
            rows.append((held, team, team_war[team], wins, n))
    slope, intercept, r = _slope([w for *_, w, _, _ in rows], [x for *_, x, _ in rows])
    return {"team_seasons": len(rows), "r": round(r, 3), "wins_per_war": round(slope, 2),
            "replacement_team_wins": round(intercept, 1), "rows": rows}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--calibrate", action="store_true")
    parser.add_argument("--backtest", action="store_true")
    parser.add_argument("--top", type=int, default=0)
    args = parser.parse_args()
    season_id = current_season_id()
    start = season_id // 10000
    if not (args.calibrate or args.backtest or args.top):
        if not DATABASE_URL:
            raise SystemExit("DATABASE_URL is not set")
        import war_v2  # imports this module

        with psycopg2.connect(DATABASE_URL) as conn:
            players = war_v2.nightly(conn, season_id, date.today())
            players.update(season_goalies(season_id))
            with conn.cursor() as cur:
                store(cur, season_id, players, date.today())
        logger.info(f"Stored WAR v2 for {len(players)} players ({season_id})")
        return
    years = [start - 3, start - 2, start - 1]
    if args.calibrate:
        print({"goals_per_win": fit_goals_per_win({y: team_records(y) for y in years})})
    if args.backtest:
        result = backtest(years)
        rows = result.pop("rows")
        print(result)
        for year, team, war, wins, _ in sorted(rows, key=lambda r: -r[2])[:5] + sorted(rows, key=lambda r: r[2])[:3]:
            print(f"  {year}-{year + 1 - 2000} {team}: {war:5.1f} WAR, {wins} wins")
    if args.top:
        values = skater_war(pv.season_skaters(start))
        for v in sorted(values.values(), key=lambda v: -v["war"])[: args.top]:
            print(f"{v['name']:24} {v['team']} {v['pos']:2} {v['gp']:3} GP  {v['gar']:+5.1f} GAR  {v['war']:+4.2f} WAR")


if __name__ == "__main__":
    main()
