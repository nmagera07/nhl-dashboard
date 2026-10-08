"""
Compact, question-shaped summaries of dashboard data for the model.

The raw API responses are far too big to send whole (the league context
alone was ~1.3M characters, so the old blind truncation kept ~2% of it and
dropped the player leaders and playoff odds entirely). These functions
keep what hockey questions need -- records, ranks, odds, leaders, box score
events -- and drop logos, ids, timestamps, and empty fields.
"""

from typing import Any, Iterable

TOP_POINTS = 15
TOP_GOALS = 10
TOP_GOALIES = 8
RECENT_SEASONS = 5


def _clean(d: dict[str, Any]) -> dict[str, Any]:
    """Drop None/empty values so the model doesn't read noise."""
    return {k: v for k, v in d.items() if v not in (None, "", [], {})}


def _record(w, l, ot) -> str | None:
    return None if w is None else f"{w}-{l}-{ot}"


def _pct(value, digits=1) -> float | None:
    return None if value is None else round(float(value) * 100, digits)


def _num(value, digits=2) -> float | None:
    return None if value is None else round(float(value), digits)


def _name(p: dict[str, Any]) -> str:
    return f"{p.get('first_name', '')} {p.get('last_name', '')}".strip()


# --- standings --------------------------------------------------------------

def standing_row(row: dict[str, Any], playoff_pct: float | None = None) -> dict[str, Any]:
    streak = f"{row['streak_code']}{row['streak_count']}" if row.get("streak_code") else None
    return _clean({
        "team": row.get("team_abbrev"),
        "name": row.get("team_name"),
        "division": row.get("division"),
        "conference": row.get("conference"),
        "gp": row.get("games_played"),
        "record": _record(row.get("wins"), row.get("losses"), row.get("ot_losses")),
        "points": row.get("points"),
        "point_pct": _pct(row.get("point_pctg")),
        "goals_for": row.get("goal_for"),
        "goals_against": row.get("goal_against"),
        "goal_diff": row.get("goal_differential"),
        "last_10": _record(row.get("l10_wins"), row.get("l10_losses"), row.get("l10_ot_losses")),
        "streak": streak,
        "home": None if row.get("home_wins") is None else f"{row['home_wins']}-{row['home_losses']}",
        "road": None if row.get("road_wins") is None else f"{row['road_wins']}-{row['road_losses']}",
        "division_rank": row.get("division_sequence"),
        "conference_rank": row.get("conference_sequence"),
        "league_rank": row.get("league_sequence"),
        "wildcard_rank": row.get("wildcard_sequence") or None,  # 0 means "not in a wild-card race"
        "playoff_odds_pct": _pct(playoff_pct),
        "xgoals_for_pct": _pct(row.get("xgoals_for_pct")),
        "pdo": _num(row.get("pdo"), 1),
    })


def odds_by_team(standings: list[dict], playoff_odds: list[dict]) -> tuple[dict[str, float], str | None]:
    """Playoff odds keyed by team, only if they're from the standings' season."""
    season = standings[0].get("season_id") if standings else None
    current = [o for o in playoff_odds if o.get("season_id") == season]
    as_of = str(current[0]["as_of_date"]) if current else None
    return {o["team_abbrev"]: o["playoff_pct"] for o in current}, as_of


# --- players ----------------------------------------------------------------

def skater_line(p: dict[str, Any]) -> dict[str, Any]:
    return _clean({
        "name": _name(p),
        "team": p.get("team_abbrev"),
        "pos": p.get("position_code"),
        "gp": p.get("games_played"),
        "g": p.get("goals"),
        "a": p.get("assists"),
        "pts": p.get("points"),
        "plus_minus": p.get("plus_minus"),
        "shots": p.get("shots"),
        "pp_pts": p.get("power_play_points"),
        "pim": p.get("pim"),
    })


def goalie_line(p: dict[str, Any]) -> dict[str, Any]:
    return _clean({
        "name": _name(p),
        "team": p.get("team_abbrev"),
        "gp": p.get("games_played"),
        "record": _record(p.get("wins"), p.get("losses"), p.get("ot_losses")),
        "gaa": _num(p.get("goals_against_avg")),
        "save_pct": _num(p.get("save_pctg"), 3),
        "shutouts": p.get("shutouts"),
    })


def _top(players: Iterable[dict], key: str, n: int, *tiebreak: str) -> list[dict]:
    return sorted(
        (p for p in players if p.get(key) is not None),
        key=lambda p: tuple(-(p.get(k) or 0) for k in (key, *tiebreak)),
    )[:n]


