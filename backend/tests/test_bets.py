"""bets: each game's lines next to PuckPulse's fair odds."""

from datetime import datetime, timezone

import pytest

import bets

PRED = {"home": "COL", "away": "PIT", "home_win_prob": 0.663, "home_goals": 3.345, "away_goals": 2.357}
MARKET = {"captured": "close", "home_prob": 0.60, "home_line": -160, "away_line": 140, "books": 9,
          "best_home_line": -150, "best_away_line": 145, "best_home_book": "DraftKings", "best_away_book": "FanDuel",
          "home_spread": -1.5, "home_spread_line": 150, "away_spread_line": -175, "home_cover_prob": 0.39,
          "total": 6.5, "over_line": -130, "under_line": 110, "over_prob": 0.54}


def test_decimal_odds():
    assert bets.decimal_odds(150) == 2.5 and bets.decimal_odds(-200) == 1.5


def test_moneyline_value_needs_an_edge_and_a_positive_return_at_the_best_price():
    ml = bets.game_board(PRED, MARKET)["moneyline"]
    home = ml["home"]
    assert home["edge"] == pytest.approx(0.063) and home["price"] == -150 and home["book"] == "DraftKings"
    assert home["ev"] == pytest.approx(0.663 * (1 + 100 / 150) - 1, abs=1e-4)
    assert home["value"] and not ml["away"]["value"]
    assert home["fair"] == -197


def test_puck_line_uses_the_books_line_and_the_goal_model():
    pl = bets.game_board(PRED, MARKET)["puck_line"]
    assert pl["home_spread"] == -1.5
    assert pl["home"]["ours"] + pl["away"]["ours"] == pytest.approx(1)
    assert 0.4 < pl["home"]["ours"] < 0.5 and pl["home"]["value"]  # 44.7% vs the books' 39% at +150


def test_totals_are_experimental_and_never_flagged():
    total = bets.game_board(PRED, MARKET)["total"]
    assert total["experimental"] and total["line"] == 6.5
    assert total["under"]["ev"] > 0 and not total["under"]["value"]


def test_a_whole_number_total_can_push():
    total = bets.game_board(PRED, {**MARKET, "total": 6.0})["total"]
    assert total["over"]["ours"] + total["under"]["ours"] < 0.95


def test_without_market_odds_or_expected_goals():
    board = bets.game_board({**PRED, "home_goals": None, "away_goals": None})
    assert board["moneyline"]["home"]["fair"] == -197 and "market" not in board["moneyline"]["home"]
    assert "puck_line" not in board and not board["moneyline"]["home"]["value"]


class TestBetsRoute:
    def test_prefers_the_closing_snapshot_and_marks_back_to_backs(self, client, db_router):
        db_router.when("from game_predictions", [{"game_id": 7, "home_abbrev": "COL", "away_abbrev": "PIT",
                                                  "home_win_prob": 0.663, "home_goals": 3.345, "away_goals": 2.357}])
        db_router.when("from market_odds", [{**MARKET, "game_id": 7, "captured_at": datetime(2026, 10, 17, 0, 45, tzinfo=timezone.utc)}])
        db_router.when("from season_sim_inputs", [{"games": [["2026-10-16", "COL", "PIT", False, True]]}])
        body = client.get("/bets?date=2026-10-16").json()
        game = body["games"]["7"]
        assert game["snapshot"] == "close" and game["b2b"] == {"home": False, "away": True}
        assert game["moneyline"]["home"]["value"] and game["as_of"].startswith("2026-10-17T00:45")
        query = next(q for q, _ in db_router.calls if "from market_odds" in q.lower())
        assert "source = 'sportsbooks'" in query and "captured = 'close'" in query
