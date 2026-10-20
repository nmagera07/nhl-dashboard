"""draft_board: the consensus board and the mock draft's order."""

import draft_board


def _board(*lists, names=("Ann", "Bo", "Cy", "Di")):
    return {"draft_year": 2027, "prospects": {n: {"pos": "C", "team": "Club", "league": None} for n in names},
            "sources": [{"name": f"S{i}", "url": "https://x.example", "as_of": "2026-10-01", "ranks": ranks}
                        for i, ranks in enumerate(lists)]}


def test_consensus_averages_ranks_and_breaks_ties_by_best_rank():
    rows = draft_board.consensus(_board(["Ann", "Bo", "Cy", "Di"], ["Bo", "Cy", "Ann", "Di"]))
    # Ann 1+3, Bo 2+1, Cy 3+2: Bo 1.5, Ann and Cy 2.5 (Ann's best is 1st), Di 4.
    assert [r["name"] for r in rows] == ["Bo", "Ann", "Cy", "Di"]
    assert rows[0]["rank"] == 1 and rows[0]["avg"] == 1.5 and rows[0]["ranks"] == {"S0": 2, "S1": 1}


def test_a_player_a_list_leaves_off_counts_as_one_past_its_end():
    rows = draft_board.consensus(_board(["Ann", "Bo"], ["Bo", "Cy", "Di", "Ann"], names=("Ann", "Bo", "Cy", "Di")))
    by_name = {r["name"]: r for r in rows}
    assert by_name["Cy"]["ranks"]["S0"] is None and by_name["Cy"]["avg"] == (3 + 2) / 2
    assert [r["name"] for r in rows][:2] == ["Bo", "Ann"]


def test_the_real_board_loads_and_every_ranked_name_is_a_prospect():
    board = draft_board.load(2027)
    for source in board["sources"]:
        assert source["url"].startswith("https://") and len(set(source["ranks"])) == len(source["ranks"])
        assert set(source["ranks"]) <= set(board["prospects"])
    assert draft_board.consensus(board)[0]["name"] == "Landon DuPont"
    assert draft_board.load(1990) is None


STANDINGS = [{"team_abbrev": t, "league_sequence": seq} for t, seq in [("AAA", 1), ("BBB", 2), ("CCC", 3), ("DDD", 4)]]


def test_today_order_is_the_lottery_then_playoff_teams_worst_first():
    assert draft_board.today_order([{"team": "DDD"}, {"team": "CCC"}], STANDINGS) == ["DDD", "CCC", "BBB", "AAA"]


def test_projected_order_sorts_by_expected_pick():
    projected = [{"team": "CCC", "picks": [0.1, 0.1] + [0.0] * 14},   # mostly a playoff team: late
                 {"team": "AAA", "picks": [0.5, 0.5] + [0.0] * 14}]   # surely in, picking 1st or 2nd
    # DDD and BBB never miss: 24.5 each, tied, so worst record first.
    assert draft_board.projected_order(projected, STANDINGS) == ["AAA", "CCC", "DDD", "BBB"]


def test_mock_draft_gives_each_pick_the_next_best_player():
    mock = draft_board.mock_draft(["DDD", "CCC"], [{"name": "Ann"}, {"name": "Bo"}, {"name": "Cy"}])
    assert mock == [{"pick": 1, "team": "DDD", "prospect": {"name": "Ann"}}, {"pick": 2, "team": "CCC", "prospect": {"name": "Bo"}}]
