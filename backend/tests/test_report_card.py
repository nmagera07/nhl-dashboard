"""report_card: PuckPulse vs. the sportsbooks on finished games."""

from datetime import date

import pytest

import report_card as rc

MARKET = {"captured": "close", "home_prob": 0.60, "home_line": -160, "away_line": 140, "books": 9,
          "best_home_line": -150, "best_away_line": 145, "best_home_book": "DraftKings", "best_away_book": "FanDuel",
          "home_spread": -1.5, "home_spread_line": 165, "away_spread_line": -190, "home_cover_prob": 0.39,
          "total": 6.5, "over_line": -110, "under_line": -110, "over_prob": 0.5}


def game(home_score, away_score, prob=0.663, market=MARKET, day=date(2026, 10, 17)):
    return {"game_date": day, "home": "COL", "away": "PIT", "home_win_prob": prob, "home_goals": 3.345,
            "away_goals": 2.357, "home_score": home_score, "away_score": away_score, "market": market}


def test_briers_and_favorites_on_the_same_games():
    out = rc.summarize([game(4, 1), game(1, 3)])
    ml = out["moneyline"]
    assert ml["games"] == 2
    assert ml["brier_ours"] == pytest.approx(((0.663 - 1) ** 2 + 0.663 ** 2) / 2, abs=1e-4)
    assert ml["brier_books"] == pytest.approx(((0.6 - 1) ** 2 + 0.6 ** 2) / 2, abs=1e-4)
    assert ml["favorite_won_ours"] == 0.5 and ml["favorite_won_books"] == 0.5


def test_value_badges_are_graded_as_100_dollar_bets():
    # The best home price (-150) beats the consensus and the model agrees: a value badge on COL.
    won = rc.summarize([game(4, 1)])["value_bets"]
    assert won["wins"] >= 1 and won["profit"] > 0
    ml = next(v for v in won["list"] if v["bet"] == "COL")
    assert ml["price"] == -150 and ml["book"] == "DraftKings" and ml["profit"] == pytest.approx(66.67, abs=0.01)
    lost = rc.summarize([game(1, 3)])["value_bets"]
    assert lost["losses"] >= 1 and next(v for v in lost["list"] if v["bet"] == "COL")["profit"] == -100


def test_puck_line_bets_are_graded_on_the_spread():
    out = rc.summarize([game(4, 3)])["value_bets"]  # COL wins by one: the -1.5 bet loses
    pl = next((v for v in out["list"] if v["bet"] == "COL -1.5"), None)
    assert pl is not None and pl["result"] == -1


def test_totals_landing_on_the_line_are_not_graded():
    out = rc.summarize([game(4, 2, market={**MARKET, "total": 6.0})])
    assert out["total"]["games"] == 0


def test_games_without_market_odds_still_count_but_are_not_compared():
    out = rc.summarize([game(4, 1, market=None), game(1, 3)])
    assert out["games"] == 2 and out["moneyline"]["games"] == 1
    assert out["value_bets"]["bets"] == len(out["value_bets"]["list"])


def test_biggest_disagreements_first():
    out = rc.summarize([game(4, 1, prob=0.62), game(1, 3, prob=0.75)])
    assert out["disagreements"][0]["ours"] == 0.75


class TestReportCardRoute:
    def test_week_and_season(self, client, db_router):
        db_router.when("from game_predictions", [
            {"game_id": 1, "game_date": date(2026, 10, 1), "home_abbrev": "COL", "away_abbrev": "PIT", "home_win_prob": 0.66,
             "home_goals": 3.3, "away_goals": 2.4, "home_score": 4, "away_score": 1},
            {"game_id": 2, "game_date": date(2026, 10, 17), "home_abbrev": "COL", "away_abbrev": "PIT", "home_win_prob": 0.66,
             "home_goals": 3.3, "away_goals": 2.4, "home_score": 1, "away_score": 3}])
        db_router.when("from market_odds", [{**MARKET, "game_id": 2}])
        body = client.get("/report-card").json()
        assert body["as_of"] == "2026-10-17"
        assert body["season"]["games"] == 2 and body["week"]["games"] == 1
        assert body["week"]["moneyline"]["games"] == 1
