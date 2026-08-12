"""Read-only client for live NHL scores and gamecenter box scores."""

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


def game_boxscore(game_id: int) -> dict[str, Any]:
    """Return the NHL gamecenter box score for one game."""
    return _get(f"/gamecenter/{game_id}/boxscore")
