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


EVENT = {
    "commence_time": "2026-10-15T23:30:00Z", "home_team": "St. Louis Blues", "away_team": "Montreal Canadiens",
    "bookmakers": [
        {"key": "dk", "markets": [{"key": "h2h", "outcomes": [{"name": "St Louis Blues", "price": -150}, {"name": "Montréal Canadiens", "price": 130}]}]},
        {"key": "fd", "markets": [{"key": "h2h", "outcomes": [{"name": "St Louis Blues", "price": -140}, {"name": "Montréal Canadiens", "price": 120}]}]},
        {"key": "x", "markets": [{"key": "totals", "outcomes": []}]},
    ],
}


def test_american_odds_to_probability():
    assert mo.american_to_prob(-150) == pytest.approx(0.6)
    assert mo.american_to_prob(130) == pytest.approx(100 / 230)


def test_sportsbook_consensus_removes_the_margin_and_takes_the_median():
    odds = mo.sportsbook_consensus(EVENT, "St. Louis Blues", "Montréal Canadiens")
    dk = 0.6 / (0.6 + 100 / 230)
    fd = (140 / 240) / (140 / 240 + 100 / 220)
    assert odds["home_prob"] == pytest.approx((dk + fd) / 2, abs=1e-4)
    assert (odds["home_line"], odds["away_line"], odds["books"]) == (-145, 125, 2)


def test_log_sportsbooks_matches_todays_games_by_name():
    cur = FakeCursor()
    names = {"STL": "St. Louis Blues", "MTL": "Montréal Canadiens", "PIT": "Pittsburgh Penguins", "BOS": "Boston Bruins"}
    later = {**EVENT, "commence_time": "2026-10-17T00:00:00Z", "home_team": "Pittsburgh Penguins", "away_team": "Boston Bruins"}
    logged = mo.log_sportsbooks(cur, date(2026, 10, 15), [(7, "STL", "MTL"), (8, "PIT", "BOS")], names, get=lambda: [EVENT, later])
    assert logged == 1  # the PIT game is another day's
    assert cur.inserted[0][:5] == (7, "sportsbooks", date(2026, 10, 15), "STL", "MTL")


class TestMarketOddsRoute:
    def test_returns_the_days_sportsbook_odds(self, client, db_router):
        from datetime import datetime, timezone
        db_router.when("from market_odds", [{"game_id": 2026020120, "home_abbrev": "DET", "away_abbrev": "PHI", "home_prob": 0.5612,
                                             "home_line": -135, "away_line": 115, "books": 8,
                                             "captured_at": datetime(2026, 10, 15, 6, 5, tzinfo=timezone.utc)}])
        body = client.get("/market-odds?date=2026-10-15").json()
        assert body["date"] == "2026-10-15"
        assert body["games"]["2026020120"] == {"home": "DET", "away": "PHI", "home_prob": 0.5612, "home_line": -135,
                                               "away_line": 115, "books": 8, "as_of": "2026-10-15T06:05:00+00:00"}
        query = next(q for q, _ in db_router.calls if "from market_odds" in q.lower())
        assert "source = 'sportsbooks'" in query  # Kalshi is graded, not shown
