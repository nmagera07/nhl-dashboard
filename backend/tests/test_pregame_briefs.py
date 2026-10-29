"""pregame_briefs: asking the brief agent for today's games and storing what passes its checks."""

import json

import requests

import pregame_briefs as pb

SCORES = {"games": [
    {"id": 2026020199, "gameState": "FUT", "awayTeam": {"abbrev": "PHI"}, "homeTeam": {"abbrev": "WSH"}},
    {"id": 2026020200, "gameState": "PRE", "awayTeam": {"abbrev": "CGY"}, "homeTeam": {"abbrev": "EDM"}},
    {"id": 2026020198, "gameState": "LIVE", "awayTeam": {"abbrev": "PIT"}, "homeTeam": {"abbrev": "TBL"}},
]}


class Response:
    def __init__(self, body, status=200):
        self.body, self.status_code = body, status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def json(self):
        return self.body


class FakeConn:
    def __init__(self):
        self.sql, self.commits = [], 0

    def cursor(self):
        conn = self

        class Cursor:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def execute(self, sql, params=None):
                conn.sql.append((sql, params))
        return Cursor()

    def commit(self):
        self.commits += 1

    def saved(self):
        return [p for s, p in self.sql if "INSERT INTO game_briefs" in s]


def get(url, timeout):
    assert url.endswith("/score/2026-10-28")
    return Response(SCORES)


def test_only_games_still_to_start_are_briefed():
    assert pb.games_to_brief("2026-10-28", get) == [
        {"game_id": 2026020199, "away": "PHI", "home": "WSH", "date": "2026-10-28"},
        {"game_id": 2026020200, "away": "CGY", "home": "EDM", "date": "2026-10-28"},
    ]


def test_briefs_that_pass_are_stored_and_the_rest_keep_the_earlier_one(monkeypatch):
    monkeypatch.setattr(pb, "INTELLIGENCE_URL", "https://intel.test")
    monkeypatch.setattr(pb, "DIGEST_TOKEN", "s3cret")
    asked = []

    def post(url, json, headers, timeout):
        asked.append((url, json, headers))
        if json["game_id"] == 2026020199:
            return Response({"text": "- WSH is -230.", "model": "Google Gemini", "problems": [], "tools": ["get_bets({})"]})
        return Response({"text": None, "model": "Groq", "problems": ["These numbers aren't in the tool results: 7."], "tools": []})

    conn = FakeConn()
    assert pb.run(conn, "2026-10-28", get, post) == (1, 1)

    assert [a[0] for a in asked] == ["https://intel.test/briefs/write"] * 2
    assert asked[0][1] == {"game_id": 2026020199, "away": "PHI", "home": "WSH", "date": "2026-10-28"}
    assert asked[0][2] == {"X-Digest-Token": "s3cret"}
    game_id, day, text, model, tools = conn.saved()[0]
    assert (game_id, day, text, model, json.loads(tools)) == (2026020199, "2026-10-28", "- WSH is -230.", "Google Gemini",
                                                               ["get_bets({})"])
    assert len(conn.saved()) == 1  # the failed one doesn't overwrite an earlier brief
    assert any("CREATE TABLE IF NOT EXISTS game_briefs" in s for s, _ in conn.sql)


def test_an_unreachable_service_skips_the_game_and_keeps_going(monkeypatch):
    calls = []

    def post(url, json, headers, timeout):
        calls.append(json["game_id"])
        if len(calls) == 1:
            raise requests.ConnectionError("cold start")
        return Response({"text": "- EDM is -210.", "model": "Groq", "problems": [], "tools": []})

    conn = FakeConn()
    assert pb.run(conn, "2026-10-28", get, post) == (1, 1)
    assert calls == [2026020199, 2026020200] and conn.saved()[0][0] == 2026020200


def test_without_the_service_settings_nothing_runs(monkeypatch):
    monkeypatch.setattr(pb, "DATABASE_URL", "postgres://unused")
    monkeypatch.setattr(pb, "INTELLIGENCE_URL", "")
    monkeypatch.setattr(pb.psycopg2, "connect", lambda url: (_ for _ in ()).throw(AssertionError("connected")))
    pb.main()  # logs a warning, no DB connection
