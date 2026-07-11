"""
Shared fixtures for the backend test suite.

DB strategy: mock the connection layer rather than hitting a real
Postgres instance. api.py (and the ingestion scripts) all go through one
narrow seam -- get_connection() -> conn.cursor() -> cur.execute()/fetchone()/
fetchall() -- so patching get_connection() to return a fake connection
backed by canned, per-query responses covers every endpoint without ever
opening a socket. See backend/README.md for the full reasoning.

Every module under test (api.py, simulate_playoff_odds.py,
ingest_advanced_stats.py) reads os.environ["DATABASE_URL"] at import time
(even though most of it is never used at test time), so a dummy value is
seeded here before those modules get imported by any test file.
"""

import os

os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test_db")

import pytest
from fastapi.testclient import TestClient


def _normalize(sql):
    return " ".join(sql.split()).lower()


class DBRouter:
    """
    Maps a query's SQL text to a canned response, matched by an
    unambiguous substring rather than the full query -- keeps each test's
    setup short and immune to whitespace/formatting changes in api.py.

    .when(substring, response) registers a rule. response is either the
    value to hand back (a list of dict-like rows for fetchall, a single
    dict-like row or None for fetchone) or a callable(params) -> value for
    responses that depend on the query params (e.g. echoing back a
    team_abbrev). Rules are checked in registration order, first match
    wins, so register more specific substrings before general ones.

    Every execute() call is recorded in .calls so tests can assert a
    query never ran at all (e.g. FastAPI's own request validation should
    reject a bad player_id before any DB call happens).
    """

    def __init__(self):
        self.rules = []
        self.calls = []

    def when(self, substring, response):
        self.rules.append((_normalize(substring), response))
        return self

    def route(self, query, params):
        self.calls.append((query, params))
        normalized = _normalize(query)
        for substring, response in self.rules:
            if substring in normalized:
                return response(params) if callable(response) else response
        raise AssertionError(
            f"DBRouter: no rule matched query.\n  query={query!r}\n  params={params!r}\n"
            f"  registered substrings={[s for s, _ in self.rules]}"
        )


class FakeCursor:
    def __init__(self, router):
        self.router = router
        self._result = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, query, params=None):
        self._result = self.router.route(query, tuple(params) if params else ())

    def fetchone(self):
        result = self._result
        if result is None:
            return None
        if isinstance(result, list):
            return result[0] if result else None
        return result

    def fetchall(self):
        result = self._result
        if result is None:
            return []
        if isinstance(result, list):
            return result
        return [result]


class FakeConnection:
    def __init__(self, router):
        self.router = router
        self.closed = False

    def cursor(self):
        return FakeCursor(self.router)

    def close(self):
        self.closed = True


@pytest.fixture
def db_router():
    """A fresh, empty DBRouter for the test to register .when() rules on."""
    return DBRouter()


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """
    slowapi's default in-memory storage is a module-level singleton on
    api.limiter, and TestClient requests all share the same fake client
    address -- so without a reset, call counts would silently accumulate
    across every test in the session and could eventually trip a 429 on
    an otherwise-unrelated test. Reset before each test so every test
    starts with a clean rate-limit window regardless of run order.
    """
    import api

    api.limiter.reset()


@pytest.fixture
def client(monkeypatch, db_router):
    """
    A FastAPI TestClient for api.app with get_connection() patched to
    return a FakeConnection backed by the test's db_router. No real
    database connection is ever attempted.
    """
    import api

    monkeypatch.setattr(api, "get_connection", lambda: FakeConnection(db_router))
    return TestClient(api.app)


# ---------------------------------------------------------------------------
# Canned rows, shaped to match the real columns from schema.sql / api.py's
# SELECTs (verified against real data pulled from the live API during the
# response-model work in this project).
# ---------------------------------------------------------------------------


@pytest.fixture
def team_row():
    return {
        "team_abbrev": "COL",
        "team_name": "Colorado Avalanche",
        "common_name": "Avalanche",
        "place_name": "Colorado",
        "conference": "Western",
        "division": "Central",
        "logo_url": "https://assets.nhle.com/logos/nhl/svg/COL_light.svg",
    }


@pytest.fixture
def playoff_odds_row():
    return {
        "id": 36,
        "season_id": 20252026,
        "as_of_date": "2026-04-17",
        "team_abbrev": "BUF",
        "playoff_pct": 1.0,
        "trials": 5000,
        "computed_at": "2026-07-09T22:30:05.210336",
        "team_name": "Buffalo Sabres",
        "division": "Atlantic",
        "conference": "Eastern",
        "logo_url": "https://assets.nhle.com/logos/nhl/svg/BUF_light.svg",
    }


@pytest.fixture
def roster_skater_row():
    return {
        "player_id": 8477492,
        "team_abbrev": "COL",
        "first_name": "Nathan",
        "last_name": "MacKinnon",
        "position_code": "C",
        "sweater_number": 29,
        "shoots_catches": "R",
        "height_in_inches": 72,
        "weight_in_pounds": 200,
        "birth_date": "1995-09-01",
        "birth_city": "Halifax",
        "birth_country": "CAN",
        "headshot_url": "https://assets.nhle.com/mugs/nhl/20262027/COL/8477492.png",
        "updated_at": "2026-07-08T23:56:05.982947",
        "season_id": 20252026,
        "games_played": 80,
        "goals": 53,
        "assists": 74,
        "points": 127,
        "plus_minus": 57,
        "pim": 39,
        "shots": 350,
        "shooting_pctg": 0.1514,
        "power_play_goals": 11,
        "power_play_points": 30,
        "shorthanded_goals": 0,
        "shorthanded_points": 0,
        "game_winning_goals": 7,
        "ot_goals": 1,
        "wins": None,
        "losses": None,
        "ot_losses": None,
        "goals_against_avg": None,
        "save_pctg": None,
        "shutouts": None,
    }


