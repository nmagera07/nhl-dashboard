"""
nhl_games.game_boxscore -- merges the NHL's three gamecenter endpoints.
_get is faked, so no network calls are made.
"""

import pytest

import nhl_games
from datetime import date

from nhl_games import NHLGamesUnavailable, game_boxscore, games_on_date, month_calendar

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
