"""Read-only client for live NHL scores and gamecenter box scores."""

import calendar
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from typing import Any

import requests


NHL_API_BASE = "https://api-web.nhle.com/v1"


class NHLGamesUnavailable(Exception):
    """The NHL game feed could not be reached."""


def _get(path: str) -> dict[str, Any]:
    try:
        response = requests.get(f"{NHL_API_BASE}{path}", timeout=15)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("unexpected NHL API response")
        return payload
    except (requests.RequestException, ValueError) as exc:
        raise NHLGamesUnavailable("The NHL live game feed is temporarily unavailable.") from exc


def today_games() -> list[dict[str, Any]]:
    """Return the NHL's score feed for the current day."""
    return _get("/score/now").get("games", [])


def games_on_date(game_date: date) -> list[dict[str, Any]]:
    """
    Return scheduled, live, and final games for a calendar date, in the same
    shape as today_games() (scores, outcomes, logos, records), so the
    scoreboard renders any day the same way. Uses /score/{date}; the
    /schedule/{date} feed nests games under gameWeek, so reading "games"
    from it always came back empty.
    """
    return _get(f"/score/{game_date.isoformat()}").get("games", [])


def _get_optional(path: str) -> dict[str, Any]:
    try:
        return _get(path)
    except NHLGamesUnavailable:
        return {}


def game_boxscore(game_id: int) -> dict[str, Any]:
    """
    Return one game's full box score.

    The NHL splits a game across three gamecenter endpoints: /boxscore has
    the teams, score, and per-player stats; /landing has the scoring
    summary, three stars, and penalties; /right-rail has the period-by-
    period linescore, shots by period, and team stats. They're fetched in
    parallel and merged. Only /boxscore is required -- if either of the
    others is down (or a scheduled game has no summary yet), the page
    still gets the core box score.
    """
    with ThreadPoolExecutor(max_workers=3) as pool:
        boxscore = pool.submit(_get, f"/gamecenter/{game_id}/boxscore")
        landing = pool.submit(_get_optional, f"/gamecenter/{game_id}/landing")
        right_rail = pool.submit(_get_optional, f"/gamecenter/{game_id}/right-rail")
        game = boxscore.result()
        landing_data = landing.result()
        right_rail_data = right_rail.result()

    return {
        **game,
        "summary": landing_data.get("summary") or {},
        "linescore": right_rail_data.get("linescore") or {},
        "shotsByPeriod": right_rail_data.get("shotsByPeriod") or [],
        "teamGameStats": right_rail_data.get("teamGameStats") or [],
    }


# Month calendars change rarely (a postponement at most), so they're cached
# in-process: past months for a day, the current/future ones for an hour.
_CALENDAR_CACHE: dict[tuple[int, int], tuple[float, dict[str, Any]]] = {}
_CALENDAR_LOCK = threading.Lock()
_PAST_MONTH_TTL = 24 * 3600
_CURRENT_MONTH_TTL = 3600


def _week_starts(year: int, month: int) -> list[date]:
    """Dates 7 days apart covering the whole month (/schedule returns a week)."""
    first = date(year, month, 1)
    last = date(year, month, calendar.monthrange(year, month)[1])
    starts, d = [], first
    while d <= last:
        starts.append(d)
        d += timedelta(days=7)
    return starts


def month_calendar(year: int, month: int, today: date | None = None) -> dict[str, Any]:
    """
    Season bounds plus the number of games on each day of one month, for the
    Scores page calendar. Season = regular season start through playoff end;
    days outside it, or with no games, are left out of "days".
    """
    today = today or date.today()
    key = (year, month)
    with _CALENDAR_LOCK:
        cached = _CALENDAR_CACHE.get(key)
        if cached and cached[0] > time.time():
            return cached[1]

    starts = _week_starts(year, month)
    with ThreadPoolExecutor(max_workers=len(starts)) as pool:
        weeks = list(pool.map(lambda d: _get(f"/schedule/{d.isoformat()}"), starts))

    first = weeks[0]
    season_start = first.get("regularSeasonStartDate")
    season_end = first.get("playoffEndDate") or first.get("regularSeasonEndDate")
    prefix = f"{year:04d}-{month:02d}-"
    days: dict[str, int] = {}
    for week in weeks:
        for day in week.get("gameWeek", []):
            d, count = day.get("date", ""), day.get("numberOfGames") or 0
            in_season = bool(season_start and season_end and season_start <= d <= season_end)
            if d.startswith(prefix) and count > 0 and in_season:
                days[d] = count

    result = {
        "season_start": season_start,
        "season_end": season_end,
        "days": [{"date": d, "games": n} for d, n in sorted(days.items())],
    }
    is_past = (year, month) < (today.year, today.month)
    ttl = _PAST_MONTH_TTL if is_past else _CURRENT_MONTH_TTL
    with _CALENDAR_LOCK:
        _CALENDAR_CACHE[key] = (time.time() + ttl, result)
    return result

