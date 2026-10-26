"""
The time machine: one of a player's seasons replayed in another era's
scoring ("Gretzky's 1985-86 in today's game", "McDavid's 2022-23 in 1985").

  1. His goals and assists per game that season, times the target season's
     scoring over his season's (league goals per team-game, era.py): the
     same translation as the compare page's era adjustment.
  2. 10,000 simulated 82-game seasons at that rate. Each one first draws
     the rate's own uncertainty (RATE_SD: era translation isn't exact; ice
     time, linemates, and goaltending differ), then Poisson goals and
     assists, so the range covers both the model's doubt and a season's luck.
  3. The median and a likely range (10th to 90th percentile), plus a
     histogram of points for the page.

Seeded by player, season, and target, so a shared link always shows the
same numbers. For fun, and labeled that way: it can't know how a player
would really adapt to another era's rules, equipment, or travel.
"""

import math
import random

SIMS = 10_000
GAMES = 82
RATE_SD = 0.10
POISSON_NORMAL_ABOVE = 25  # a Poisson this large is a normal to within a goal


def _poisson(rng, lam):
    if lam <= 0:
        return 0
    if lam > POISSON_NORMAL_ABOVE:
        return max(0, round(rng.gauss(lam, math.sqrt(lam))))
    limit, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= limit:
            return k
        k += 1


def _pct(sorted_values, q):
    return sorted_values[min(len(sorted_values) - 1, int(q * len(sorted_values)))]


def simulate(goals_per_game, assists_per_game, seed, sims=SIMS, games=GAMES, rate_sd=RATE_SD):
    """{goals, assists, points: {median, low, high}, histogram: [(points from, seasons)]} over `games`-game seasons."""
    rng = random.Random(seed)
    goals, assists, points = [], [], []
    for _ in range(sims):
        m = max(0.0, rng.gauss(1.0, rate_sd))
        g = _poisson(rng, goals_per_game * m * games)
        a = _poisson(rng, assists_per_game * m * games)
        goals.append(g)
        assists.append(a)
        points.append(g + a)
    out = {}
    for name, values in (("goals", goals), ("assists", assists), ("points", points)):
        values.sort()
        out[name] = {"median": _pct(values, 0.5), "low": _pct(values, 0.1), "high": _pct(values, 0.9)}
    lo, hi = points[0], points[-1]
    width = max(1, math.ceil((hi - lo + 1) / 24))  # about two dozen bars
    bins = {}
    for p in points:
        start = lo + (p - lo) // width * width
        bins[start] = bins.get(start, 0) + 1
    out["histogram"] = [[start, bins[start]] for start in sorted(bins)]
    out["bin_width"] = width
    return out


def run(player, season_id, target_season_id, scoring):
    """
    The time machine for `player` (api.player_detail()'s data): his regular
    season `season_id` (or his best by points) replayed at `target_season_id`'s
    scoring. Raises ValueError for goalies, a season he didn't play, or a
    season missing from the scoring table.
    """
    if player.get("position_code") == "G":
        raise ValueError("The time machine is for skaters (goalies are coming).")
    seasons = [s for s in player.get("season_history") or []
               if s.get("season_type") == "regular_season" and s.get("games_played")]
    if not seasons:
        raise ValueError("No NHL regular seasons for this player.")
    season = (next((s for s in seasons if s["season_id"] == season_id), None) if season_id
              else max(seasons, key=lambda s: s.get("points") or 0))
    if not season:
        raise ValueError(f"He didn't play an NHL regular season in {season_id}.")
    source, target = scoring.get(str(season["season_id"])), scoring.get(str(target_season_id))
    if not source or not target:
        raise ValueError("No league scoring for one of those seasons.")
    gp = season["games_played"]
    factor = target / source
    goals_pg, assists_pg = (season.get("goals") or 0) / gp, (season.get("assists") or 0) / gp
    sim = simulate(goals_pg * factor, assists_pg * factor, seed=f"{player['player_id']}-{season['season_id']}-{target_season_id}")
    return {
        "player": {"id": player["player_id"], "name": f"{player['first_name']} {player['last_name']}",
                   "position": player.get("position_code"), "headshot": player.get("headshot_url")},
        "source": {"season_id": season["season_id"], "games_played": gp, "goals": season.get("goals"),
                   "assists": season.get("assists"), "points": season.get("points"), "scoring": source},
        "target": {"season_id": int(target_season_id), "scoring": target},
        "factor": round(factor, 3),
        "pace_82": {"goals": round(goals_pg * factor * GAMES), "assists": round(assists_pg * factor * GAMES),
                    "points": round((goals_pg + assists_pg) * factor * GAMES)},
        "seasons": [s["season_id"] for s in sorted(seasons, key=lambda s: s["season_id"])],
        **sim,
    }
