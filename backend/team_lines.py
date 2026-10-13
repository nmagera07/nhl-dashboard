"""
Last game's lines: each team's forward lines and defense pairs from its most
recent completed game, worked out from the NHL's shift charts. Runs in the
daily job (after rosters); served by GET /teams/{team}/lines.

How: every shift has a player, period, start and end. Keep the seconds when
both teams had exactly 5 skaters on the ice (even strength, so power-play
units don't blur the lines), add up how long each pair of teammates was on
together, then take the trios (forwards) and pairs (defense) with the most
time together, each player used once. Positions and names come from that
game's box score.

Why last game: it's the closest open data to tonight's lineup. Projected
lines are only published by sites that would have to be scraped. Season-long
totals (MoneyPuck's lines.csv) were tried first, but an early-season line
that was broken up weeks ago could still top the list.

Usage:
    python team_lines.py              # update teams whose stored game is stale
    python team_lines.py --days 30    # look further back for each team's last game
"""

import argparse
import itertools
import json
import os
import time
from collections import defaultdict
from datetime import date, timedelta

import psycopg2
import requests
from dotenv import load_dotenv

from logging_config import setup_logging

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
logger = setup_logging("team_lines")

SCORE_URL = "https://api-web.nhle.com/v1/score/{date}"
BOXSCORE_URL = "https://api-web.nhle.com/v1/gamecenter/{game_id}/boxscore"
SHIFTS_URL = "https://api.nhle.com/stats/rest/en/shiftcharts?cayenneExp=gameId={game_id}"
HEADERS = {"User-Agent": "nhl-dashboard (personal project)"}  # the stats API 403s a blank one
FINAL_STATES = {"OFF", "FINAL"}
PERIOD_SECONDS = 1200
LOOKBACK_DAYS = 14
FORWARD_LINES, DEFENSE_PAIRS = 4, 3

TABLE_SQL = """
CREATE TABLE IF NOT EXISTS team_lines (
    team_abbrev             VARCHAR(3) PRIMARY KEY,
    game_id                 BIGINT NOT NULL,
    game_date               DATE NOT NULL,
    opponent                VARCHAR(3) NOT NULL,
    home                    BOOLEAN NOT NULL,
    payload                 JSONB NOT NULL,           -- {"lines": [...], "pairs": [...]}
    updated_at              TIMESTAMPTZ DEFAULT NOW()
)
"""


def _get(url):
    for attempt in range(4):
        response = requests.get(url, headers=HEADERS, timeout=30)
        if response.status_code != 429:
            response.raise_for_status()
            return response.json()
        time.sleep(5 * (attempt + 1))
    response.raise_for_status()


def _seconds(clock):
    minutes, seconds = clock.split(":")
    return int(minutes) * 60 + int(seconds)


def roster_from_boxscore(box):
    """{player_id: {"team", "pos" ("F"/"D"/"G"), "name"}} for everyone who dressed."""
    out = {}
    for side in ("awayTeam", "homeTeam"):
        team = box[side]["abbrev"]
        stats = box.get("playerByGameStats", {}).get(side, {})
        for group, pos in (("forwards", "F"), ("defense", "D"), ("goalies", "G")):
            for p in stats.get(group, []):
                out[p["playerId"]] = {"team": team, "pos": pos, "name": (p.get("name") or {}).get("default", "")}
    return out


def even_strength_time(shifts, roster):
    """
    ({(team, a, b): seconds together}, {second: {team: frozenset(ids)}}) over
    the seconds when both teams had exactly 5 skaters on the ice.
    """
    on = defaultdict(lambda: defaultdict(set))
    for s in shifts:
        player = roster.get(s.get("playerId"))
        if not player or player["pos"] == "G" or not s.get("startTime") or not s.get("endTime"):
            continue
        base = (s["period"] - 1) * PERIOD_SECONDS
        for t in range(base + _seconds(s["startTime"]), base + _seconds(s["endTime"])):
            on[t][player["team"]].add(s["playerId"])
    teams = {p["team"] for p in roster.values()}
    pairs, even = defaultdict(int), {}
    for t, by_team in on.items():
        if len(by_team) != len(teams) or any(len(ids) != 5 for ids in by_team.values()):
            continue
        even[t] = {team: frozenset(ids) for team, ids in by_team.items()}
        for team, ids in by_team.items():
            for a, b in itertools.combinations(sorted(ids), 2):
                pairs[(team, a, b)] += 1
    return pairs, even


