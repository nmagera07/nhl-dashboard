"""data_checks: the morning check that the 2 AM run produced everything the site needs."""

import json
from datetime import date

import data_checks as dc

TODAY = date(2026, 10, 29)
FINALS = [{"id": 1, "away": "PIT", "home": "TBL", "state": "OFF"}, {"id": 2, "away": "FLA", "home": "WPG", "state": "OFF"}]


class Cursor:
    """Answers each query from a table of (SQL fragment -> rows); records what ran."""

    def __init__(self, answers):
        self.answers, self.sql, self.rows = answers, [], []

    def execute(self, sql, params=None):
        self.sql.append((sql, params))
        matches = [fragment for fragment in self.answers if fragment in sql]
        self.rows = self.answers[max(matches, key=len)] if matches else []  # the most specific rule wins

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows


def healthy(**overrides):
    answers = {
        "MAX(": [{"latest": TODAY}],
        "FROM team_game_xg WHERE game_id = ANY(%s) GROUP BY": [{"game_id": 1}, {"game_id": 2}],
        "FROM war_v2_games": [{"game_id": 1}, {"game_id": 2}],
        "FROM team_game_5v5": [{"game_id": 1}, {"game_id": 2}],
        "FROM game_results": [{"game_id": 1}, {"game_id": 2}],
        "FROM game_predictions WHERE game_id = ANY(%s) AND graded_at IS NULL": [],
        "FROM game_predictions WHERE game_id = ANY(%s)": [{"game_id": 3}],
        "FROM swing_of_the_night": [{"?column?": 1}],
        "SUM(playoff_pct)": [{"total": 1600.0, "teams": 32}],
        "xg_for < %s": [],
    }
    answers.update(overrides)
    return Cursor(answers)


def get(url, timeout):
    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            if url.endswith("2026-10-28"):
                return {"games": [{"id": g["id"], "gameType": 2, "gameState": g["state"], "awayTeam": {"abbrev": g["away"]},
                                   "homeTeam": {"abbrev": g["home"]}} for g in FINALS]
                        + [{"id": 9, "gameType": 1, "gameState": "OFF", "awayTeam": {"abbrev": "X"}, "homeTeam": {"abbrev": "Y"}}]}
            return {"games": [{"id": 3, "gameType": 2, "gameState": "FUT", "awayTeam": {"abbrev": "UTA"}, "homeTeam": {"abbrev": "PIT"}}]}
    return Response()


def failures(results):
    return {r.name: r.detail for r in results if not r.ok}


def test_a_clean_night_passes_everything():
    results = dc.run_checks(healthy(), TODAY, get)
    assert failures(results) == {}
    assert len(results) == len(dc.FRESH) + 5 + 1 + 1 + 2


def test_a_table_the_run_didnt_update_is_flagged():
    cur = healthy(**{"MAX(": [{"latest": date(2026, 10, 28)}]})
    assert failures(dc.check_fresh(cur, TODAY))["WAR updated"] == "last updated 2026-10-28"


def test_a_game_missing_its_nightly_data_is_named():
    cur = healthy(**{"FROM team_game_5v5": [{"game_id": 1}], "FROM game_predictions WHERE game_id = ANY(%s) AND graded_at IS NULL": [{"game_id": 2}]})
    found = failures(dc.check_last_night(cur, FINALS))
    assert found == {"Last night: 5-on-5 shift data": "missing FLA @ WPG (2)",
                     "Last night: predictions graded": "ungraded FLA @ WPG (2)"}


def test_preseason_games_are_left_out():
    assert [g["id"] for g in dc.games_on(date(2026, 10, 28), get)] == [1, 2]


def test_playoff_odds_must_add_up_to_16_teams_either_scale():
    assert failures(dc.check_sanity(healthy(**{"SUM(playoff_pct)": [{"total": 16.0, "teams": 32}]}), [])) == {}
    bad = failures(dc.check_sanity(healthy(**{"SUM(playoff_pct)": [{"total": 1450.0, "teams": 32}]}), []))
    assert bad == {"Playoff odds add up": "32 teams, odds sum to 14.50 spots"}


def test_unusual_xg_is_flagged():
    cur = healthy(**{"xg_for < %s": [{"game_id": 2, "team_abbrev": "WPG", "xg_for": 11.2}]})
    assert failures(dc.check_sanity(cur, FINALS))["Last night's xG in range"] == "unusual: WPG 11.20 (2)"


def test_no_games_last_night_means_no_game_checks():
    assert dc.check_last_night(healthy(), []) == [] and dc.check_swing(healthy(), TODAY, []) == []


def test_results_are_saved_and_failures_pushed_once(monkeypatch):
    results = [dc.Result("WAR updated", False, "last updated 2026-10-28"), dc.Result("Standings updated", True)]
    cur = Cursor({})
    dc.save(cur, TODAY, results)
    run_date, ok, saved = cur.sql[-1][1]
    assert (run_date, ok, json.loads(saved)[0]["name"]) == (TODAY, False, "WAR updated")

    sent, claimed = [], []
    monkeypatch.setattr(dc.nlg, "claim", lambda cur, keys: claimed.append(keys) or set(keys) if len(claimed) < 1 else set())
    monkeypatch.setattr(dc.nlg, "creators", lambda cur: [{"endpoint": "e"}])
    monkeypatch.setattr(dc.nlg, "deliver", lambda cur, key, sub, payload, ttl: sent.append((key, payload)) or True)
    assert dc.alert(cur, TODAY, results) == 1
    key, payload = sent[0]
    assert key == "data-check:2026-10-29"
    assert payload["title"] == "Data check: 1 problem" and payload["body"] == "WAR updated: last updated 2026-10-28"
    assert dc.alert(cur, TODAY, results) == 0  # already sent today


def test_a_clean_run_pushes_nothing(monkeypatch):
    monkeypatch.setattr(dc.nlg, "claim", lambda cur, keys: (_ for _ in ()).throw(AssertionError("claimed")))
    assert dc.alert(Cursor({}), TODAY, [dc.Result("WAR updated", True)]) == 0
