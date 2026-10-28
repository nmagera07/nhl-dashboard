"""
WAR v2 (step 3): wins above replacement built from RAPM instead of Game Score.

A skater's goals above average is the sum of:
  - 5v5 offense and defense: his RAPM ratings (rapm.chain, xG per 60
    above average) times his 5v5 hours
  - finishing: his goals minus the xG of his own shots (not into an empty net)
  - power play / penalty kill: on-ice xG for (PP) or against (PK) compared
    with the league rate over the same minutes, split among the skaters on
    the ice (5 on the power play, 4 killing), so a unit's credit adds up to
    the unit's
  - penalties: minutes drawn minus minutes taken, times what a penalty
    minute is worth (the league's net power-play xG per penalty minute)

Then, as in war.py: replacement level is what fringe players (5-29 GP)
give per game, by position group; GAR = goals above average - replacement
x games; WAR = GAR / GOALS_PER_WIN. Goalies are unchanged (war.goalie_war,
GSAx).

The season inputs come from the local cache (rapm_stints.py) and are saved
to {CACHE}/war_v2/inputs_{season}.json after the first pass.

Usage:
    python war_v2.py --backtest           # team WAR vs. wins, v1 and v2, same season and next season
    python war_v2.py --top 20 --season 20252026
"""

import argparse
import gzip
import json
import os
import time
from collections import defaultdict
from datetime import timedelta

import numpy as np

import rapm
import rapm_stints as rs
import war
import xg_model as xm

SEASONS = [20212022, 20222023, 20232024, 20242025, 20252026, 20262027]
FRINGE_GP = (5, 29)  # war.py / player_values.py's replacement pool
PP_SKATERS, PK_SKATERS = 5, 4
# Fringe (5-29 GP) goals above average per game, half-weight finishing: 2022-23..2025-26 ran
# F -0.017/-0.018/-0.026/-0.016 and D -0.017/-0.021/-0.025/-0.032.
REPLACEMENT = {"F": -0.019, "D": -0.024}
FINISHING_WEIGHT = 0.5  # finishing barely carries over (r -0.06 next season); half weight fit wins best (backtest)


LABELS = {"ev_offense": "EV off", "ev_defense": "EV def", "finishing": "finish", "power_play": "PP",
          "penalty_kill": "PK", "penalties": "pens"}


def _group(position_code):
    return "D" if position_code == "D" else "F"


def game_extract(pbp, shifts, model):
    """
    What WAR v2 needs from one game, small enough to store (the nightly
    job keeps one per game): {"stints": 5v5 stints or None without a shift
    chart, "players": {pid: {name, pos, team, goals, ixg, pim_taken,
    pim_drawn, pp_seconds, pp_xgf, pp_xga, pk_seconds, pk_xga}}, "pim": the
    game's minor and major penalty minutes}.
    """
    abbrev = {pbp["homeTeam"]["id"]: pbp["homeTeam"]["abbrev"], pbp["awayTeam"]["id"]: pbp["awayTeam"]["abbrev"]}
    players = {}
    for r in pbp.get("rosterSpots", []):
        if r.get("positionCode") != "G":
            players[r["playerId"]] = {
                "name": f"{r['firstName']['default']} {r['lastName']['default']}", "pos": _group(r.get("positionCode")),
                "team": abbrev.get(r["teamId"]), "goals": 0, "ixg": 0.0, "pim_taken": 0, "pim_drawn": 0,
                "pp_seconds": 0.0, "pp_xgf": 0.0, "pp_xga": 0.0, "pk_seconds": 0.0, "pk_xga": 0.0}
    for shot in xm.shots_from_game(pbp):
        if shot["goalie"] is not None and shot["shooter"] in players:
            players[shot["shooter"]]["ixg"] += xm.predict(shot, model)
            players[shot["shooter"]]["goals"] += shot["goal"]
    pim = 0
    for play in pbp.get("plays", []):
        d = play.get("details") or {}
        if play.get("typeDescKey") != "penalty" or d.get("typeCode") not in ("MIN", "MAJ"):
            continue
        minutes = d.get("duration") or 0
        if d.get("committedByPlayerId") in players:
            players[d["committedByPlayerId"]]["pim_taken"] += minutes
        if d.get("drawnByPlayerId") in players:
            players[d["drawnByPlayerId"]]["pim_drawn"] += minutes
        pim += minutes
    stints = None
    if shifts:
        stints, _ = rs.stints(pbp, shifts, model)
        for pid, st in rs.special_teams(pbp, shifts, model).items():
            if pid in players:
                for key in ("pp_seconds", "pp_xgf", "pp_xga", "pk_seconds", "pk_xga"):
                    players[pid][key] += st[key]
    return {"stints": stints, "players": players, "pim": pim}