def leaders(players: list[dict]) -> dict[str, list[dict]]:
    skaters = [p for p in players if p.get("position_code") != "G"]
    goalies = [p for p in players if p.get("position_code") == "G" and (p.get("games_played") or 0) > 0]
    return {
        "points": [skater_line(p) for p in _top(skaters, "points", TOP_POINTS, "goals")],
        "goals": [skater_line(p) for p in _top(skaters, "goals", TOP_GOALS, "points")],
        "goalie_wins": [goalie_line(p) for p in _top(goalies, "wins", TOP_GOALIES, "save_pctg")],
    }


# --- contexts ---------------------------------------------------------------

def league_facts(standings: list[dict], players: list[dict], playoff_odds: list[dict]) -> dict[str, Any]:
    odds, as_of = odds_by_team(standings, playoff_odds)
    rows = sorted(standings, key=lambda r: r.get("league_sequence") or 99)
    return _clean({
        "standings_as_of": str(standings[0]["snapshot_date"]) if standings else None,
        "playoff_odds_as_of": as_of,
        "standings": [standing_row(r, odds.get(r.get("team_abbrev"))) for r in rows],
        "leaders": leaders(players),
    })


def team_facts(abbrev: str, standings: list[dict], roster: list[dict], playoff_odds: list[dict]) -> dict[str, Any]:
    odds, as_of = odds_by_team(standings, playoff_odds)
    row = next((r for r in standings if r.get("team_abbrev") == abbrev), None)
    skaters = sorted((p for p in roster if p.get("position_code") != "G"), key=lambda p: -(p.get("points") or 0))
    goalies = [p for p in roster if p.get("position_code") == "G"]
    return _clean({
        "team": abbrev,
        "standing": standing_row(row, odds.get(abbrev)) if row else None,
        "playoff_odds_as_of": as_of,
        "skaters": [{k: v for k, v in skater_line(p).items() if k != "team"} for p in skaters],
        "goalies": [{k: v for k, v in goalie_line(p).items() if k != "team"} for p in goalies],
    })


def _season_label(season_id) -> str | None:
    s = str(season_id or "")
    return f"{s[:4]}-{s[6:]}" if len(s) == 8 else None


def player_facts(player: dict[str, Any]) -> dict[str, Any]:
    is_goalie = player.get("position_code") == "G"
    line = goalie_line if is_goalie else skater_line

    def stats(d):
        return {k: v for k, v in line(d).items() if k not in ("name", "team")}

    season = (player.get("season_stats") or [None])[0]
    history = player.get("season_history") or []
    regular = [h for h in history if h.get("season_type") == "regular_season"][:RECENT_SEASONS]
    playoffs = [h for h in history if h.get("season_type") == "playoffs"][:3]
    career = player.get("career_totals") or {}
    advanced = player.get("advanced_stats") or {}
    inches = player.get("height_in_inches")

    return _clean({
        "name": _name(player),
        "team": player.get("team_name") or player.get("team_abbrev"),
        "number": player.get("sweater_number"),
        "position": player.get("position_code"),
        "shoots_catches": player.get("shoots_catches"),
        "height": f"{inches // 12}'{inches % 12}\"" if inches else None,
        "weight_lbs": player.get("weight_in_pounds"),
        "birth_date": player.get("birth_date"),
        "birthplace": ", ".join(filter(None, [player.get("birth_city"), player.get("birth_country")])) or None,
        "this_season": _clean({"season": _season_label(season.get("season_id")), **stats(season)}) if season else None,
        "advanced_5v5": _clean({
            "corsi_for_pct": _pct(advanced.get("corsi_for_pct")),
            "xgoals_for_pct": _pct(advanced.get("xgoals_for_pct")),
            "individual_xgoals": _num(advanced.get("individual_xgoals")),
            "pdo": _num(advanced.get("pdo"), 1),
        }) if advanced else None,
        "career_regular_season": stats(career["regular_season"]) if career.get("regular_season") else None,
        "career_playoffs": stats(career["playoffs"]) if career.get("playoffs") else None,
        "recent_seasons": [_clean({"season": _season_label(h.get("season_id")), **stats(h)}) for h in regular],
        "recent_playoffs": [_clean({"season": _season_label(h.get("season_id")), **stats(h)}) for h in playoffs],
    })


