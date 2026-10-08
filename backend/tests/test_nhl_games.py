"""
nhl_games.game_boxscore -- merges the NHL's three gamecenter endpoints.
_get is faked, so no network calls are made.
"""

import pytest

import nhl_games
from datetime import date

from nhl_games import NHLGamesUnavailable, game_boxscore, games_on_date, month_calendar

@pytest.fixture(autouse=True)
def fresh_cache():
    """Every test starts with an empty game response cache."""
    nhl_games._cache.clear()
    yield
    nhl_games._cache.clear()


BOXSCORE = {"id": 2026020044, "gameState": "OFF", "awayTeam": {"abbrev": "NSH"}, "homeTeam": {"abbrev": "TOR"}}
LANDING = {"summary": {"scoring": [{"goals": []}], "threeStars": []}}
RIGHT_RAIL = {
    "linescore": {"byPeriod": [], "totals": {"away": 4, "home": 5}},
    "shotsByPeriod": [{"away": 11, "home": 8}],
    "teamGameStats": [{"category": "sog", "awayValue": 25, "homeValue": 37}],
}


def _fake_get(responses):
    def fake(path):
        for suffix, response in responses.items():
            if path.endswith(suffix):
                if isinstance(response, Exception):
                    raise response
                return response
        raise AssertionError(f"unexpected path {path}")

    return fake


class TestGameBoxscore:
    def test_merges_all_three_endpoints(self, monkeypatch):
        monkeypatch.setattr(
            nhl_games, "_get", _fake_get({"/boxscore": BOXSCORE, "/landing": LANDING, "/right-rail": RIGHT_RAIL})
        )

        game = game_boxscore(2026020044)

        assert game["id"] == 2026020044
        assert game["awayTeam"]["abbrev"] == "NSH"
        assert game["summary"] == LANDING["summary"]
        assert game["linescore"]["totals"] == {"away": 4, "home": 5}
        assert game["shotsByPeriod"] == RIGHT_RAIL["shotsByPeriod"]
        assert game["teamGameStats"] == RIGHT_RAIL["teamGameStats"]

    def test_landing_and_right_rail_outages_still_return_the_core_box_score(self, monkeypatch):
        down = NHLGamesUnavailable("down")
        monkeypatch.setattr(
            nhl_games, "_get", _fake_get({"/boxscore": BOXSCORE, "/landing": down, "/right-rail": down})
        )

        game = game_boxscore(2026020044)

        assert game["id"] == 2026020044
        assert game["summary"] == {}
        assert game["linescore"] == {}
        assert game["shotsByPeriod"] == []
        assert game["teamGameStats"] == []

    def test_boxscore_outage_is_still_an_error(self, monkeypatch):
        monkeypatch.setattr(
            nhl_games,
            "_get",
            _fake_get({"/boxscore": NHLGamesUnavailable("down"), "/landing": LANDING, "/right-rail": RIGHT_RAIL}),
        )

        with pytest.raises(NHLGamesUnavailable):
            game_boxscore(2026020044)


class TestGamesOnDate:
    def test_reads_the_score_feed_for_that_date(self, monkeypatch):
        # Regression: /schedule/{date} nests games under gameWeek, so reading
        # "games" from it always returned an empty list.
        calls = []

        def fake_get(path):
            calls.append(path)
            return {"games": [{"id": 2026020044, "gameState": "OFF"}], "gameWeek": []}

        monkeypatch.setattr(nhl_games, "_get", fake_get)

        games = games_on_date(date(2026, 10, 6))

        assert calls == ["/score/2026-10-06"]
        assert games == [{"id": 2026020044, "gameState": "OFF"}]

    def test_a_day_with_no_games_returns_an_empty_list(self, monkeypatch):
        monkeypatch.setattr(nhl_games, "_get", lambda path: {"gameWeek": []})

        assert games_on_date(date(2026, 7, 1)) == []


class TestMonthCalendar:
    @pytest.fixture(autouse=True)
    def empty_cache(self):
        nhl_games._CALENDAR_CACHE.clear()

    @staticmethod
    def _schedule(calls):
        """Fake /schedule/{date}: a week starting that day, with 2 games/day
        except Sundays (0), plus the season bounds."""
        def fake_get(path):
            calls.append(path)
            start = date.fromisoformat(path.rsplit("/", 1)[1])
            week = []
            for i in range(7):
                d = start + nhl_games.timedelta(days=i)
                week.append({"date": d.isoformat(), "numberOfGames": 0 if d.weekday() == 6 else 2})
            return {
                "regularSeasonStartDate": "2026-10-07",
                "playoffEndDate": "2027-06-10",
                "gameWeek": week,
            }
        return fake_get

    def test_counts_games_per_day_for_the_month_within_the_season(self, monkeypatch):
        calls = []
        monkeypatch.setattr(nhl_games, "_get", self._schedule(calls))

        result = month_calendar(2026, 10, today=date(2026, 10, 8))

        assert result["season_start"] == "2026-10-07"
        assert result["season_end"] == "2027-06-10"
        dates = [d["date"] for d in result["days"]]
        assert dates[0] == "2026-10-07"                # nothing before the season starts
        assert "2026-10-11" not in dates               # a Sunday with no games
        assert all(d.startswith("2026-10-") for d in dates)  # weeks spill into November; dropped
        assert {d["games"] for d in result["days"]} == {2}
        assert calls[0] == "/schedule/2026-10-01" and len(calls) == 5

    def test_repeat_requests_are_served_from_cache(self, monkeypatch):
        calls = []
        monkeypatch.setattr(nhl_games, "_get", self._schedule(calls))

        month_calendar(2026, 10, today=date(2026, 10, 8))
        month_calendar(2026, 10, today=date(2026, 10, 8))

        assert len(calls) == 5

    def test_an_nhl_outage_is_raised_not_cached(self, monkeypatch):
        def down(path):
            raise NHLGamesUnavailable("down")
        monkeypatch.setattr(nhl_games, "_get", down)

        with pytest.raises(NHLGamesUnavailable):
            month_calendar(2026, 10)
        assert nhl_games._CALENDAR_CACHE == {}



