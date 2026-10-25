"""
Era adjustment: how many goals a team scored per game, league-wide, in
every NHL regular season, so a player's numbers can be rescaled to today's
scoring (the compare page's "era-adjusted" view).

A season's numbers times REFERENCE / that season's goals per team-game: a
goal in 1985-86 (3.97 a game) counts for less than one in 2025-26 (3.08).
Completed seasons never change, so they're built once into
assets/league_scoring.json; the season in progress is read live (api.py).

Usage:
    python era.py --build     # rebuild assets/league_scoring.json (one request per season)
"""

import argparse
import json
import os
import time

import requests

ASSET = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "league_scoring.json")
TEAM_SUMMARY_URL = ("https://api.nhle.com/stats/rest/en/team/summary?limit=-1"
                    "&cayenneExp=seasonId={season}%20and%20gameTypeId=2")
FIRST_SEASON = 1917


def season_scoring(season_id, get=requests.get):
    """Goals per team per regular-season game in `season_id` (e.g. 19851986), or None (no NHL season, e.g. 2004-05)."""
    response = get(TEAM_SUMMARY_URL.format(season=season_id), timeout=30)
    response.raise_for_status()
    rows = response.json().get("data", [])
    games = sum(r.get("gamesPlayed") or 0 for r in rows)
    return round(sum(r.get("goalsFor") or 0 for r in rows) / games, 4) if games else None


def build(last_completed_start, get=requests.get):
    """{season_id: goals per team-game} for every completed regular season through the one starting `last_completed_start`."""
    out = {}
    for start in range(FIRST_SEASON, last_completed_start + 1):
        season_id = start * 10000 + start + 1
        scoring = season_scoring(season_id, get)
        if scoring:
            out[str(season_id)] = scoring
        time.sleep(0.1)  # a free API: be polite
    return out


def load():
    with open(ASSET) as f:
        return json.load(f)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--build", action="store_true")
    args = parser.parse_args()
    if args.build:
        from seasons import current_season_id

        seasons = build(current_season_id() // 10000 - 1)
        with open(ASSET, "w") as f:
            json.dump({"note": "Goals per team per regular-season game, league-wide (era.py --build).",
                       "seasons": seasons}, f, indent=0, sort_keys=True)
        print(f"{len(seasons)} seasons, {min(seasons)} to {max(seasons)}")


if __name__ == "__main__":
    main()