def _period(pd: dict[str, Any] | None) -> str:
    if not pd:
        return ""
    if pd.get("periodType") in ("OT", "SO"):
        return pd["periodType"]
    return f"P{pd.get('number')}"


def _goal(goal: dict[str, Any], period: str, home_abbrev: str) -> str:
    team = goal.get("teamAbbrev")
    team = team.get("default") if isinstance(team, dict) else team
    scorer = (goal.get("name") or {}).get("default", "")
    tally = f" ({goal['goalsToDate']})" if goal.get("goalsToDate") is not None else ""
    tags = [t for t in (
        {"pp": "power play", "sh": "shorthanded"}.get(goal.get("strength")),
        {"empty-net": "empty net", "penalty-shot": "penalty shot"}.get(goal.get("goalModifier")),
    ) if t]
    assists = ", ".join((a.get("name") or {}).get("default", "") for a in goal.get("assists") or [])
    score = ""
    if goal.get("awayScore") is not None:
        score = f" -> {goal['awayScore']}-{goal['homeScore']} (away-home)"
    return (
        f"{period} {goal.get('timeInPeriod', '')} {team}: {scorer}{tally}"
        f"{' [' + ', '.join(tags) + ']' if tags else ''}"
        f"{', assists: ' + assists if assists else ', unassisted'}{score}"
    )


def game_facts(game: dict[str, Any]) -> dict[str, Any]:
    away, home = game.get("awayTeam") or {}, game.get("homeTeam") or {}

    def team(t):
        name = " ".join(filter(None, [(t.get("placeName") or {}).get("default"), (t.get("commonName") or {}).get("default")]))
        return _clean({"abbrev": t.get("abbrev"), "name": name or None, "score": t.get("score"), "shots": t.get("sog")})

    def by_period(entries):
        return [_clean({"period": _period(p.get("periodDescriptor")), "away": p.get("away"), "home": p.get("home")}) for p in entries or []]

    def players(side):
        stats = (game.get("playerByGameStats") or {}).get(side) or {}
        skaters = (stats.get("forwards") or []) + (stats.get("defense") or [])
        skaters = sorted(skaters, key=lambda p: (-(p.get("points") or 0), -(p.get("sog") or 0)))
        return _clean({
            "skaters": [_clean({
                "name": (p.get("name") or {}).get("default"), "pos": p.get("position"),
                "g": p.get("goals"), "a": p.get("assists"), "pts": p.get("points"),
                "plus_minus": p.get("plusMinus"), "shots": p.get("sog"), "hits": p.get("hits"), "toi": p.get("toi"),
            }) for p in skaters],
            "goalies": [_clean({
                "name": (g.get("name") or {}).get("default"), "shots_against": g.get("shotsAgainst"),
                "saves": g.get("saves"), "goals_against": g.get("goalsAgainst"), "toi": g.get("toi"),
            }) for g in stats.get("goalies") or [] if g.get("toi") not in (None, "00:00")],
        })

    summary = game.get("summary") or {}
    scoring = [
        _goal(goal, _period(period.get("periodDescriptor")), home.get("abbrev"))
        for period in summary.get("scoring") or []
        for goal in period.get("goals") or []
    ]
    clock = game.get("clock") or {}
    return _clean({
        "date": game.get("gameDate"),
        "venue": (game.get("venue") or {}).get("default"),
        "state": game.get("gameState"),
        "current_period": _period(game.get("periodDescriptor")) if game.get("gameState") in ("LIVE", "CRIT") else None,
        "time_remaining": clock.get("timeRemaining") if game.get("gameState") in ("LIVE", "CRIT") else None,
        "ended_in": (game.get("gameOutcome") or {}).get("lastPeriodType"),
        "away": team(away),
        "home": team(home),
        "goals_by_period": by_period((game.get("linescore") or {}).get("byPeriod")),
        "shots_by_period": by_period(game.get("shotsByPeriod")),
        "scoring": scoring,
        "three_stars": [
            _clean({"star": s.get("star"), "name": (s.get("name") or {}).get("default"), "team": s.get("teamAbbrev"),
                    "g": s.get("goals"), "a": s.get("assists")})
            for s in summary.get("threeStars") or []
        ],
        "team_stats": [
            {"stat": s.get("category"), "away": s.get("awayValue"), "home": s.get("homeValue")}
            for s in game.get("teamGameStats") or []
        ],
        "away_players": players("awayTeam"),
        "home_players": players("homeTeam"),
    })