def combine(extracts):
    """
    A season's inputs from its games' extracts, oldest first (so a traded
    player's team is his last): {"players": {pid: {..., gp}}, "league":
    {pp_seconds, pp_xgf, pk_seconds, pk_xga, pp_net_xg, pim}}.
    """
    players = {}
    league = {"pp_seconds": 0.0, "pp_xgf": 0.0, "pk_seconds": 0.0, "pk_xga": 0.0, "pp_net_xg": 0.0, "pim": 0}
    for extract in extracts:
        league["pim"] += extract["pim"]
        for pid, g in extract["players"].items():
            pid = int(pid)
            p = players.setdefault(pid, {"gp": 0, "goals": 0, "ixg": 0.0, "pim_taken": 0, "pim_drawn": 0,
                                         "pp_seconds": 0.0, "pp_xgf": 0.0, "pk_seconds": 0.0, "pk_xga": 0.0})
            p.update(name=g["name"], pos=g["pos"], team=g["team"])
            p["gp"] += 1
            for key in ("goals", "ixg", "pim_taken", "pim_drawn", "pp_seconds", "pp_xgf", "pk_seconds", "pk_xga"):
                p[key] += g[key]
            # Team totals: each PP skater carries 1/5 of his unit's time and xG, each PK skater 1/4.
            league["pp_seconds"] += g["pp_seconds"] / PP_SKATERS
            league["pp_xgf"] += g["pp_xgf"] / PP_SKATERS
            league["pk_seconds"] += g["pk_seconds"] / PK_SKATERS
            league["pk_xga"] += g["pk_xga"] / PK_SKATERS
            league["pp_net_xg"] += (g["pp_xgf"] - g["pp_xga"]) / PP_SKATERS
    return {"players": players, "league": league}


def season_inputs(season, model=None):
    """combine() over every cached regular-season game (offline), saved to {CACHE}/war_v2/inputs_{season}.json."""
    path = os.path.join(rs.CACHE, "war_v2", f"inputs_{season}.json")
    if os.path.exists(path):
        with open(path) as f:
            data = json.load(f)
        data["players"] = {int(k): v for k, v in data["players"].items()}
        return data
    model = model or xm.load_model()
    extracts = []
    for game_id in rs._game_ids(season):
        extract = game_extract(rs.load("pbp", season, game_id), rs.load("shifts", season, game_id), model)
        extract["stints"] = None  # the offline path reads stints from their own cache
        extracts.append(extract)
    data = combine(extracts)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f)
    return data


def goals_above_average(inputs, ev, finishing_weight=1.0):
    """{pid: {ev_offense, ev_defense, finishing, power_play, penalty_kill, penalties, total}} in goals."""
    league = inputs["league"]
    # xG per second of power play for the PP side, and the same shots seen from the PK side (0 before any)
    pp_rate = league["pp_xgf"] / league["pp_seconds"] if league["pp_seconds"] else 0.0
    pk_rate = league["pk_xga"] / league["pk_seconds"] if league["pk_seconds"] else 0.0
    per_pim = league["pp_net_xg"] / league["pim"] if league["pim"] else 0.0
    out = {}
    for pid, p in inputs["players"].items():
        r = ev.get(pid, {"offense": 0.0, "defense": 0.0, "hours": 0.0})
        parts = {
            "ev_offense": r["offense"] * r["hours"],
            "ev_defense": r["defense"] * r["hours"],
            "finishing": (p["goals"] - p["ixg"]) * finishing_weight,
            "power_play": (p["pp_xgf"] - pp_rate * p["pp_seconds"]) / PP_SKATERS,
            "penalty_kill": (pk_rate * p["pk_seconds"] - p["pk_xga"]) / PK_SKATERS,
            "penalties": (p["pim_drawn"] - p["pim_taken"]) * per_pim,
        }
        parts["total"] = sum(parts.values())
        out[pid] = parts
    return out


