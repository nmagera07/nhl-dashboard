"""
Players beyond today's rosters: retired players, and anyone else who has
played in the NHL, straight from the NHL's own player search and profile
(landing) pages. Nothing is stored: a player's page is built on request and
cached in memory, since a retired player's numbers never change.

The page has the same shape as a rostered player's (api.player_detail), so
the site shows both the same way: bio, career totals, and season by season.
"""

import requests

SEARCH_URL = "https://search.d3.nhle.com/api/v1/search/player"
LANDING_URL = "https://api-web.nhle.com/v1/player/{player_id}/landing"
TIMEOUT = 10

STAT_KEYS = {  # NHL camelCase -> our snake_case (CareerTotalsStats / SeasonHistoryEntry)
    "gamesPlayed": "games_played", "goals": "goals", "assists": "assists", "points": "points",
    "plusMinus": "plus_minus", "pim": "pim", "shots": "shots", "shootingPctg": "shooting_pctg",
    "powerPlayGoals": "power_play_goals", "powerPlayPoints": "power_play_points",
    "shorthandedGoals": "shorthanded_goals", "shorthandedPoints": "shorthanded_points",
    "gameWinningGoals": "game_winning_goals", "otGoals": "ot_goals", "wins": "wins", "losses": "losses",
    "otLosses": "ot_losses", "goalsAgainstAvg": "goals_against_avg", "savePctg": "save_pctg", "shutouts": "shutouts",
}


class PlayerNotFound(Exception):
    pass


def _stats(row):
    return {ours: row.get(theirs) for theirs, ours in STAT_KEYS.items()}


def _text(value):
    return value.get("default") if isinstance(value, dict) else value


def search(query, limit=10, get=requests.get):
    """
    Players matching `query` who have played in the NHL, active or not:
    [{player_id, name, position_code, active, last_team_abbrev, last_season_id}].
    The search also knows draft picks who never played; those are left out.
    """
    response = get(SEARCH_URL, params={"culture": "en-us", "limit": 40, "q": query}, timeout=TIMEOUT)
    response.raise_for_status()
    out = []
    for p in response.json():
        if not p.get("lastSeasonId"):
            continue
        out.append({"player_id": int(p["playerId"]), "name": p.get("name"), "position_code": p.get("positionCode"),
                    "active": bool(p.get("active")), "last_team_abbrev": p.get("lastTeamAbbrev"),
                    "last_season_id": int(p["lastSeasonId"])})
    # Most recent first, so the familiar names come up before the 1930s ones.
    out.sort(key=lambda p: (not p["active"], -p["last_season_id"]))
    return out[:limit]


def fetch_landing(player_id, get=requests.get):
    response = get(LANDING_URL.format(player_id=player_id), timeout=TIMEOUT)
    if response.status_code == 404:
        raise PlayerNotFound(player_id)
    response.raise_for_status()
    return response.json()


def _parse_time_on_ice_to_seconds(time_on_ice):
    if not time_on_ice:
        return 0
    minutes, seconds = time_on_ice.split(":")
    return int(minutes) * 60 + int(seconds)


def _combine_season_entries(entries):
    """
    Combine multiple raw seasonTotals entries for the same (season,
    gameTypeId) -- i.e. a mid-season trade, where the player has one
    entry per team -- into the single row stored in player_season_history.
    Counting stats are summed (None treated as 0 so a partial None from a
    skater-only or goalie-only entry doesn't poison the sum). shooting_pctg,
    save_pctg, and goals_against_avg are NOT averaged across entries --
    they're recomputed from the summed underlying counts, since averaging
    per-stint percentages would misweight a short stint against a long one.
    """
    counting_int_keys = (
        "gamesPlayed",
        "goals",
        "assists",
        "points",
        "plusMinus",
        "pim",
        "shots",
        "powerPlayGoals",
        "powerPlayPoints",
        "shorthandedGoals",
        "shorthandedPoints",
        "gameWinningGoals",
        "otGoals",
        "wins",
        "losses",
        "otLosses",
        "shutouts",
    )
    combined = {key: sum(e.get(key) or 0 for e in entries) for key in counting_int_keys}

    total_shots = combined["shots"]
    combined["shootingPctg"] = (combined["goals"] / total_shots) if total_shots > 0 else None

    total_goals_against = sum(e.get("goalsAgainst") or 0 for e in entries)
    total_shots_against = sum(e.get("shotsAgainst") or 0 for e in entries)
    total_seconds = sum(_parse_time_on_ice_to_seconds(e.get("timeOnIce")) for e in entries)

    combined["savePctg"] = (
        (total_shots_against - total_goals_against) / total_shots_against
        if total_shots_against > 0
        else None
    )
    combined["goalsAgainstAvg"] = (
        total_goals_against * 3600 / total_seconds if total_seconds > 0 else None
    )

    return combined


def season_history(landing):
    """NHL seasons only (not junior or international), one row per season and type, trades combined."""
    groups = {}
    for entry in landing.get("seasonTotals", []):
        if entry.get("leagueAbbrev") != "NHL" or entry.get("gameTypeId") not in (2, 3):
            continue
        season_type = "regular_season" if entry["gameTypeId"] == 2 else "playoffs"
        groups.setdefault((entry["season"], season_type), []).append(entry)
    rows = []
    for (season_id, season_type), group in groups.items():
        combined = group[0] if len(group) == 1 else _combine_season_entries(group)
        rows.append({"season_id": season_id, "season_type": season_type, **_stats(combined)})
    rows.sort(key=lambda r: r["season_id"], reverse=True)
    return rows


def player_detail(landing):
    """api.player_detail()'s shape from an NHL profile, for a player not on a current roster."""
    history = season_history(landing)
    if not history:
        raise PlayerNotFound(landing.get("playerId"))  # drafted, never played
    career = landing.get("careerTotals") or {}
    last_nhl = max((e for e in landing.get("seasonTotals", []) if e.get("leagueAbbrev") == "NHL"),
                   key=lambda e: (e["season"], e.get("sequence", 0)))
    return {
        "player_id": landing["playerId"],
        "first_name": _text(landing.get("firstName")), "last_name": _text(landing.get("lastName")),
        "position_code": landing.get("position"), "sweater_number": landing.get("sweaterNumber"),
        "shoots_catches": landing.get("shootsCatches"), "height_in_inches": landing.get("heightInInches"),
        "weight_in_pounds": landing.get("weightInPounds"), "birth_date": landing.get("birthDate"),
        "birth_city": _text(landing.get("birthCity")), "birth_country": landing.get("birthCountry"),
        "headshot_url": landing.get("headshot"),
        "team_abbrev": None, "team_name": None, "team_logo_url": None,
        "status": "active" if landing.get("isActive") else "retired",
        "in_hall_of_fame": bool(landing.get("inHHOF")),
        "last_season_id": last_nhl["season"], "last_team_name": _text(last_nhl.get("teamName")),
        "season_stats": [], "advanced_stats": None, "advanced_percentiles": None, "goalie_advanced_stats": None,
        "war": None,
        "career_totals": {"regular_season": _stats(career["regularSeason"]) if career.get("regularSeason") else None,
                          "playoffs": _stats(career["playoffs"]) if career.get("playoffs") else None},
        "season_history": history,
    }
