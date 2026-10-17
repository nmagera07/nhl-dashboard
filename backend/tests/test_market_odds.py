"""market_odds: Kalshi's game odds, logged next to our predictions."""

import statistics
from datetime import date, datetime, timezone

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
    assert cur.inserted[0][:6] == (7, "sportsbooks", "morning", date(2026, 10, 15), "STL", "MTL")


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


def test_prices_round_trip_and_the_median_is_taken_as_probabilities():
    assert (mo.prob_to_american(0.6), mo.prob_to_american(100 / 230)) == (-150, 130)
    assert mo.median_price([-105, 100]) == -102  # not -2.5, the plain median of the two numbers
    assert mo.best_price([-120, -105, -110]) == -105
    assert mo.best_price([140, 150, 135]) == 150


def _book(key, moneyline, spread=None, total=None):
    markets = [{"key": "h2h", "outcomes": [{"name": "Colorado Avalanche", "price": moneyline[0]},
                                           {"name": "Pittsburgh Penguins", "price": moneyline[1]}]}]
    if spread:
        point, home_price, away_price = spread
        markets.append({"key": "spreads", "outcomes": [{"name": "Colorado Avalanche", "price": home_price, "point": point},
                                                       {"name": "Pittsburgh Penguins", "price": away_price, "point": -point}]})
    if total:
        point, over, under = total
        markets.append({"key": "totals", "outcomes": [{"name": "Over", "price": over, "point": point},
                                                      {"name": "Under", "price": under, "point": point}]})
    return {"key": key, "markets": markets}


GAME = {"commence_time": "2026-10-17T01:00:00Z", "home_team": "Colorado Avalanche", "away_team": "Pittsburgh Penguins",
        "bookmakers": [_book("dk", (-200, 165), (-1.5, 120, -140), (6.5, -110, -110)),
                       _book("fd", (-190, 160), (-1.5, 125, -150), (6.5, -105, -115)),
                       _book("mgm", (-210, 170), (-1.5, 118, -138), (6.0, -130, 110))]}


def test_consensus_has_the_puck_line_total_and_best_prices():
    odds = mo.sportsbook_consensus(GAME, "Colorado Avalanche", "Pittsburgh Penguins")
    assert (odds["best_home_line"], odds["best_away_line"], odds["books"]) == (-190, 170, 3)
    assert (odds["home_spread"], odds["home_spread_line"], odds["away_spread_line"]) == (-1.5, 120, -140)
    cover = statistics.median(mo.american_to_prob(h) / (mo.american_to_prob(h) + mo.american_to_prob(a))
                              for h, a in ((120, -140), (125, -150), (118, -138)))
    assert odds["home_cover_prob"] == pytest.approx(cover, abs=1e-4)
    # Two books say 6.5, one 6.0: the total is 6.5, from those two books only.
    assert (odds["total"], odds["over_line"], odds["under_line"]) == (6.5, -107, -112)
    assert odds["over_prob"] == pytest.approx(0.5 * (0.5 + (105 / 205) / (105 / 205 + 115 / 215)), abs=1e-4)


def test_consensus_without_a_puck_line_or_total_leaves_them_empty():
    odds = mo.sportsbook_consensus({**GAME, "bookmakers": [_book("dk", (-200, 165))]}, "Colorado Avalanche", "Pittsburgh Penguins")
    assert odds["home_prob"] and odds["home_spread"] is None and odds["total"] is None


def _game(game_id, start, state="FUT"):
    return {"id": game_id, "gameState": state, "startTimeUTC": start,
            "homeTeam": {"abbrev": "COL"}, "awayTeam": {"abbrev": "PIT"}}


NOW = datetime(2026, 10, 16, 22, 50, tzinfo=timezone.utc)  # 6:50 PM ET


def test_closing_snapshot_waits_until_a_game_is_15_minutes_out():
    games = [_game(1, "2026-10-16T23:10:00Z"), _game(2, "2026-10-17T01:00:00Z")]
    assert mo.closing_due(games, set(), NOW) == []  # 20 minutes out


def test_closing_snapshot_covers_every_game_in_the_next_75_minutes():
    games = [_game(1, "2026-10-16T23:00:00Z"), _game(2, "2026-10-16T23:30:00Z"), _game(3, "2026-10-17T01:00:00Z"),
             _game(4, "2026-10-16T22:00:00Z", "LIVE")]
    assert [g["id"] for g in mo.closing_due(games, set(), NOW)] == [1, 2]


def test_closing_snapshot_is_taken_once():
    games = [_game(1, "2026-10-16T23:00:00Z"), _game(2, "2026-10-16T23:30:00Z")]
    assert mo.closing_due(games, {1}, NOW) == []  # game 2 is still 40 minutes out


class ClosingCursor(FakeCursor):
    def __init__(self, have_close=()):
        super().__init__()
        self.have_close = list(have_close)
        self.result = []

    def execute(self, sql, params=None):
        super().execute(sql, params)
        if "SELECT DISTINCT game_id" in sql:
            self.result = [(g,) for g in self.have_close]
        elif "FROM teams" in sql:
            self.result = [("COL", "Colorado Avalanche"), ("PIT", "Pittsburgh Penguins")]

    def fetchall(self):
        return self.result

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeConnection:
    def __init__(self, cur):
        self.cur = cur

    def cursor(self):
        return self.cur

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _closing_run(monkeypatch, cur, credits=400):
    monkeypatch.setattr(mo.psycopg2, "connect", lambda url: FakeConnection(cur))
    scores = {"games": [_game(2026020120, "2026-10-17T01:00:00Z")]}
    get = lambda url: scores if "api-web.nhle.com" in url else {"markets": []}  # noqa: E731
    now = datetime(2026, 10, 17, 0, 50, tzinfo=timezone.utc)
    return mo.log_closing(now=now, get=get, odds_get=lambda: [GAME], credits=lambda: credits)


def test_closing_run_logs_the_full_sportsbook_snapshot_and_replaces_an_older_one(monkeypatch):
    cur = ClosingCursor()
    assert _closing_run(monkeypatch, cur) == 1
    insert = next(s for s in cur.sql if s.lstrip().startswith("INSERT") and "home_spread" in s)
    assert "DO UPDATE SET" in insert
    params = cur.inserted[-1]
    assert params[:6] == (2026020120, "sportsbooks", "close", date(2026, 10, 16), "COL", "PIT")
    assert -1.5 in params and 6.5 in params


def test_closing_run_skips_sportsbooks_when_credits_run_low(monkeypatch):
    cur = ClosingCursor()
    assert _closing_run(monkeypatch, cur, credits=mo.CREDIT_FLOOR - 1) == 1
    assert not any(p[1] == "sportsbooks" for p in cur.inserted)


def test_compare_bets_grades_puck_line_and_total_and_skips_pushes():
    rows = [
        (3.3, 2.4, -1.5, 0.44, 6.5, 0.54, 5, 2),   # home covers, over
        (2.6, 2.9, 1.5, 0.70, 6.0, 0.52, 3, 3),    # (a tie can't be final; 6 total is a push on 6.0)
        (2.9, 2.7, -1.5, 0.40, 5.5, 0.55, 2, 1),   # home doesn't cover, under
    ]
    result = mo.compare_bets(rows)
    assert result["puck line"]["games"] == 3
    assert result["total"]["games"] == 2
    assert 0 < result["puck line"]["brier_ours"] < 1 and 0 < result["total"]["brier_market"] < 1
