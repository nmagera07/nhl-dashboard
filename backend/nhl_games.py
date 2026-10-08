"""Read-only client for live NHL scores and gamecenter box scores."""

from concurrent.futures import ThreadPoolExecutor
from datetime import date
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
    """Return scheduled, live, and final games for a calendar date."""
    return _get(f"/schedule/{game_date.isoformat()}").get("games", [])


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
