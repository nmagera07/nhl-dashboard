"""team_lines + GET /teams/{team}/lines: most-used 5-on-5 combinations."""

import pytest

import team_lines as tl

CSV = "\n".join([
    "lineId,name,team,position,situation,games_played,icetime,xGoalsPercentage,goalsFor,goalsAgainst",
    "847794684780428482078,Arvidsson-Larkin-Raymond,DET,line,5on5,3,1949.0,0.54,1.0,3.0",
    "84788548480803,Shea-Bouchard,EDM,pairing,5on5,5,804.0,0.73,3.0,0.0",
    "84788548480803,Shea-Bouchard,EDM,pairing,5on4,5,120.0,0.9,1.0,0.0",
    "123,Bad-Id,EDM,line,5on5,1,60.0,0.5,0,0",
])


def test_line_ids_are_7_digit_player_ids():
    assert tl.split_line_id("847794684780428482078") == [8477946, 8478042, 8482078]
    with pytest.raises(ValueError):
        tl.split_line_id("12345678")


def test_parses_5on5_lines_and_pairs_only():
    lines = tl.parse_lines(CSV)
    assert [(l["team_abbrev"], l["kind"], l["player_ids"]) for l in lines] == [
        ("DET", "line", [8477946, 8478042, 8482078]),
        ("EDM", "pair", [8478854, 8480803]),
    ]
    assert lines[0]["icetime_seconds"] == 1949 and lines[0]["xg_pct"] == 0.54 and lines[0]["goals_against"] == 3


def _row(kind, ids, names, seconds):
    return {"kind": kind, "player_ids": ids, "names": names, "games_played": 5, "icetime_seconds": seconds,
            "xg_pct": 0.5, "goals_for": 1, "goals_against": 1}


ROSTER = {i: (f"First{i}", name) for i, name in enumerate("Ann Bo Cy Di Ed Fay Gus Hal".split(), start=1)}


def test_top_lines_drop_players_off_the_roster_and_sort_by_ice_time():
    rows = [_row("line", [1, 2, 3], "x", 600), _row("line", [1, 2, 9], "x", 3000),
            _row("line", [4, 5, 6], "x", 1200), _row("pair", [7, 8], "x", 900)]
    top = tl.top_lines(rows, ROSTER)
    assert [l["players"] for l in top["lines"]] == [["Di", "Ed", "Fay"], ["Ann", "Bo", "Cy"]]
    assert top["pairs"][0] == {"players": ["Gus", "Hal"], "player_ids": [7, 8], "minutes": 15, "games": 5,
                               "xg_pct": 0.5, "goals_for": 1, "goals_against": 1}


def test_a_player_appears_once_most_used_combination_first():
    rows = [_row("line", [1, 2, 3], "x", 900), _row("line", [4, 2, 3], "x", 800), _row("line", [4, 5, 6], "x", 300)]
    assert [l["player_ids"] for l in tl.top_lines(rows, ROSTER)["lines"]] == [[1, 2, 3], [4, 5, 6]]


def test_shared_last_names_get_a_first_initial():
    names = tl.display_names({1: ("Aliaksei", "Protas"), 2: ("Ilya", "Protas"), 3: ("Pavel", "Dorofeyev")})
    assert names == {1: "A. Protas", 2: "I. Protas", 3: "Dorofeyev"}


class TestLinesRoute:
    def test_returns_current_combinations(self, client, db_router):
        db_router.when("select 1 from teams where team_abbrev", {"?column?": 1})
        db_router.when("select player_id, first_name, last_name from players",
                       [{"player_id": i, "first_name": "F", "last_name": n} for i, n in ((1, "A"), (2, "B"), (3, "C"), (7, "G"), (8, "H"))])
        db_router.when("from team_lines", [_row("line", [1, 2, 3], "A-B-C", 600), _row("pair", [7, 8], "G-H", 900)])

        response = client.get("/teams/det/lines")

        assert response.status_code == 200
        body = response.json()
        assert body["team"] == "DET"
        assert body["lines"][0]["players"] == ["A", "B", "C"] and body["pairs"][0]["minutes"] == 15

    def test_unknown_team_404s(self, client, db_router):
        db_router.when("select 1 from teams where team_abbrev", None)
        assert client.get("/teams/ZZZ/lines").status_code == 404