def replacement_levels(inputs, gaa):
    """Goals above average per game of the fringe (5-29 GP) players, by position group."""
    players = inputs["players"]
    replacement = {}
    for group in ("F", "D"):
        pool = [pid for pid, p in players.items() if p["pos"] == group and FRINGE_GP[0] <= p["gp"] <= FRINGE_GP[1]]
        games = sum(players[pid]["gp"] for pid in pool)
        replacement[group] = sum(gaa[pid]["total"] for pid in pool) / games if games else 0.0  # none yet (early season)
    return replacement


def skater_war(inputs, ev, goals_per_win=war.GOALS_PER_WIN, finishing_weight=FINISHING_WEIGHT, replacement=None):
    """
    war.skater_war()'s shape, plus the parts: {pid: {name, team, pos, gp,
    gar, war, parts}}. `replacement` defaults to this season's own fringe
    players (the backtest); the nightly job passes REPLACEMENT, since the
    fringe pool is thin early in a season.
    """
    gaa = goals_above_average(inputs, ev, finishing_weight)
    players = inputs["players"]
    replacement = replacement or replacement_levels(inputs, gaa)
    out = {}
    for pid, p in players.items():
        gar = gaa[pid]["total"] - replacement[p["pos"]] * p["gp"]
        out[pid] = {"name": p["name"], "team": p["team"], "pos": p["pos"], "gp": p["gp"],
                    "gar": round(gar, 2), "war": round(gar / goals_per_win, 2),
                    "parts": {k: round(v, 2) for k, v in gaa[pid].items()}}
    return out


def ev_ratings(season, seasons=SEASONS, box=False):
    """
    RAPM through `season` (a chain from the oldest cached season), with 5v5
    hours in `season`; box=True adds the box-score prior (box_prior.py).
    """
    chain = [s for s in seasons if s <= season and os.path.exists(os.path.join(rs.CACHE, "stints", f"{s}.json.gz"))]
    if box:
        import box_prior
        return box_prior.chain_with_box(chain)[0][season]
    beta, design, sums = rapm.chain(chain)
    return rapm.ratings(beta, design, sums)


def _team_sums(players):
    totals = defaultdict(float)
    for p in players.values():
        totals[p["team"]] += p["war"]
    return totals


def _corr(rows):
    slope, intercept, r = war._slope([x for x, _ in rows], [y for _, y in rows])
    return {"r": round(r, 3), "wins_per_war": round(slope, 2), "n": len(rows)}


def backtest(years=(2022, 2023, 2024, 2025)):
    """
    v1 vs v2, three ways, goals-per-win held out by season:
      same season: each team's summed WAR against its wins (war.backtest's test)
      next season: each player's WAR per game, times his games for his team
        the next season, summed by team, against that season's wins
      roster changes: the same, minus what the team's players were worth for
        it the season before, against its change in wins: whatever stayed
        (coach, system, the players who stayed) cancels out, so a rating
        can't get credit for team context that carried over
    """
    records = {y: war.team_records(y) for y in years}
    goalies = {y: war.moneypuck_goalies(y) for y in years}
    skaters = {y: war.pv.season_skaters(y) for y in years}
    v1, v2, v2_half, v2_box = {}, {}, {}, {}
    for y in years:
        gpw, _ = war.fit_goals_per_win({o: records[o] for o in years if o != y})
        season = int(f"{y}{y + 1}")
        goalie = war.goalie_war(goalies[y], goals_per_win=gpw)
        fit = war.pv.calibrate([o for o in years if o != y], skaters=lambda o: skaters[o],
                               team_goals=lambda o: {t: (g, n) for t, (_, g, n) in records[o].items()})
        v1[y] = {**war.skater_war(skaters[y], fit["gs_to_goals"], fit["replacement_gs"], gpw), **goalie}
        inputs, ev = season_inputs(season), ev_ratings(season)
        v2[y] = {**skater_war(inputs, ev, gpw, finishing_weight=1.0), **goalie}
        v2_half[y] = {**skater_war(inputs, ev, gpw), **goalie}
        v2_box[y] = {**skater_war(inputs, ev_ratings(season, box=True), gpw, finishing_weight=0.5), **goalie}
    results = {}
    for name, by_year in (("v1", v1), ("v2", v2), ("v2, half finishing", v2_half),
                          ("v2 + box prior, half finishing", v2_box)):
        same = [(_team_sums(by_year[y])[t], wins) for y in years for t, (wins, _, _) in records[y].items()]
        nxt = []
        for y, later in zip(years, years[1:]):
            team = defaultdict(float)
            for pid, p in by_year[later].items():
                before = by_year[y].get(pid)
                if before and before["gp"]:
                    team[p["team"]] += before["war"] / before["gp"] * p["gp"]
            nxt += [(team[t], wins) for t, (wins, _, _) in records[later].items()]
        changes = []
        for y, later in zip(years, years[1:]):
            before, after = defaultdict(float), defaultdict(float)
            for p in by_year[y].values():
                if p["gp"]:
                    before[p["team"]] += p["war"]
            for pid, p in by_year[later].items():
                prior = by_year[y].get(pid)
                if prior and prior["gp"]:
                    after[p["team"]] += prior["war"] / prior["gp"] * p["gp"]
            changes += [(after[t] - before[t], wins - records[y][t][0])
                        for t, (wins, _, _) in records[later].items() if t in records[y]]
        results[name] = {"same season": _corr(same), "next season": _corr(nxt), "roster changes": _corr(changes)}
    return results, v2


