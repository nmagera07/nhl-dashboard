"""Tests for the in-memory TTL response cache (daily_cache.py) and its wiring in api.py."""

import asyncio
from datetime import datetime

import pytest

import api
from daily_cache import TTLCache


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


TEAM = {"team_abbrev": "PIT", "team_name": "Pittsburgh Penguins", "division": "Metropolitan",
        "conference": "Eastern", "logo_url": "https://x/pit.svg"}


def _team_queries(db_router):
    return [c for c in db_router.calls if "from teams order by" in " ".join(c[0].split()).lower()]


class TestTTLCacheUnit:
    def test_hit_skips_compute(self):
        cache, calls = TTLCache(), []
        compute = lambda: calls.append(1) or "v"
        assert cache.get_or_compute("k", compute) == "v"
        assert cache.get_or_compute("k", compute) == "v"
        assert len(calls) == 1

    def test_ttl_expires(self):
        clock = FakeClock()
        cache, calls = TTLCache(ttl_seconds=600, clock=clock), []
        compute = lambda: calls.append(1) or len(calls)
        assert cache.get_or_compute("k", compute) == 1
        clock.now += 599
        assert cache.get_or_compute("k", compute) == 1
        clock.now += 2
        assert cache.get_or_compute("k", compute) == 2

    def test_size_bounded_lru(self):
        cache = TTLCache(max_entries=2)
        for k in "abc":
            cache.get_or_compute(k, lambda k=k: k)
        assert len(cache) == 2
        calls = []
        cache.get_or_compute("a", lambda: calls.append(1) or "a")
        assert calls == [1]  # "a" was evicted

    def test_exceptions_are_not_cached(self):
        cache, calls = TTLCache(), []

        def boom():
            calls.append(1)
            raise RuntimeError("db down")

        for _ in range(2):
            with pytest.raises(RuntimeError):
                cache.get_or_compute("k", boom)
        assert len(calls) == 2 and len(cache) == 0

    def test_disabled_always_computes(self):
        cache, calls = TTLCache(enabled=False), []
        for _ in range(3):
            cache.get_or_compute("k", lambda: calls.append(1))
        assert len(calls) == 3 and len(cache) == 0

    def test_env_flag_disables(self, monkeypatch):
        import importlib
        import daily_cache

        monkeypatch.setenv("DAILY_CACHE_DISABLED", "1")
        try:
            assert importlib.reload(daily_cache).cache.enabled is False
        finally:
            monkeypatch.delenv("DAILY_CACHE_DISABLED")
            importlib.reload(daily_cache)


class TestEndpointCaching:
    def test_cache_hit_skips_the_db(self, client, db_router):
        db_router.when("FROM teams ORDER BY", [TEAM])
        first = client.get("/teams")
        second = client.get("/teams")
        assert first.status_code == second.status_code == 200
        assert first.json() == second.json()
        assert len(_team_queries(db_router)) == 1

    def test_response_headers_unchanged_on_hit(self, client, db_router):
        db_router.when("FROM teams ORDER BY", [TEAM])
        a, b = client.get("/teams"), client.get("/teams")
        assert a.headers.get("cache-control") == b.headers.get("cache-control")
        assert a.headers.get("content-type") == b.headers.get("content-type")

    def test_different_query_strings_get_separate_entries(self, client, db_router):
        db_router.when("FROM players p", [])
        client.get("/players/leaders")
        client.get("/players/leaders?view=table")
        client.get("/players/leaders?view=table")
        client.get("/players/leaders")
        leader_calls = [c for c in db_router.calls if "from players p" in " ".join(c[0].split()).lower()]
        assert len(leader_calls) == 2

    def test_standings_sort_params_are_separate_entries(self, client, db_router):
        db_router.when("FROM standings_snapshots s", [])
        client.get("/standings/latest")
        client.get("/standings/latest?sort_by=points&sort_dir=asc")
        client.get("/standings/latest")
        assert len(db_router.calls) == 2

    def test_invalidation_clears_entries(self, client, db_router):
        db_router.when("FROM teams ORDER BY", [TEAM])
        client.get("/teams")
        api.daily_cache.clear()
        client.get("/teams")
        assert len(_team_queries(db_router)) == 2

    def test_disabled_flag_hits_the_db_every_time(self, client, db_router, monkeypatch):
        monkeypatch.setattr(api.daily_cache, "enabled", False)
        db_router.when("FROM teams ORDER BY", [TEAM])
        client.get("/teams")
        client.get("/teams")
        assert len(_team_queries(db_router)) == 2

    def test_404_is_not_cached(self, client, db_router):
        db_router.when("FROM daily_digest", None)
        assert client.get("/digest/latest").status_code == 404
        assert client.get("/digest/latest").status_code == 404
        assert len(db_router.calls) == 2


class TestFreshnessLoopInvalidation:
    def test_new_ingest_clears_the_cache(self, monkeypatch, db_router):
        from tests.conftest import FakeConnection

        stamps = iter([datetime(2026, 10, 12, 6, 0), datetime(2026, 10, 12, 6, 0), datetime(2026, 10, 13, 6, 0)])
        db_router.when("MAX(created_at)", lambda params: {"last_updated": next(stamps)})
        monkeypatch.setattr(api, "get_connection", lambda: FakeConnection(db_router))
        cleared = []
        monkeypatch.setattr(api.daily_cache, "clear", lambda: cleared.append(1))

        sleeps = []

        async def fake_sleep(_):
            sleeps.append(1)
            if len(sleeps) >= 3:
                raise asyncio.CancelledError

        monkeypatch.setattr(api.asyncio, "sleep", fake_sleep)
        with pytest.raises(asyncio.CancelledError):
            asyncio.run(api.check_ingestion_freshness_loop())
        # first read just records the stamp, second is unchanged, third is new
        assert cleared == [1]


class TestDecoratorSpecifics:
    def test_a_built_response_is_rebuilt_per_request_not_shared(self, client, db_router, player_bio_row):
        rows = [dict(player_bio_row, team_name="Colorado Avalanche", team_logo_url=None, games_played=5, points=7)]
        db_router.when("t.logo_url as team_logo_url", rows)

        first = client.get("/players/leaders?view=table")
        calls_after_first = len(db_router.calls)
        second = client.get("/players/leaders?view=table")

        assert first.status_code == second.status_code == 200
        assert first.json() == second.json() and first.json()[0]["points"] == 7
        assert len(db_router.calls) == calls_after_first  # served from the cache
        assert second.headers["content-type"].startswith("application/json")

    def test_rate_limits_still_count_cached_responses(self, client, db_router, monkeypatch):
        import api

        db_router.when("from season_sim_inputs", [{"payload": {"season_id": 1, "teams": {}, "games": []}}])
        limit = int(api.EXPENSIVE_RATE_LIMIT.split("/")[0])
        codes = [client.get("/season-sim").status_code for _ in range(limit + 1)]

        assert codes[:limit] == [200] * limit and codes[-1] == 429
