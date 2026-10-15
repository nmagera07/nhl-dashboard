"""market_odds: Kalshi's game odds, logged next to our predictions."""

from datetime import date

import pytest

import market_odds as mo


def _market(team, bid, ask, volume="1000"):
    return {"ticker": f"KXNHLGAME-26OCT14DALCOL-{team}", "yes_bid_dollars": bid, "yes_ask_dollars": ask, "volume_fp": volume}


def test_event_tickers_use_kalshis_codes():
    assert mo.event_ticker(date(2026, 10, 14), "DAL", "COL") == "KXNHLGAME-26OCT14DALCOL"
    assert mo.event_ticker(date(2026, 11, 2), "TBL", "LAK") == "KXNHLGAME-26NOV02TBLA"


def test_implied_probability_is_the_normalized_midpoint():
    odds = mo.implied_home_prob([_market("COL", "0.5900", "0.6000"), _market("DAL", "0.4000", "0.4100")], "COL", "DAL")
    assert odds["home_prob"] == pytest.approx(0.595 / (0.595 + 0.405), abs=1e-4)
    assert (odds["home_bid"], odds["away_ask"], odds["volume"]) == (0.59, 0.41, 2000.0)


def test_no_two_sided_quote_means_no_odds():
    assert mo.implied_home_prob([_market("COL", None, "0.60"), _market("DAL", "0.40", "0.41")], "COL", "DAL") is None
    assert mo.implied_home_prob([_market("COL", "0.59", "0.60")], "COL", "DAL") is None


class FakeCursor:
    def __init__(self):
        self.inserted, self.sql = [], []

    def execute(self, sql, params=None):
        self.sql.append(sql)
        if sql.lstrip().startswith("INSERT"):
            self.inserted.append(params)


def test_log_games_skips_games_without_a_market():
    def get(url):
        if "DALCOL" in url:
            return {"markets": [_market("COL", "0.59", "0.60"), _market("DAL", "0.40", "0.41")]}
        return {"markets": []}

    cur = FakeCursor()
    assert mo.log_games(cur, date(2026, 10, 14), [(1, "COL", "DAL"), (2, "WSH", "MTL")], get=get) == 1
    assert cur.inserted[0][:7] == (1, "kalshi", "morning", date(2026, 10, 14), "COL", "DAL", 0.595)
    assert any("GRANT SELECT ON market_odds" in s for s in cur.sql)


def test_compare_grades_both_and_the_disagreements():
    rows = [(0.7, 0.6, True), (0.6, 0.4, False), (0.3, 0.45, False)]
    result = mo.compare(rows)
    assert result["games"] == 3 and result["picked_different_winner"] == 1 and result["we_were_right_when_we_differed"] == 0
    assert result["brier_ours"] == pytest.approx((0.09 + 0.36 + 0.09) / 3, abs=1e-4)
    assert result["brier_market"] == pytest.approx((0.16 + 0.16 + 0.2025) / 3, abs=1e-4)


def test_only_games_that_havent_started_are_logged():
    scores = {"games": [{"id": 1, "gameState": "FUT"}, {"id": 2, "gameState": "LIVE"}, {"id": 3, "gameState": "PRE"}]}
    assert mo.not_started(date(2026, 10, 14), get=lambda url: scores) == {1, 3}
