"""A narrow, read-only client for the NHL dashboard public API."""

import asyncio
from dataclasses import dataclass
from typing import Any

import httpx

from . import compact


class DashboardUnavailable(Exception):
    """The dashboard could not provide the requested context."""


@dataclass
class ContextBundle:
    facts: dict[str, Any]
    evidence: list[dict[str, str]]


class DashboardClient:
    def __init__(self, base_url: str, client: httpx.AsyncClient | None = None):
        self.base_url = base_url.rstrip("/")
        self.client = client

    async def _get(self, path: str) -> Any:
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                if self.client:
                    response = await self.client.get(path)
                else:
                    timeout = httpx.Timeout(25.0, connect=10.0)
                    async with httpx.AsyncClient(base_url=self.base_url, timeout=timeout) as client:
                        response = await client.get(path)
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as exc:
                last_error = exc
                if exc.response.status_code < 500:
                    break
            except (httpx.TimeoutException, httpx.NetworkError, ValueError) as exc:
                last_error = exc

            if attempt < 2:
                await asyncio.sleep(0.25 * (2**attempt))

        raise DashboardUnavailable("The NHL dashboard data is temporarily unavailable.") from last_error

    async def player_context(self, player_id: int) -> ContextBundle:
        player = await self._get(f"/players/{player_id}")
        return ContextBundle(
            facts={"player": compact.player_facts(player)},
            evidence=[{"label": "Player profile and season statistics", "endpoint": f"/players/{player_id}"}],
        )

    async def team_context(self, team_abbrev: str) -> ContextBundle:
        abbrev = team_abbrev.upper()
        standings, roster, playoff_odds = await asyncio.gather(
            self._get("/standings/latest"),
            self._get(f"/teams/{abbrev}/roster"),
            self._get("/playoff-odds"),
        )
        return ContextBundle(
            facts=compact.team_facts(abbrev, standings, roster, playoff_odds),
            evidence=[
                {"label": "Current standings", "endpoint": "/standings/latest"},
                {"label": "Current roster and season totals", "endpoint": f"/teams/{abbrev}/roster"},
                {"label": "Playoff simulation", "endpoint": "/playoff-odds"},
            ],
        )

    async def league_summary(self) -> ContextBundle:
        """
        The league page's context for the agent: just the playoff picture and
        dates (~150 tokens). The full standings, odds, and leaders (~3,300
        tokens) are one tool call away, and sending them with every request
        pushed a single question over Groq's per-minute token cap.
        """
        standings = await self._get("/standings/latest")
        return ContextBundle(
            facts=compact._clean({
                "standings_as_of": str(standings[0]["snapshot_date"]) if standings else None,
                "playoff_picture_if_season_ended_today": compact.playoff_picture(standings),
                "note": "Use tools for standings, playoff odds, leaders, schedules, players, and simulations.",
            }),
            evidence=[{"label": "Current standings", "endpoint": "/standings/latest"}],
        )

    async def game_context(self, game_id: int) -> ContextBundle:
        game = await self._get(f"/games/{game_id}/boxscore")
        return ContextBundle(
            facts={"game": compact.game_facts(game)},
            evidence=[{"label": "NHL game box score", "endpoint": f"/games/{game_id}/boxscore"}],
        )