# --- the nightly step (war.py runs it) -------------------------------------------

TABLES_SQL = """
CREATE TABLE IF NOT EXISTS war_v2_games (
    game_id     BIGINT PRIMARY KEY,
    season_id   INTEGER NOT NULL,
    game_date   DATE NOT NULL,
    has_stints  BOOLEAN NOT NULL,   -- false: no shift chart yet (retried for SHIFT_RETRY_DAYS)
    data        BYTEA NOT NULL      -- game_extract(), gzipped JSON (~5 KB)
);
CREATE TABLE IF NOT EXISTS rapm_ratings (
    season_id   INTEGER NOT NULL,
    player_id   INTEGER NOT NULL,
    offense     NUMERIC(7,4) NOT NULL,   -- xG/60 at 5v5 above average
    defense     NUMERIC(7,4) NOT NULL,   -- xG/60 prevented (positive = good)
    hours       NUMERIC(7,3) NOT NULL,   -- 5v5 hours that season
    PRIMARY KEY (season_id, player_id)
);
"""
SHIFT_RETRY_DAYS = 14  # as ingest_xg.py: keep checking for a late shift chart this long


def games_to_fetch(cur, season_id, today):
    """Finished regular-season games (ingest_xg.py's) not stored yet, or stored without a shift chart recently."""
    cur.execute(
        """
        SELECT DISTINCT x.game_id, x.game_date FROM team_game_xg x
        LEFT JOIN war_v2_games w ON w.game_id = x.game_id
        WHERE x.season_id = %s AND x.game_type = 2
          AND (w.game_id IS NULL OR (NOT w.has_stints AND x.game_date >= %s))
        ORDER BY x.game_date, x.game_id
        """,
        (season_id, today - timedelta(days=SHIFT_RETRY_DAYS)),
    )
    return cur.fetchall()


def store_games(cur, season_id, today, get=rs._get, get_text=rs._get_text, model=None, pause=rs.PAUSE):
    """Fetch and store each game's extract; returns (stored, without a shift chart)."""
    model = model or xm.load_model()
    stored = missing = 0
    for game_id, game_date in games_to_fetch(cur, season_id, today):
        pbp = get(rs.PBP_URL.format(game_id=game_id))
        time.sleep(pause)
        if not pbp:
            continue
        shifts = (get(rs.SHIFTS_URL.format(game_id=game_id)) or {}).get("data", [])
        time.sleep(pause)
        if len(shifts) < rs.MIN_SHIFTS:
            shifts = rs.html_shifts(pbp, get_text) or []  # the NHL skips whole stretches of shift charts
            time.sleep(pause)
        has_stints = len(shifts) >= rs.MIN_SHIFTS
        missing += not has_stints
        extract = game_extract(pbp, shifts if has_stints else None, model)
        cur.execute(
            """
            INSERT INTO war_v2_games (game_id, season_id, game_date, has_stints, data) VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (game_id) DO UPDATE SET has_stints = EXCLUDED.has_stints, data = EXCLUDED.data
            """,
            (game_id, season_id, game_date, has_stints, gzip.compress(json.dumps(extract).encode())),
        )
        stored += 1
    return stored, missing


