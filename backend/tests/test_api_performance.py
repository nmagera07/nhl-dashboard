"""The API's speed plumbing: connection pooling, gzip, and cache headers."""

import psycopg2
import pytest

import api


class FakePgConnection:
    def __init__(self):
        self.closed = 0
        self.rollbacks = 0

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closed = 1


@pytest.fixture
def pool(monkeypatch):
    opened = []

    def connect(*args, **kwargs):
        opened.append(FakePgConnection())
        return opened[-1]

    monkeypatch.setattr(api.psycopg2, "connect", connect)
    monkeypatch.setattr(api, "_pool", [])
    return opened


class TestConnectionPool:
    def test_a_returned_connection_is_reused(self, pool):
        first = api.get_connection()
        first.close()
        second = api.get_connection()

        assert len(pool) == 1 and second._conn is pool[0]
        assert pool[0].rollbacks == 1  # the read transaction was ended before reuse

    def test_concurrent_requests_get_their_own_connections(self, pool):
        a, b = api.get_connection(), api.get_connection()
        assert a._conn is not b._conn and len(pool) == 2

    def test_connections_idle_too_long_are_replaced(self, pool, monkeypatch):
        api.get_connection().close()
        clock = api.time.monotonic()
        monkeypatch.setattr(api.time, "monotonic", lambda: clock + api.POOL_IDLE_SECONDS + 1)

        fresh = api.get_connection()

        assert len(pool) == 2 and fresh._conn is pool[1] and pool[0].closed

    def test_a_broken_connection_is_dropped_not_pooled(self, pool):
        conn = api.get_connection()

        def broken():
            raise psycopg2.OperationalError("server closed the connection")

        conn._conn.rollback = broken
        conn.close()

        assert api._pool == [] and pool[0].closed

    def test_the_pool_is_capped(self, pool):
        conns = [api.get_connection() for _ in range(api.POOL_MAX_IDLE + 2)]
        for c in conns:
            c.close()

        assert len(api._pool) == api.POOL_MAX_IDLE
        assert sum(c.closed for c in pool) == 2


class TestResponseHeaders:
    def test_large_responses_are_gzipped(self, client, db_router):
        games = [["2026-11-01", "PIT", "BOS"]] * 500
        db_router.when("from season_sim_inputs", [{"payload": {"season_id": 1, "teams": {}, "games": games}}])

        response = client.get("/season-sim", headers={"Accept-Encoding": "gzip"})

        assert response.headers.get("content-encoding") == "gzip"

    def test_daily_data_is_cacheable_but_live_data_is_not(self):
        assert api._daily_cacheable("/standings/latest")
        assert api._daily_cacheable("/playoff-odds/history")
        assert api._daily_cacheable("/players/8478402")
        assert api._daily_cacheable("/teams/PIT/roster")
        assert api._daily_cacheable("/season-sim")
        assert not api._daily_cacheable("/teams/PIT/schedule")
        assert not api._daily_cacheable("/games/today")
        assert not api._daily_cacheable("/season-sim/scenario")
        assert not api._daily_cacheable("/push/config")

    def test_the_header_is_set_on_daily_routes(self, client, db_router):
        db_router.when("from season_sim_inputs", [{"payload": {"season_id": 1, "teams": {}, "games": []}}])

        assert client.get("/season-sim").headers["cache-control"] == api.DAILY_CACHE_CONTROL
        assert "cache-control" not in client.get("/").headers
