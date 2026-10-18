"""team_lines: last game's lines from NHL shift charts, and GET /teams/{team}/lines."""

import json

import team_lines as tl


def _box():
    def players(start, n, prefix):
        return [{"playerId": start + i, "name": {"default": f"{prefix}. P{start + i}"}} for i in range(n)]
    return {
        "awayTeam": {"abbrev": "AAA"}, "homeTeam": {"abbrev": "HHH"},
        "playerByGameStats": {
            "awayTeam": {"forwards": players(100, 6, "A"), "defense": players(200, 4, "A"), "goalies": players(300, 1, "A")},
            "homeTeam": {"forwards": players(400, 6, "H"), "defense": players(500, 4, "H"), "goalies": players(600, 1, "H")},
        },
    }


def _shift(pid, start, end, period=1):
    return {"playerId": pid, "period": period, "startTime": f"{start // 60:02d}:{start % 60:02d}",
            "endTime": f"{end // 60:02d}:{end % 60:02d}"}


def _shifts():
    """Two 60-second shifts per team: line 1 + pair 1, then line 2 + pair 2. Goalies on throughout."""
    out = []
    for team, f, d, g in ((0, 100, 200, 300), (1, 400, 500, 600)):
        out += [_shift(g, 0, 120)]
        out += [_shift(f + i, 0, 60) for i in range(3)] + [_shift(d + i, 0, 60) for i in range(2)]
        out += [_shift(f + 3 + i, 60, 120) for i in range(3)] + [_shift(d + 2 + i, 60, 120) for i in range(2)]
    return out


def test_lines_come_from_time_together_at_even_strength():
    lines = tl.lines_from_game(_box(), _shifts())
    away = lines["AAA"]
    assert [l["player_ids"] for l in away["lines"]] == [[100, 101, 102], [103, 104, 105]]
    assert [p["player_ids"] for p in away["pairs"]] == [[200, 201], [202, 203]]
    assert away["lines"][0]["minutes"] == 1.0 and away["lines"][0]["players"] == ["P100", "P101", "P102"]


def test_power_play_time_doesnt_count():
    shifts = _shifts() + [_shift(100, 120, 180), _shift(103, 120, 180), _shift(200, 120, 180)]  # 3 skaters vs nobody
    lines = tl.lines_from_game(_box(), shifts)
    assert [l["player_ids"] for l in lines["AAA"]["lines"]] == [[100, 101, 102], [103, 104, 105]]


def test_shared_last_names_keep_the_initial():
    assert tl.display_names({1: "M. Tkachuk", 2: "B. Tkachuk", 3: "S. Bennett"}) == {1: "M. Tkachuk", 2: "B. Tkachuk", 3: "Bennett"}


def test_latest_game_per_team_within_the_lookback():
    from datetime import date

    days = {
        "2026-10-12": [{"id": 2, "gameState": "OFF", "gameType": 2, "awayTeam": {"abbrev": "AAA"}, "homeTeam": {"abbrev": "HHH"}},
                       {"id": 3, "gameState": "FUT", "gameType": 2, "awayTeam": {"abbrev": "CCC"}, "homeTeam": {"abbrev": "DDD"}}],
        "2026-10-10": [{"id": 1, "gameState": "OFF", "gameType": 2, "awayTeam": {"abbrev": "HHH"}, "homeTeam": {"abbrev": "CCC"}}],
    }
    latest = tl.latest_games(3, today=date(2026, 10, 13), get=lambda url: {"games": days.get(url.rsplit("/", 1)[-1], [])})
    assert latest["AAA"] == {"game_id": 2, "date": "2026-10-12", "opponent": "HHH", "home": False}
    assert latest["HHH"]["game_id"] == 2 and latest["CCC"]["game_id"] == 1 and "DDD" not in latest


class TestLinesRoute:
    def test_returns_last_games_lines(self, client, db_router):
        payload = {"lines": [{"players": ["A", "B", "C"], "player_ids": [1, 2, 3], "minutes": 11.8}], "pairs": []}
        db_router.when("select 1 from teams where team_abbrev", {"?column?": 1})
        db_router.when("from team_lines", {"game_id": 2026020087, "game_date": "2026-10-12", "opponent": "BUF",
                                           "home": True, "payload": json.dumps(payload)})
        # Shift charts list a line in no particular order; positions put it left wing, center, right wing.
        db_router.when("from players", [{"player_id": 1, "position_code": "C"}, {"player_id": 2, "position_code": "R"},
                                        {"player_id": 3, "position_code": "L"}])

        body = client.get("/teams/fla/lines").json()

        assert body["team"] == "FLA" and body["game"] == {"id": 2026020087, "date": "2026-10-12", "opponent": "BUF", "home": True}
        assert body["lines"][0]["players"] == ["C", "A", "B"] and body["lines"][0]["player_ids"] == [3, 1, 2]

    def test_no_lines_yet(self, client, db_router):
        db_router.when("select 1 from teams where team_abbrev", {"?column?": 1})
        db_router.when("from team_lines", None)
        assert client.get("/teams/FLA/lines").json() == {"team": "FLA", "game": None, "lines": [], "pairs": []}

    def test_unknown_team_404s(self, client, db_router):
        db_router.when("select 1 from teams where team_abbrev", None)
        assert client.get("/teams/ZZZ/lines").status_code == 404
