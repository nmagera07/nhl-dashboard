"""
Pure-function tests for api.py's compute_staleness() -- the ingestion
staleness check that logs an ERROR line (picked up by the
nhl-ingestion-stale Azure Monitor alert) when standings_snapshots hasn't
been updated recently, meaning ingest_standings.py's scheduled task may
have stopped running.
"""

from datetime import datetime, timedelta, timezone

from api import as_utc, compute_staleness


class TestAsUtc:
    def test_naive_datetime_gets_utc_attached(self):
        # What psycopg2 actually hands back for a TIMESTAMP (no time
        # zone) column -- reproduces a real TypeError hit when this
        # was compared directly against datetime.now(timezone.utc).
        naive = datetime(2026, 7, 18, 9, 0, 0)

        result = as_utc(naive)

        assert result.tzinfo == timezone.utc
        assert result.replace(tzinfo=None) == naive

    def test_already_aware_datetime_is_left_alone(self):
        aware = datetime(2026, 7, 18, 9, 0, 0, tzinfo=timezone.utc)

        assert as_utc(aware) == aware

    def test_none_passes_through(self):
        assert as_utc(None) is None


class TestComputeStaleness:
    def test_recent_update_is_not_stale(self):
        now = datetime(2026, 7, 17, 12, 0, tzinfo=timezone.utc)
        last_updated = now - timedelta(hours=2)

        is_stale, hours_old = compute_staleness(last_updated, now, threshold_hours=30)

        assert is_stale is False
        assert hours_old == 2.0

    def test_update_older_than_threshold_is_stale(self):
        now = datetime(2026, 7, 17, 12, 0, tzinfo=timezone.utc)
        last_updated = now - timedelta(hours=31)

        is_stale, hours_old = compute_staleness(last_updated, now, threshold_hours=30)

        assert is_stale is True
        assert hours_old == 31.0

    def test_exactly_at_threshold_is_not_yet_stale(self):
        # Strictly greater-than, not >=, so a run that lands exactly on
        # the boundary (e.g. the daily job firing right at the 30h mark
        # from the previous day's run) isn't a false alarm.
        now = datetime(2026, 7, 17, 12, 0, tzinfo=timezone.utc)
        last_updated = now - timedelta(hours=30)

        is_stale, hours_old = compute_staleness(last_updated, now, threshold_hours=30)

        assert is_stale is False

    def test_no_rows_at_all_is_stale_with_no_age(self):
        now = datetime(2026, 7, 17, 12, 0, tzinfo=timezone.utc)

        is_stale, hours_old = compute_staleness(None, now, threshold_hours=30)

        assert is_stale is True
        assert hours_old is None
