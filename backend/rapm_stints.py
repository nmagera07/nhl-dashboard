"""
RAPM step 1: every game split into 5-on-5 stints.

A stint is a stretch of a period where the same ten skaters (and both
goalies) are on the ice; a faceoff starts a new one even when nobody
changes, so every draw's zone is recorded. RAPM (step 2) regresses what happens in each stint
on who was out there, so a player's rating is separated from his linemates
and the opponents he faced.

Each stint carries:
  - the five home and five away skaters (sorted player ids)
  - its length in seconds
  - xG, goals and unblocked shots for each side (our xG model, 5-on-5 shots)
  - the score at its start (home minus away), since trailing teams push
  - the zone of the faceoff it started on, from the home side ("O", "D",
    "N"), or None when it started on the fly

Who was on the ice comes from the NHL's shift charts; a player is on for a
moment t when start < t <= end (as in ingest_xg.on_ice), so a goal at a
change belongs to the group that was out when it went in.

When the NHL never posts a game's shift chart (whole stretches go
missing: Apr 8-15 2025, Oct 13-19 2026), the shifts come from its HTML
time-on-ice reports instead (TH home, TV visitor), which list every
player's shifts under his sweater number.

Games come from a local cache, {CACHE}/{pbp,shifts}/{season}/{game_id}.json.gz
(the same one train_xg.py and the backtests read); `--download` fills it.
Stints for a season are written to {CACHE}/stints/{season}.json.gz.

Usage:
    python rapm_stints.py --download 20232024 20242025   # fill the cache (polite: ~4 calls/s)
    python rapm_stints.py --build 20232024 20242025 20252026
    python rapm_stints.py --check 20252026               # sanity report
"""

import argparse
import gzip
import json
import os
import re
import time
from collections import defaultdict

import requests

import xg_model as xm
from logging_config import setup_logging

logger = setup_logging("rapm_stints")

CACHE = os.path.expanduser("~/.cache/puckpulse")
PBP_URL = "https://api-web.nhle.com/v1/gamecenter/{game_id}/play-by-play"
SHIFTS_URL = "https://api.nhle.com/stats/rest/en/shiftcharts?cayenneExp=gameId={game_id}"
TOI_REPORT_URL = "https://www.nhl.com/scores/htmlreports/{season}/{side}{number}.HTM"  # TH home, TV visitor
HEADERS = {"User-Agent": "nhl-dashboard (personal project)"}
FINAL_STATES = {"OFF", "FINAL"}
FIVE_ON_FIVE = "1551"
SHIFT = 517  # shift-chart typeCode for a shift (goal rows are 505)
MIN_SHIFTS = 100  # a full game has ~700; fewer means the chart is missing
MAX_GAMES = 1400  # regular-season game numbers run 0001..1312 (1344 in an 84-game season)
PAUSE = 0.25


def _clock(text):
    minutes, seconds = (text or "0:00").split(":")
    return int(minutes) * 60 + int(seconds)


def _path(kind, season, game_id):
    return os.path.join(CACHE, kind, str(season), f"{game_id}.json.gz")


def load(kind, season, game_id):
    path = _path(kind, season, game_id)
    if not os.path.exists(path):
        return None
    with gzip.open(path, "rt") as f:
        return json.load(f)


