"""Read-only client for live NHL scores and gamecenter box scores."""

import calendar
import logging
import threading
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from typing import Any

import requests


NHL_API_BASE = "https://api-web.nhle.com/v1"

logger = logging.getLogger(__name__)


class NHLGamesUnavailable(Exception):
    """The NHL game feed could not be reached."""


# --- Response cache -------------------------------------------------------
#
# Design goal: the site shouldn't hammer the NHL API, or break when it's
# slow or down. Game responses are cached briefly (seconds for live games,
# an hour for finished ones); concurrent requests for the same thing share
# one upstream fetch; and if the NHL API fails, the last good copy (up to
# MAX_STALE_SECONDS old) is served instead of an error.

LIVE_TTL = 15            # live / pre-game box score
SCOREBOARD_LIVE_TTL = 20  # a day with live (or about-to-start) games
SCHEDULED_TTL = 60       # upcoming games: catch the switch to live quickly
FINAL_TTL = 3600         # finished games don't change
MAX_STALE_SECONDS = 6 * 3600
MAX_ENTRIES = 500

LIVE_STATES = {"LIVE", "CRIT", "PRE"}
FINAL_STATES = {"FINAL", "OFF"}


class _ResponseCache:
    def __init__(self, max_entries: int = MAX_ENTRIES):
        self.max_entries = max_entries
        self._entries: OrderedDict[str, tuple[float, float, Any]] = OrderedDict()  # key -> (fetched_at, ttl, value)
        self._lock = threading.Lock()
        self._key_locks: dict[str, threading.Lock] = {}

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
            self._key_locks.clear()

    def _fresh(self, key: str, now: float):
        entry = self._entries.get(key)
        if entry and now - entry[0] < entry[1]:
            self._entries.move_to_end(key)
            return entry
        return None

    def get(self, key: str, fetch, ttl_for) -> Any:
        """Return a cached value, fetching (once per key at a time) when stale."""
        with self._lock:
            entry = self._fresh(key, _now())
            if entry:
                return entry[2]
            key_lock = self._key_locks.setdefault(key, threading.Lock())

        with key_lock:  # concurrent callers for this key wait for one fetch
            with self._lock:
                entry = self._fresh(key, _now())
                if entry:
                    return entry[2]
            try:
                value = fetch()
            except NHLGamesUnavailable:
                with self._lock:
                    stale = self._entries.get(key)
                if stale and _now() - stale[0] < MAX_STALE_SECONDS:
                    logger.warning("NHL API unavailable; serving %ds-old cached %s", int(_now() - stale[0]), key)
                    return stale[2]
                raise
            with self._lock:
                self._entries[key] = (_now(), ttl_for(value), value)
                self._entries.move_to_end(key)
                while len(self._entries) > self.max_entries:
                    old_key, _ = self._entries.popitem(last=False)
                    self._key_locks.pop(old_key, None)
            return value


def _now() -> float:
    return time.monotonic()


_cache = _ResponseCache()


def _scoreboard_ttl(games: list[dict[str, Any]]) -> int:
    states = {g.get("gameState") for g in games}
    if states & LIVE_STATES:
        return SCOREBOARD_LIVE_TTL
    if games and states <= FINAL_STATES:
        return FINAL_TTL
    return SCHEDULED_TTL


def _boxscore_ttl(game: dict[str, Any]) -> int:
    state = game.get("gameState")
    if state in LIVE_STATES:
        return LIVE_TTL
    if state in FINAL_STATES:
        return FINAL_TTL
    return SCHEDULED_TTL


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
    """Return the NHL's score feed for the current day (cached)."""
    return _cache.get("score/now", lambda: _get("/score/now").get("games", []), _scoreboard_ttl)


def games_on_date(game_date: date) -> list[dict[str, Any]]:
    """
    Return scheduled, live, and final games for a calendar date, in the same
    shape as today_games() (scores, outcomes, logos, records), so the
    scoreboard renders any day the same way. Uses /score/{date}; the
    /schedule/{date} feed nests games under gameWeek, so reading "games"
    from it always came back empty.
    """
    path = f"/score/{game_date.isoformat()}"
    return _cache.get(path, lambda: _get(path).get("games", []), _scoreboard_ttl)


def _get_optional(path: str) -> dict[str, Any]:
    try:
        return _get(path)
    except NHLGamesUnavailable:
        return {}


def game_boxscore(game_id: int) -> dict[str, Any]:
    """One game's merged box score (cached; see _fetch_game_boxscore)."""
    return _cache.get(f"boxscore/{game_id}", lambda: _fetch_game_boxscore(game_id), _boxscore_ttl)


def _fetch_game_boxscore(game_id: int) -> dict[str, Any]:
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

