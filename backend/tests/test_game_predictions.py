"""game_predictions / prediction_record: logging, grading, and scoring the model's game predictions."""

from datetime import date

import pytest

import game_predictions as gp
from prediction_record import track_record

DAY = date(2026, 10, 11)
PAYLOAD = {
    "season_id": 20262027, "as_of_date": "2026-10-11",
    "model": {"version": "v2.1", "home_edge": 0.264, "scale": 1.47},
    "teams": {"PIT": {"rating": 0.137}, "CAR": {"rating": 0.565}, "NYR": {"rating": -0.04}},
}


def _game(gid, away, home, state="FUT", away_score=None, home_score=None, ended="REG"):
    return {"id": gid, "gameState": state, "gameOutcome": {"lastPeriodType": ended},
            "awayTeam": {"abbrev": away, "score": away_score}, "homeTeam": {"abbrev": home, "score": home_score}}


class TestPredictions:
    def test_logs_unstarted_games_with_the_models_home_win_probability(self):
        games = [_game(1, "CAR", "PIT"), _game(2, "NYR", "PIT", state="LIVE"), _game(3, "PIT", "XYZ")]
        [row] = gp.predictions(games, PAYLOAD, DAY)
        assert row["game_id"] == 1 and row["home_abbrev"] == "PIT" and row["away_abbrev"] == "CAR"
        # (0.137 - 0.565 + 0.264) / 1.47 -> the stronger visitor is favored, but home ice narrows it
        assert row["home_win_prob"] == pytest.approx(0.4722, abs=1e-4)
        assert row["model_version"] == "v2.1" and row["source"] == "daily"

    def test_a_tired_road_team_moves_the_prediction(self):
        payload = {**PAYLOAD, "model": {"version": "v2.6", "home_edge": 0.16, "scale": 1.457, "home_b2b": -0.306, "away_b2b": 0.53},
                   "games": [["2026-10-11", "PIT", "CAR", False, True]]}  # CAR played yesterday
        [tired] = gp.predictions([_game(1, "CAR", "PIT")], payload, DAY)
        [rested] = gp.predictions([_game(1, "CAR", "PIT")], {**payload, "games": []}, DAY)
        assert tired["home_win_prob"] == pytest.approx(1 / (1 + 2.718281828 ** (-(0.137 - 0.565 + 0.16 + 0.53) / 1.457)), abs=1e-4)
        assert tired["home_win_prob"] > rested["home_win_prob"]

    def test_outcome_needs_a_final_and_records_how_it_ended(self):
        assert gp.outcome(_game(1, "CAR", "PIT")) is None
        assert gp.outcome(_game(1, "DAL", "PIT", state="OFF", away_score=1, home_score=2, ended="SO")) == {
            "home_score": 2, "away_score": 1, "ended": "SO", "home_won": True}


class FakeCursor:
    def __init__(self, payload=None, ungraded=()):
        self.payload, self.ungraded, self.executed, self.rowcount = payload, list(ungraded), [], 1
        self._last = None

    def execute(self, sql, params=None):
        self.executed.append((" ".join(sql.split()), params))
        self._last = sql

    def fetchone(self):
        return (self.payload,) if self.payload else None

    def fetchall(self):
        return [(d,) for d in self.ungraded]


class TestLogAndGrade:
    def test_stale_ratings_log_nothing(self, monkeypatch):
        monkeypatch.setattr(gp.nhl_games, "games_on_date", lambda d: [_game(1, "CAR", "PIT")])
        cur = FakeCursor(payload={**PAYLOAD, "as_of_date": "2026-10-10"})
        assert gp.log_today(cur, DAY) == 0
        assert not any("INSERT" in sql for sql, _ in cur.executed)

    def test_logging_never_overwrites_an_existing_prediction(self, monkeypatch):
        monkeypatch.setattr(gp.nhl_games, "games_on_date", lambda d: [_game(1, "CAR", "PIT")])
        cur = FakeCursor(payload=PAYLOAD)
        assert gp.log_today(cur, DAY) == 1
        inserts = [sql for sql, _ in cur.executed if "INSERT" in sql]
        assert inserts and "ON CONFLICT (game_id) DO NOTHING" in inserts[0]

    def test_grades_finals_from_earlier_days_only_once(self, monkeypatch):
        monkeypatch.setattr(gp.nhl_games, "games_on_date", lambda d: [
            _game(1, "DAL", "PIT", state="OFF", away_score=1, home_score=2, ended="SO"),
            _game(2, "NYR", "CAR", state="FUT"),  # postponed: stays ungraded
        ])
        cur = FakeCursor(ungraded=[date(2026, 10, 10)])
        assert gp.grade(cur, DAY) == 1
        sql, params = cur.executed[-1]
        assert "home_won IS NULL" in sql and params["game_id"] == 1 and params["home_won"] is True


