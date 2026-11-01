"""value_pick: the Bets tab's value of the night, picked from the morning lines and graded vs. the close."""

from datetime import date

import pytest

import value_pick as v

PRED = {"home_abbrev": "COL", "away_abbrev": "PIT", "home_win_prob": 0.663, "home_goals": 3.345, "away_goals": 2.357,
        "home_score": None, "away_score": None}
MORNING = {"source": "sportsbooks", "captured": "morning", "home_prob": 0.60, "home_line": -160, "away_line": 140,
           "best_home_line": -150, "best_away_line": 145, "best_home_book": "DraftKings", "best_away_book": "FanDuel",
           "home_spread": -1.5, "home_spread_line": 150, "away_spread_line": -175, "home_cover_prob": 0.39,
           "total": 6.5, "over_line": -130, "under_line": 110, "over_prob": 0.54}


def board(**market):
    pred = {"home": "COL", "away": "PIT", "home_win_prob": 0.663, "home_goals": 3.345, "away_goals": 2.357}
    return v.bets.game_board(pred, {**MORNING, **market})


def test_picks_the_best_value_side():
    p = v.pick({"7": board()})
    assert (p["game_id"], p["market"], p["side"], p["price"], p["book"], p["value"]) == (7, "moneyline", "home", -150, "DraftKings", True)


def test_without_value_the_closest_side_the_model_leans_toward():
    p = v.pick({"7": board(best_home_line=-165)})
    assert not p["value"] and p["edge"] > 0 and p["side"] == "home"


def test_no_prices_no_pick():
    assert v.pick({"7": v.bets.game_board({"home": "COL", "away": "PIT", "home_win_prob": 0.6}, None)}) is None


def test_grades_the_puck_line_from_the_pick_side_with_clv():
    p = {"market": "puck_line", "side": "away", "line": 1.5, "price": -175}
    close = board(away_spread_line=-190, home_cover_prob=0.35)  # the books moved toward PIT +1.5: closing 65%
    result = v.grade(p, {"home_score": 3, "away_score": 2}, close)  # lost by 1: covered
    assert result["outcome"] == "win" and result["units"] == pytest.approx(100 / 175, abs=1e-4)
    assert result["clv"] == pytest.approx(0.65 * (1 + 100 / 175) - 1, abs=1e-4) and result["close_price"] == -190
    assert v.grade(p, {"home_score": 4, "away_score": 2}, close)["outcome"] == "loss"


def test_no_clv_when_the_line_moved_and_no_grade_before_the_final():
    p = {"market": "puck_line", "side": "home", "line": -1.5, "price": 150}
    assert v.grade(p, {"home_score": 4, "away_score": 2}, board(home_spread=-2.5))["clv"] is None
    assert v.grade(p, {"home_score": None, "away_score": None}, None) is None


class _Cur:
    def __init__(self, predictions, markets):
        self.rows = {"game_predictions": predictions, "market_odds": markets}

    def execute(self, query, params=None):
        self._last = next(rows for name, rows in self.rows.items() if name in query)

    def fetchall(self):
        return self._last


def test_tonights_pick_and_the_record_of_past_nights():
    predictions = [
        {**PRED, "game_id": 1, "game_date": date(2026, 10, 28), "home_score": 4, "away_score": 1},
        {**PRED, "game_id": 2, "game_date": date(2026, 10, 29)},
    ]
    markets = [{**MORNING, "game_id": 1}, {**MORNING, "game_id": 1, "captured": "close", "home_prob": 0.62},
               {**MORNING, "game_id": 2}]
    out = v.value_of_the_night(_Cur(predictions, markets), date(2026, 10, 29))
    assert out["available"] and out["pick"]["game_id"] == 2 and out["result"] is None
    rec = out["record"]
    assert (rec["nights"], rec["wins"], rec["losses"], rec["value_nights"]) == (1, 1, 0, 1)
    assert rec["units"] == pytest.approx(100 / 150, abs=0.01)
    assert rec["beat_close"] == 1 and rec["clv"] == pytest.approx(0.62 * (1 + 100 / 150) - 1, abs=1e-4)
    assert out["last"]["result"]["outcome"] == "win"


def test_season_start():
    assert v.season_start(date(2026, 10, 29)) == date(2026, 9, 1)
    assert v.season_start(date(2027, 4, 1)) == date(2026, 9, 1)


def test_endpoint_without_a_morning_snapshot(client, db_router):
    db_router.when("from game_predictions", [])
    db_router.when("from market_odds", [])
    body = client.get("/value-of-the-night?date=2026-10-29").json()
    assert body["available"] is False and body["pick"] is None and body["record"]["nights"] == 0


def test_share_text_and_card(client, monkeypatch):
    import api
    from tests.test_og_image import VALUE
    monkeypatch.setattr(api, "value_of_the_night", lambda day: VALUE)
    body = client.get("/value-of-the-night/2026-10-29/share").json()
    assert body["title"] == "Closest to value, Oct 29: MTL +142 (to win)"
    assert body["description"] == ("MTL @ DAL: PuckPulse's fair chance 42% vs. the books' 41%, expected return +1%. "
                                   "This season: 7-6, +3.16u, beat the close 5 of 12. Not betting advice. 21+.")
    assert body["image"].endswith("/og/value/2026-10-29.png")
    image = client.get("/og/value/2026-10-29.png")
    assert image.status_code == 200 and image.headers["content-type"] == "image/png"
    monkeypatch.setattr(api, "value_of_the_night", lambda day: {"available": False})
    assert client.get("/value-of-the-night/2026-10-30/share").status_code == 404
