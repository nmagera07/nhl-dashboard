"""
ingest_standings.insert_snapshot -- the latest run of the day must win.
A recording cursor stands in for the database; no network calls are made.
"""

from ingest_standings import insert_snapshot


class _RecordingCursor:
    def __init__(self):
        self.calls = []

    def execute(self, query, params=None):
        self.calls.append((" ".join(query.split()).lower(), params))


def _team(**overrides):
    team = {
        "teamAbbrev": {"default": "PIT"}, "seasonId": 20262027, "gamesPlayed": 4,
        "wins": 2, "losses": 2, "otLosses": 0, "points": 4, "pointPctg": 0.5,
        "goalFor": 15, "goalAgainst": 12, "goalDifferential": 3,
        "homeWins": 1, "homeLosses": 1, "roadWins": 1, "roadLosses": 1,
        "l10Wins": 2, "l10Losses": 2, "l10OtLosses": 0,
        "streakCode": "L", "streakCount": 1,
        "divisionSequence": 3, "conferenceSequence": 6, "leagueSequence": 13,
        "wildcardSequence": None,
    }
    team.update(overrides)
    return team


class TestInsertSnapshot:
    def test_a_rerun_overwrites_the_days_row_instead_of_skipping_it(self):
        # Regression: with DO NOTHING, a mid-game run at 00:56 UTC froze the
        # day and the 06:00 UTC run's final standings were silently dropped.
        cur = _RecordingCursor()

        insert_snapshot(cur, "2026-10-08", _team())

        query, _ = cur.calls[0]
        assert "on conflict (snapshot_date, team_abbrev) do update set" in query
        assert "do nothing" not in query

    def test_every_stat_and_the_freshness_timestamp_are_refreshed(self):
        cur = _RecordingCursor()

        insert_snapshot(cur, "2026-10-08", _team())

        query, _ = cur.calls[0]
        for column in ("games_played", "points", "goal_differential", "l10_wins",
                       "streak_code", "division_sequence", "wildcard_sequence"):
            assert f"{column} = excluded.{column}" in query
        assert "created_at = now()" in query

    def test_writes_the_given_snapshot_date_and_team(self):
        cur = _RecordingCursor()

        insert_snapshot(cur, "2026-10-08", _team(gamesPlayed=5, points=6))

        _, params = cur.calls[0]
        assert params[:4] == ("2026-10-08", "PIT", 20262027, 5)
        assert params[7] == 6


    def test_stores_the_clinch_flag_and_tolerates_its_absence(self):
        cur = _RecordingCursor()
        insert_snapshot(cur, "2026-04-10", _team(clinchIndicator="x"))
        insert_snapshot(cur, "2026-10-08", _team())

        assert cur.calls[0][1][-1] == "x"
        assert cur.calls[1][1][-1] is None