class TestResponseCache:
    @pytest.fixture
    def clock(self, monkeypatch):
        """A controllable clock for the cache."""
        now = {"t": 1000.0}
        monkeypatch.setattr(nhl_games, "_now", lambda: now["t"])
        return now

    @staticmethod
    def counting(responses):
        """Fake _get returning successive responses (an Exception is raised)."""
        calls = []

        def fake_get(path):
            calls.append(path)
            r = responses[min(len(calls), len(responses)) - 1]
            if isinstance(r, Exception):
                raise r
            return r
        return fake_get, calls

    def test_repeat_requests_within_the_ttl_hit_the_cache(self, monkeypatch, clock):
        live = {"games": [{"id": 1, "gameState": "LIVE"}]}
        fake, calls = self.counting([live])
        monkeypatch.setattr(nhl_games, "_get", fake)

        nhl_games.today_games()
        clock["t"] += nhl_games.SCOREBOARD_LIVE_TTL - 1
        nhl_games.today_games()

        assert len(calls) == 1

    def test_refetches_after_the_ttl(self, monkeypatch, clock):
        fake, calls = self.counting([{"games": [{"id": 1, "gameState": "LIVE"}]}])
        monkeypatch.setattr(nhl_games, "_get", fake)

        nhl_games.today_games()
        clock["t"] += nhl_games.SCOREBOARD_LIVE_TTL + 1
        nhl_games.today_games()

        assert len(calls) == 2

    def test_a_day_of_finals_is_cached_much_longer_than_a_live_day(self, monkeypatch, clock):
        finals = {"games": [{"id": 1, "gameState": "OFF"}, {"id": 2, "gameState": "FINAL"}]}
        fake, calls = self.counting([finals])
        monkeypatch.setattr(nhl_games, "_get", fake)

        nhl_games.games_on_date(date(2026, 10, 6))
        clock["t"] += 30 * 60
        nhl_games.games_on_date(date(2026, 10, 6))

        assert len(calls) == 1

    def test_serves_the_last_good_copy_when_the_nhl_api_fails(self, monkeypatch, clock):
        good = {"games": [{"id": 1, "gameState": "LIVE"}]}
        fake, calls = self.counting([good, NHLGamesUnavailable("down")])
        monkeypatch.setattr(nhl_games, "_get", fake)

        first = nhl_games.today_games()
        clock["t"] += 120
        second = nhl_games.today_games()

        assert len(calls) == 2           # it did try again
        assert second == first           # but fell back to the cached copy

    def test_too_old_a_copy_is_not_served_and_the_error_surfaces(self, monkeypatch, clock):
        fake, _ = self.counting([{"games": []}, NHLGamesUnavailable("down")])
        monkeypatch.setattr(nhl_games, "_get", fake)

        nhl_games.today_games()
        clock["t"] += nhl_games.MAX_STALE_SECONDS + 1

        with pytest.raises(NHLGamesUnavailable):
            nhl_games.today_games()

    def test_live_box_scores_refresh_quickly_and_finals_are_kept(self, monkeypatch, clock):
        assert nhl_games._boxscore_ttl({"gameState": "LIVE"}) == nhl_games.LIVE_TTL
        assert nhl_games._boxscore_ttl({"gameState": "OFF"}) == nhl_games.FINAL_TTL
        assert nhl_games._boxscore_ttl({"gameState": "FUT"}) == nhl_games.SCHEDULED_TTL

    def test_concurrent_requests_share_one_upstream_fetch(self, monkeypatch):
        import threading

        calls = []
        release = threading.Event()

        def slow_get(path):
            calls.append(path)
            release.wait(2)
            return {"games": [{"id": 1, "gameState": "LIVE"}]}

        monkeypatch.setattr(nhl_games, "_get", slow_get)
        results = []
        threads = [threading.Thread(target=lambda: results.append(nhl_games.today_games())) for _ in range(10)]
        for t in threads:
            t.start()
        release.set()
        for t in threads:
            t.join(5)

        assert len(calls) == 1
        assert len(results) == 10

    def test_the_cache_is_size_capped(self):
        cache = nhl_games._ResponseCache(max_entries=3)
        for i in range(5):
            cache.get(f"k{i}", lambda i=i: i, lambda v: 60)

        assert list(cache._entries) == ["k2", "k3", "k4"]