def load_blobs(cur, season_id):
    """The season's stored extracts, still compressed (~9 MB by April), oldest first."""
    cur.execute("SELECT game_id, data FROM war_v2_games WHERE season_id = %s ORDER BY game_date, game_id", (season_id,))
    return [(game_id, bytes(data)) for game_id, data in cur.fetchall()]


class StoredStints:
    """
    {game_id: stints} for rapm.build, unpacked one game at a time: a whole
    season of stints as Python objects (~1 MB a game) won't fit in the
    ingest job's 1 GiB.
    """

    def __init__(self, blobs):
        self.blobs = blobs

    def items(self):
        for game_id, blob in self.blobs:
            stints = json.loads(gzip.decompress(blob))["stints"]
            if stints:
                yield str(game_id), stints


def previous_season(season_id):
    return season_id - 10001  # 20262027 -> 20252026


def prior_beta(cur, season_id, design):
    """Last season's stored ratings as the ridge prior (rapm.chain's method); players new to it start at 0."""
    cur.execute("SELECT player_id, offense, defense FROM rapm_ratings WHERE season_id = %s", (previous_season(season_id),))
    prior = np.zeros(design.n)
    for player_id, offense, defense in cur.fetchall():
        i = design.index.get(player_id)
        if i is not None:
            prior[i] = float(offense)
            prior[design.n_players + i] = -float(defense)  # stored positive = good; the beta is xG allowed
    return prior


def store_ratings(cur, season_id, ev):
    cur.execute("DELETE FROM rapm_ratings WHERE season_id = %s", (season_id,))
    for player_id, r in ev.items():
        if r["hours"] > 0:
            cur.execute("INSERT INTO rapm_ratings (season_id, player_id, offense, defense, hours) VALUES (%s, %s, %s, %s, %s)",
                        (season_id, player_id, round(r["offense"], 4), round(r["defense"], 4), round(r["hours"], 3)))


def nightly(conn, season_id, today, get=rs._get, get_text=rs._get_text, pause=rs.PAUSE):
    """
    The daily step: store new games, fit this season's RAPM from them with
    last season's ratings as the prior, store those ratings (next season's
    prior), and return skater_war() for the season.
    """
    with conn.cursor() as cur:
        cur.execute(TABLES_SQL)
        stored, missing = store_games(cur, season_id, today, get, get_text, pause=pause)
    conn.commit()  # the fetched games are kept even if the fit below fails
    with conn.cursor() as cur:
        blobs = load_blobs(cur, season_id)
        extracts, skaters = [], set()
        for _, blob in blobs:  # first pass: the box lines, and who played 5v5 (the regression's columns)
            extract = json.loads(gzip.decompress(blob))
            for s in extract.pop("stints") or ():
                skaters.update(s["home"] + s["away"])
            extracts.append(extract)
        ev = {}
        if skaters:
            design = rapm.Design(skaters)
            sums, _ = rapm.build([season_id], design=design, loaded={season_id: StoredStints(blobs)})
            beta = rapm.solve(sums[0], design, rapm.CHAIN_LAMBDA, prior_beta(cur, season_id, design))
            ev = rapm.ratings(beta, design, sums[0])
            store_ratings(cur, season_id, ev)
    conn.commit()
    war.logger.info(f"WAR v2: {stored} new games ({missing} without a shift chart yet), "
                    f"{len(extracts)} this season, RAPM for {len(ev)} skaters")
    return skater_war(combine(extracts), ev, replacement=REPLACEMENT)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--backtest", action="store_true")
    parser.add_argument("--top", type=int, default=0)
    parser.add_argument("--season", type=int, default=20252026)
    args = parser.parse_args()
    if args.backtest:
        results, _ = backtest()
        for name, tests in results.items():
            print(name, tests)
    if args.top:
        players = skater_war(season_inputs(args.season), ev_ratings(args.season))
        for pid, p in sorted(players.items(), key=lambda kv: -kv[1]["war"])[: args.top]:
            parts = "  ".join(f"{LABELS[k]} {v:+5.1f}" for k, v in p["parts"].items() if k != "total")
            print(f"{p['name']:<22} {p['team']} {p['pos']} {p['gp']:3} GP  {p['war']:+5.2f} WAR   {parts}")


if __name__ == "__main__":
    main()