def test_digest_backfill_matches_the_digests_odds_to_game_ids():
    facts = {"tonight": [{"away": "DAL", "home": "PIT", "model_home_win_pct": 55},
                         {"away": "SEA", "home": "WSH"},  # no odds: skipped
                         {"away": "AAA", "home": "BBB", "model_home_win_pct": 50}]}  # no such game
    games = [_game(7, "DAL", "PIT"), _game(8, "SEA", "WSH")]
    [row] = gp.digest_predictions(facts, games, date(2026, 10, 10), 20262027)
    assert row["game_id"] == 7 and row["home_win_prob"] == 0.55 and row["source"] == "digest"


class TestTrackRecord:
    def test_nothing_graded_yet(self):
        assert track_record([{"home_win_prob": 0.6, "home_won": None}])["games"] == 0

    def test_scores_favorites_brier_and_calibration(self):
        rows = [
            {"game_id": 1, "game_date": "2026-10-10", "home_win_prob": 0.70, "home_won": True},
            {"game_id": 2, "game_date": "2026-10-10", "home_win_prob": 0.40, "home_won": True},  # away favorite lost
            {"game_id": 3, "game_date": "2026-10-11", "home_win_prob": 0.52, "home_won": False},
            {"game_id": 4, "game_date": "2026-10-11", "home_win_prob": 0.50, "home_won": True},  # no pick
        ]
        record = track_record(rows)
        assert record["games"] == 4
        assert (record["picks"], record["favorite_correct"]) == (3, 1)
        assert record["favorite_won"] == pytest.approx(1 / 3, abs=1e-4)
        assert record["brier"] == pytest.approx((0.09 + 0.36 + 0.2704 + 0.25) / 4, abs=1e-4)
        assert [b["label"] for b in record["calibration"]] == ["50-55%", "60-65%", "65%+"]
        assert record["recent"][0]["game_id"] == 4 and record["recent"][0]["favorite_won"] is None


def test_scoring_ratings_blend_this_season_with_last():
    prior = {"COL": (82, 300, 230), "SJS": (82, 200, 300)}
    seen = {"COL": (5, 20, 10, 18.0, 11.0), "SJS": (5, 10, 20, 11.0, 18.0)}
    ratings, league = gp.scoring_ratings(prior, seen)
    assert ratings["COL"]["offense"] > league > ratings["SJS"]["offense"]
    assert ratings["COL"]["defense"] < ratings["SJS"]["defense"]
    # 5 games barely move a 40-game prior.
    alone, _ = gp.scoring_ratings(prior, {})
    assert abs(ratings["COL"]["offense"] - alone["COL"]["offense"]) < 0.3


def test_predictions_carry_expected_goals_that_match_the_win_probability():
    import goal_model
    scoring = gp.scoring_ratings({"BOS": (82, 260, 240), "TOR": (82, 270, 250)}, {})
    payload = {"season_id": 20262027, "teams": {"BOS": {"rating": 0.2}, "TOR": {"rating": 0.0}}, "model": {}, "games": []}
    game = {"id": 1, "gameState": "FUT", "homeTeam": {"abbrev": "BOS"}, "awayTeam": {"abbrev": "TOR"}}
    (row,) = gp.predictions([game], payload, date(2026, 10, 16), scoring)
    assert row["home_goals"] > row["away_goals"]
    assert goal_model.home_win(goal_model.final_scores(row["home_goals"], row["away_goals"])) == pytest.approx(row["home_win_prob"], abs=1e-3)


def test_predictions_without_scoring_ratings_still_log_the_win_probability():
    payload = {"season_id": 20262027, "teams": {"BOS": {"rating": 0.2}, "TOR": {"rating": 0.0}}, "model": {}, "games": []}
    game = {"id": 1, "gameState": "FUT", "homeTeam": {"abbrev": "BOS"}, "awayTeam": {"abbrev": "TOR"}}
    (row,) = gp.predictions([game], payload, date(2026, 10, 16))
    assert row["home_win_prob"] and row["home_goals"] is None
