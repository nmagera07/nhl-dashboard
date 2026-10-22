"""DashboardClient: one shared connection, and a cache for once-a-day data."""

import httpx
import pytest

from app import dashboard as dash
from app.dashboard import DashboardClient


def _client(seen):
    def handler(request):
        seen.append(request.url.path)
        return httpx.Response(200, json={"path": request.url.path, "n": len(seen)})
    return httpx.AsyncClient(base_url="https://dashboard.test", transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
class TestCache:
    async def test_daily_data_is_fetched_once_until_it_expires(self, monkeypatch):
        seen = []
        async with _client(seen) as http:
            client = DashboardClient("https://dashboard.test", http)
            first = await client._get("/standings/latest")
            second = await client._get("/standings/latest")
            assert first == second and seen == ["/standings/latest"]

            later = dash.time.monotonic() + dash.CACHE_SECONDS + 1
            monkeypatch.setattr(dash.time, "monotonic", lambda: later)
            await client._get("/standings/latest")
            assert seen == ["/standings/latest", "/standings/latest"]

    async def test_live_data_and_simulations_are_never_cached(self):
        seen = []
        async with _client(seen) as http:
            client = DashboardClient("https://dashboard.test", http)
            for path in ("/teams/PIT/schedule", "/games/2026020001/boxscore", "/season-sim/scenario?team=PIT&games=4&wins=4"):
                await client._get(path)
                await client._get(path)
        assert len(seen) == 6

    async def test_what_counts_as_daily(self):
        for path in ("/playoff-odds", "/playoff-odds/history", "/playoff-odds/why", "/season-sim", "/players/leaders",
                     "/players/8471675", "/teams/PIT/roster", "/predictions/track-record", "/digest/latest"):
            assert dash.CACHEABLE.match(path), path
        for path in ("/teams/PIT/schedule", "/season-sim/roster-change?move=1:NONE", "/games/date/2026-10-11"):
            assert not dash.CACHEABLE.match(path), path

    async def test_without_an_injected_client_it_reuses_one(self):
        client = DashboardClient("https://dashboard.test")
        assert client._http() is client._http()
        await client.aclose()


@pytest.mark.asyncio
async def test_warm_never_raises_when_the_api_is_down():
    def down(request):
        raise httpx.ConnectError("down")

    client = DashboardClient("https://api.test", client=httpx.AsyncClient(transport=httpx.MockTransport(down),
                                                                            base_url="https://api.test"))
    await client.warm()