@pytest.fixture
def roster_goalie_row():
    return {
        "player_id": 8475809,
        "team_abbrev": "COL",
        "first_name": "Scott",
        "last_name": "Wedgewood",
        "position_code": "G",
        "sweater_number": 41,
        "shoots_catches": "L",
        "height_in_inches": 74,
        "weight_in_pounds": 201,
        "birth_date": "1992-08-14",
        "birth_city": "Brampton",
        "birth_country": "CAN",
        "headshot_url": "https://assets.nhle.com/mugs/nhl/20262027/COL/8475809.png",
        "updated_at": "2026-07-08T23:56:05.982947",
        "season_id": 20252026,
        "games_played": 45,
        "goals": None,
        "assists": None,
        "points": None,
        "plus_minus": None,
        "pim": None,
        "shots": None,
        "shooting_pctg": None,
        "power_play_goals": None,
        "power_play_points": None,
        "shorthanded_goals": None,
        "shorthanded_points": None,
        "game_winning_goals": None,
        "ot_goals": None,
        "wins": 31,
        "losses": 6,
        "ot_losses": 6,
        "goals_against_avg": 2.0243,
        "save_pctg": 0.9213,
        "shutouts": 4,
    }


@pytest.fixture
def player_bio_row():
    return {
        "player_id": 8477492,
        "team_abbrev": "COL",
        "first_name": "Nathan",
        "last_name": "MacKinnon",
        "position_code": "C",
        "sweater_number": 29,
        "shoots_catches": "R",
        "height_in_inches": 72,
        "weight_in_pounds": 200,
        "birth_date": "1995-09-01",
        "birth_city": "Halifax",
        "birth_country": "CAN",
        "headshot_url": "https://assets.nhle.com/mugs/nhl/20262027/COL/8477492.png",
        "updated_at": "2026-07-08T23:56:05.982947",
        "team_name": "Colorado Avalanche",
        "team_logo_url": "https://assets.nhle.com/logos/nhl/svg/COL_light.svg",
    }


@pytest.fixture
def player_season_stat_row():
    return {
        "id": 211,
        "player_id": 8477492,
        "season_id": 20252026,
        "games_played": 80,
        "goals": 53,
        "assists": 74,
        "points": 127,
        "plus_minus": 57,
        "pim": 39,
        "shots": 350,
        "shooting_pctg": 0.1514,
        "power_play_goals": 11,
        "power_play_points": 30,
        "shorthanded_goals": 0,
        "shorthanded_points": 0,
        "game_winning_goals": 7,
        "ot_goals": 1,
        "wins": None,
        "losses": None,
        "ot_losses": None,
        "goals_against_avg": None,
        "save_pctg": None,
        "shutouts": None,
        "updated_at": "2026-07-08T23:56:05.982947",
    }


@pytest.fixture
def player_advanced_stat_row():
    return {
        "id": 843,
        "player_id": 8477492,
        "season_id": 20252026,
        "corsi_for": 1024,
        "corsi_against": 760,
        "corsi_for_pct": 0.574,
        "fenwick_for": 738,
        "fenwick_against": 584,
        "fenwick_for_pct": 0.5582,
        "games_processed": 50,
        "updated_at": "2026-07-09T02:06:35.973321",
    }


@pytest.fixture
def standings_row():
    return {
        "id": 135,
        "snapshot_date": "2026-07-09",
        "team_abbrev": "COL",
        "season_id": 20252026,
        "games_played": 82,
        "wins": 55,
        "losses": 16,
        "ot_losses": 11,
        "points": 121,
        "point_pctg": 0.7378,
        "goal_for": 302,
        "goal_against": 203,
        "goal_differential": 99,
        "home_wins": 26,
        "home_losses": 9,
        "road_wins": 29,
        "road_losses": 7,
        "l10_wins": 7,
        "l10_losses": 2,
        "l10_ot_losses": 1,
        "streak_code": "W",
        "streak_count": 3,
        "division_sequence": 1,
        "conference_sequence": 1,
        "league_sequence": 1,
        "wildcard_sequence": 0,
        "created_at": "2026-07-09T09:59:59.838160",
        "team_name": "Colorado Avalanche",
        "common_name": "Avalanche",
        "division": "Central",
        "conference": "Western",
        "logo_url": "https://assets.nhle.com/logos/nhl/svg/COL_light.svg",
    }


@pytest.fixture
def season_final_standing_row():
    return {
        "id": 140,
        "season_id": 20212022,
        "team_abbrev": "PIT",
        "games_played": 82,
        "wins": 46,
        "losses": 25,
        "ot_losses": 11,
        "points": 103,
        "point_pctg": 0.628,
        "goal_for": 272,
        "goal_against": 229,
        "goal_differential": 43,
        "division_sequence": 3,
        "conference_sequence": 7,
        "league_sequence": 12,
        "made_playoffs": True,
        "created_at": "2026-07-08T23:03:54.971739",
    }
