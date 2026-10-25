"""
The numbers on a "X vs Y" share card (og_image.render_compare and the
preview text): the compare page's headline rows for two players, from
api.player_detail()'s data, with the era adjustment done the same way as
the site (frontend utils/compare.js eraAdjust; era.py has the scoring).
"""


import math


def _round(x):
    """Halves round up, like the site's Math.round (Python's round() goes to even: 126.5 -> 126)."""
    return math.floor(x + 0.5)


def _per_game(total, games):
    return round(total / games, 2) if total is not None and games else None


def era_points_per_game(player, scoring, reference):
    """Career regular-season points per game with each season rescaled to `reference` scoring."""
    games = points = 0
    for s in player.get("season_history") or []:
        if s.get("season_type") != "regular_season" or s.get("games_played") is None:
            continue
        league = scoring.get(str(s["season_id"]))
        f = reference / league if league else 1.0
        games += s["games_played"]
        points += _round((s.get("goals") or 0) * f) + _round((s.get("assists") or 0) * f)
    return _per_game(points, games)


def summary(player, era):
    """Who he is and the numbers the card compares: [(label, value, shown, higher is better)]."""
    rs = (player.get("career_totals") or {}).get("regular_season") or {}
    goalie = player.get("position_code") == "G"
    seasons = [s for s in player.get("season_history") or [] if s.get("season_type") == "regular_season"]
    key = "wins" if goalie else "points"
    best = max((s for s in seasons if s.get(key) is not None), key=lambda s: s[key], default=None)
    years = sorted({s["season_id"] for s in seasons})
    if not years:
        span = ""
    elif player.get("team_abbrev"):  # still playing
        span = f"since {str(years[0])[:4]}"
    else:
        span = f"{str(years[0])[:4]}-{str(years[-1])[6:]}"
    who = player.get("team_abbrev") or ("Hall of Fame" if player.get("in_hall_of_fame") else "Retired")
    out = {"name": f"{player['first_name']} {player['last_name']}", "last": player["last_name"],
           "headshot": player.get("headshot_url"), "subtitle": f"{who} · {span}" if span else who, "rows": []}
    if goalie:
        out["rows"] = [("Wins", rs.get("wins"), str(rs.get("wins") or "—"), True),
                       ("Save %", rs.get("save_pctg"), f"{rs['save_pctg']:.3f}".lstrip("0") if rs.get("save_pctg") else "—", True),
                       ("Goals against avg", rs.get("goals_against_avg"), f"{rs['goals_against_avg']:.2f}" if rs.get("goals_against_avg") else "—", False),
                       ("Shutouts", rs.get("shutouts"), str(rs.get("shutouts") or "—"), True)]
        return out
    ppg = _per_game(rs.get("points"), rs.get("games_played"))
    adj = era_points_per_game(player, era["seasons"], era["reference"]) if era else None
    out["rows"] = [("Points per game", ppg, f"{ppg:.2f}" if ppg is not None else "—", True),
                   ("Era-adjusted pts/game", adj, f"{adj:.2f}" if adj is not None else "—", True),
                   ("Career points", rs.get("points"), str(rs.get("points") or "—"), True),
                   ("Best season (points)", best["points"] if best else None,
                    f"{best['points']} in {str(best['season_id'])[2:4]}-{str(best['season_id'])[6:]}" if best else "—", True)]
    return out