def pick_groups(players, size, limit, together):
    """The `limit` groups of `size` with the most pairwise time together, each player once."""
    def score(group):
        return sum(together(a, b) for a, b in itertools.combinations(sorted(group), 2))

    picked, used = [], set()
    for group in sorted(itertools.combinations(sorted(players), size), key=score, reverse=True):
        if used & set(group) or score(group) == 0:
            continue
        used |= set(group)
        picked.append(list(group))
        if len(picked) == limit:
            break
    return picked


def display_names(names):
    """{id: name}: last name, keeping the box score's first initial only when
    teammates share a last name (two Tkachuks, two Protases)."""
    last = {pid: n.split(". ", 1)[-1] for pid, n in names.items()}
    counts = defaultdict(int)
    for n in last.values():
        counts[n] += 1
    return {pid: (names[pid] if counts[last[pid]] > 1 else last[pid]) for pid in names}


def lines_from_game(box, shifts):
    """{team: {"lines": [...], "pairs": [...]}} for one completed game."""
    roster = roster_from_boxscore(box)
    pairs, even = even_strength_time(shifts, roster)
    out = {}
    for team in {p["team"] for p in roster.values()}:
        mine = {pid: p for pid, p in roster.items() if p["team"] == team}
        names = display_names({pid: p["name"] for pid, p in mine.items()})

        def together(a, b, team=team):
            return pairs.get((team, a, b), 0)

        def describe(group):
            seconds = sum(1 for by_team in even.values() if set(group) <= by_team.get(team, frozenset()))
            return {"players": [names[i] for i in group], "player_ids": group, "minutes": round(seconds / 60, 1)}

        forwards = [pid for pid, p in mine.items() if p["pos"] == "F"]
        defense = [pid for pid, p in mine.items() if p["pos"] == "D"]
        out[team] = {
            "lines": [describe(g) for g in pick_groups(forwards, 3, FORWARD_LINES, together)],
            "pairs": [describe(g) for g in pick_groups(defense, 2, DEFENSE_PAIRS, together)],
        }
    return out


def latest_games(days, today=None, get=_get):
    """{team: game} for each team's most recent completed game in the last `days` days."""
    today = today or date.today()
    latest = {}
    for back in range(1, days + 1):
        day = today - timedelta(days=back)
        for g in get(SCORE_URL.format(date=day)).get("games", []):
            if g.get("gameState") not in FINAL_STATES or g.get("gameType") not in (2, 3):
                continue
            away, home = g["awayTeam"]["abbrev"], g["homeTeam"]["abbrev"]
            for team, opp, is_home in ((away, home, False), (home, away, True)):
                latest.setdefault(team, {"game_id": g["id"], "date": str(day), "opponent": opp, "home": is_home})
    return latest


def update(cur, days=LOOKBACK_DAYS, get=_get):
    """Refresh every team whose stored game isn't its latest. Returns teams updated."""
    cur.execute(TABLE_SQL)
    cur.execute("GRANT SELECT ON team_lines TO nhl_api_readonly")
    cur.execute("SELECT team_abbrev, game_id FROM team_lines")
    stored = dict(cur.fetchall())
    latest = latest_games(days, get=get)
    stale = {team: g for team, g in latest.items() if stored.get(team) != g["game_id"]}
    updated = 0
    for game_id in sorted({g["game_id"] for g in stale.values()}):
        try:
            box = get(BOXSCORE_URL.format(game_id=game_id))
            shifts = get(SHIFTS_URL.format(game_id=game_id)).get("data", [])
        except requests.RequestException as exc:
            logger.warning(f"Game {game_id}: no shift data ({exc}); keeping the previous lines")
            continue
        if not shifts:
            logger.warning(f"Game {game_id}: empty shift chart; keeping the previous lines")
            continue
        for team, lines in lines_from_game(box, shifts).items():
            g = stale.get(team)
            if not g or g["game_id"] != game_id:
                continue
            cur.execute(
                """
                INSERT INTO team_lines (team_abbrev, game_id, game_date, opponent, home, payload, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT (team_abbrev) DO UPDATE SET
                    game_id = EXCLUDED.game_id, game_date = EXCLUDED.game_date, opponent = EXCLUDED.opponent,
                    home = EXCLUDED.home, payload = EXCLUDED.payload, updated_at = NOW()
                """,
                (team, game_id, g["date"], g["opponent"], g["home"], json.dumps(lines)),
            )
            updated += 1
        time.sleep(0.5)  # polite to the NHL API
    return updated


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=LOOKBACK_DAYS)
    args = parser.parse_args()
    if not DATABASE_URL:
        raise SystemExit("DATABASE_URL is not set")
    with psycopg2.connect(DATABASE_URL) as conn, conn.cursor() as cur:
        updated = update(cur, args.days)
    logger.info(f"Lines updated for {updated} teams")


if __name__ == "__main__":
    main()