def _save(kind, season, game_id, data):
    path = _path(kind, season, game_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with gzip.open(path, "wt") as f:
        json.dump(data, f)


def _get(url):
    for attempt in range(4):
        response = requests.get(url, headers=HEADERS, timeout=30)
        if response.status_code == 404:
            return None
        if response.status_code != 429:
            response.raise_for_status()
            return response.json()
        time.sleep(5 * (attempt + 1))
    response.raise_for_status()


def _get_text(url):
    response = requests.get(url, headers=HEADERS, timeout=30)
    if response.status_code == 404:
        return None
    response.raise_for_status()
    return response.text


_PLAYER = re.compile(r'class="playerHeading[^"]*"[^>]*>(\d+) [^<]*</td>')
# Shift #, period, "start elapsed / game clock", "end elapsed / game clock" (the per-period summary rows have no "/").
_SHIFT_ROW = re.compile(r'<td[^>]*>\d+</td>\s*<td[^>]*>(\d|OT)</td>\s*'
                        r'<td[^>]*>(\d+:\d\d) / [\d:]+</td>\s*<td[^>]*>(\d+:\d\d) / [\d:]+</td>')


def html_shifts(pbp, get_text=_get_text):
    """
    The game's shifts from the HTML time-on-ice reports, shaped like the
    shift chart's rows ({playerId, teamId, period, startTime, endTime,
    typeCode}); None if either report is missing.
    """
    game_id = str(pbp["id"])
    season = f"{game_id[:4]}{int(game_id[:4]) + 1}"
    rows = []
    for side, team in (("TH", pbp["homeTeam"]["id"]), ("TV", pbp["awayTeam"]["id"])):
        html = get_text(TOI_REPORT_URL.format(season=season, side=side, number=game_id[4:]))
        if not html:
            return None
        number_to_id = {r.get("sweaterNumber"): r["playerId"] for r in pbp.get("rosterSpots", []) if r["teamId"] == team}
        parts = _PLAYER.split(html)  # [before, number, his rows, number, his rows, ...]
        for number, chunk in zip(parts[1::2], parts[2::2]):
            pid = number_to_id.get(int(number))
            if pid is None:
                continue
            for period, start, end in _SHIFT_ROW.findall(chunk):
                rows.append({"playerId": pid, "teamId": team, "period": 4 if period == "OT" else int(period),
                             "startTime": start, "endTime": end, "typeCode": SHIFT})
    return rows


def download(season, get=_get, get_text=_get_text, pause=PAUSE):
    """
    Cache play-by-play and shift charts for a season's finished regular-season
    games. Already-cached games are skipped, so it can be re-run (and picks
    up where it stopped). Returns {"pbp": n, "shifts": n} newly saved.
    """
    saved = {"pbp": 0, "shifts": 0}
    missing_in_a_row = 0
    for number in range(1, MAX_GAMES + 1):
        game_id = int(f"{str(season)[:4]}02{number:04d}")
        pbp = load("pbp", season, game_id)
        if pbp is None:
            pbp = get(PBP_URL.format(game_id=game_id))
            time.sleep(pause)
            if pbp is None:
                missing_in_a_row += 1
                if missing_in_a_row >= 3:
                    break  # past the season's last game
                continue
            if pbp.get("gameState") not in FINAL_STATES:
                continue  # not played yet: don't cache, check again next time
            _save("pbp", season, game_id, pbp)
            saved["pbp"] += 1
        missing_in_a_row = 0
        if load("shifts", season, game_id) is None:
            shifts = (get(SHIFTS_URL.format(game_id=game_id)) or {}).get("data", [])
            time.sleep(pause)
            if len(shifts) < MIN_SHIFTS:
                shifts = html_shifts(pbp, get_text) or []
                time.sleep(pause)
            if len(shifts) >= MIN_SHIFTS:  # neither yet: the reports may still be posted later
                _save("shifts", season, game_id, shifts)
                saved["shifts"] += 1
        if number % 100 == 0:
            logger.info(f"{season}: through game {number} ({saved['pbp']} pbp, {saved['shifts']} shifts saved)")
    return saved


def _home_zone(play, home_id):
    """A faceoff's zone from the home side ("O" = in the away end); zoneCode is from the winner's side."""
    zone = (play.get("details") or {}).get("zoneCode")
    if zone not in ("O", "D", "N"):
        return None
    if (play.get("details") or {}).get("eventOwnerTeamId") == home_id or zone == "N":
        return zone
    return {"O": "D", "D": "O"}[zone]


def stints(pbp, shifts, model):
    """
    The game's 5-on-5 stints, in order: [{period, start, end, seconds, home,
    away, home_xg, away_xg, home_goals, away_goals, home_shots, away_shots,
    score, zone}], plus how many 5-on-5 shots (by the play-by-play's
    situation code) didn't land in a 5-on-5 stint: (stints, unmatched).
    """
    home_id = pbp["homeTeam"]["id"]
    roster = {r["playerId"]: (r["teamId"] == home_id, r.get("positionCode") == "G")
              for r in pbp.get("rosterSpots", [])}

    by_period = defaultdict(list)
    for s in shifts:
        if s.get("typeCode", SHIFT) != SHIFT or s.get("playerId") not in roster:
            continue
        if not s.get("startTime") or not s.get("endTime") or s.get("period", 0) > 4:
            continue  # period 5 is a regular-season shootout
        start, end = _clock(s["startTime"]), _clock(s["endTime"])
        if end > start:
            by_period[s["period"]].append((start, end, s["playerId"]))

    faceoffs, goals = {}, []
    for play in pbp.get("plays", []):
        period = (play.get("periodDescriptor") or {}).get("number")
        if (play.get("periodDescriptor") or {}).get("periodType") == "SO":
            continue
        t = _clock(play.get("timeInPeriod"))
        if play.get("typeDescKey") == "faceoff":
            faceoffs.setdefault((period, t), _home_zone(play, home_id))
        elif play.get("typeDescKey") == "goal":
            team = (play.get("details") or {}).get("eventOwnerTeamId")
            goals.append((period, t, 1 if team == home_id else -1))

    out = []
    for period in sorted(by_period):
        rows = by_period[period]
        draws = {t for p, t in faceoffs if p == period}
        marks = sorted({t for start, end, _ in rows for t in (start, end)} | draws)
        for a, b in zip(marks, marks[1:]):
            on = [pid for start, end, pid in rows if start <= a and end >= b]
            home = sorted(p for p in on if roster[p] == (True, False))
            away = sorted(p for p in on if roster[p] == (False, False))
            home_g = sum(1 for p in on if roster[p] == (True, True))
            away_g = sum(1 for p in on if roster[p] == (False, True))
            if not (len(home) == 5 and len(away) == 5 and home_g == 1 and away_g == 1):
                continue
            last = out[-1] if out else None
            if (last and last["period"] == period and last["end"] == a and a not in draws
                    and last["home"] == home and last["away"] == away):
                last["end"] = b  # same ten skaters, no faceoff in between: one stint
                continue
            score = sum(sign for p, t, sign in goals if (p, t) <= (period, a))
            out.append({"period": period, "start": a, "end": b, "home": home, "away": away,
                        "home_xg": 0.0, "away_xg": 0.0, "home_goals": 0, "away_goals": 0,
                        "home_shots": 0, "away_shots": 0, "score": score,
                        "zone": faceoffs.get((period, a))})

    index = defaultdict(list)
    for s in out:
        s["seconds"] = s["end"] - s["start"]
        index[s["period"]].append(s)
    unmatched = 0
    for shot in xm.shots_from_game(pbp):
        if shot["situation"] != FIVE_ON_FIVE:
            continue
        stint = next((s for s in index.get(shot["period"], ()) if s["start"] < shot["time"] <= s["end"]), None)
        if stint is None:
            unmatched += 1
            continue
        side = "home" if shot["team_is_home"] else "away"
        stint[f"{side}_xg"] += xm.predict(shot, model)
        stint[f"{side}_shots"] += 1
        stint[f"{side}_goals"] += shot["goal"]
    for s in out:
        s["home_xg"], s["away_xg"] = round(s["home_xg"], 4), round(s["away_xg"], 4)
    return out, unmatched


def _game_ids(season):
    folder = os.path.join(CACHE, "pbp", str(season))
    names = sorted(os.listdir(folder)) if os.path.isdir(folder) else []
    return [int(n.split(".")[0]) for n in names if n[4:6] == "02"]  # regular season


def build(season, model=None):
    """Write {CACHE}/stints/{season}.json.gz: {game_id: [stints]}; games without a shift chart are left out."""
    model = model or xm.load_model()
    games, skipped, unmatched, shots = {}, [], 0, 0
    for game_id in _game_ids(season):
        pbp, shifts = load("pbp", season, game_id), load("shifts", season, game_id)
        if not shifts:
            skipped.append(game_id)
            continue
        game_stints, missed = stints(pbp, shifts, model)
        games[str(game_id)] = game_stints
        unmatched += missed
        shots += missed + sum(s["home_shots"] + s["away_shots"] for s in game_stints)
    path = os.path.join(CACHE, "stints", f"{season}.json.gz")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with gzip.open(path, "wt") as f:
        json.dump(games, f, separators=(",", ":"))
    logger.info(f"{season}: {len(games)} games, {sum(len(g) for g in games.values())} stints; "
                f"{len(skipped)} without a shift chart; {unmatched} of {shots} 5v5 shots outside a stint")
    return games


def load_stints(season):
    with gzip.open(os.path.join(CACHE, "stints", f"{season}.json.gz"), "rt") as f:
        return json.load(f)


def check(season):
    """Plain-language sanity numbers for a built season."""
    games = load_stints(season)
    all_stints = [s for g in games.values() for s in g]
    seconds = sum(s["seconds"] for s in all_stints)
    toi = defaultdict(int)
    for s in all_stints:
        for p in s["home"] + s["away"]:
            toi[p] += s["seconds"]
    xg = sum(s["home_xg"] + s["away_xg"] for s in all_stints)
    goals = sum(s["home_goals"] + s["away_goals"] for s in all_stints)
    zones = defaultdict(int)
    for s in all_stints:
        zones[s["zone"]] += 1
    lengths = sorted(s["seconds"] for s in all_stints)
    print(f"{season}: {len(games)} games, {len(all_stints)} stints ({len(all_stints) / len(games):.0f} a game)")
    print(f"  5v5 time a game: {seconds / len(games) / 60:.1f} min; median stint {lengths[len(lengths) // 2]}s")
    print(f"  5v5 xG a game: {xg / len(games):.2f}; goals a game: {goals / len(games):.2f}")
    print(f"  starts: {zones['O']} home O-zone, {zones['D']} home D-zone, {zones['N']} neutral, {zones[None]} on the fly")
    print(f"  skaters: {len(toi)}; with 500+ 5v5 minutes: {sum(1 for t in toi.values() if t >= 500 * 60)}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--download", nargs="+", type=int, metavar="SEASON")
    parser.add_argument("--build", nargs="+", type=int, metavar="SEASON")
    parser.add_argument("--check", nargs="+", type=int, metavar="SEASON")
    args = parser.parse_args()
    for season in args.download or ():
        logger.info(f"{season}: saved {download(season)}")
    for season in args.build or ():
        build(season)
    for season in args.check or ():
        check(season)


if __name__ == "__main__":
    main()
