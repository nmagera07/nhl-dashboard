"""
run_daily_ingest.py -- the daily job's entry point. Subprocesses are
faked, so no ingestion script actually runs.
"""

import sys
from types import SimpleNamespace

import pytest

import run_daily_ingest
from run_daily_ingest import run_all


def _fake_runner(exit_codes):
    calls = []

    def runner(cmd):
        calls.append(cmd)
        return SimpleNamespace(returncode=exit_codes[cmd[-1]])

    return runner, calls


class TestRunAll:
    def test_runs_standings_first_since_player_stats_depend_on_it(self):
        runner, calls = _fake_runner({"ingest_standings.py": 0, "ingest_player_stats.py": 0})

        assert run_all(runner=runner) == []
        assert [cmd[-1] for cmd in calls] == ["ingest_standings.py", "ingest_player_stats.py"]
        assert all(cmd[0] == sys.executable for cmd in calls)

    def test_a_failed_script_does_not_stop_the_next_one(self):
        runner, calls = _fake_runner({"ingest_standings.py": 1, "ingest_player_stats.py": 0})

        assert run_all(runner=runner) == ["ingest_standings.py"]
        assert len(calls) == 2


@pytest.fixture
def pings(monkeypatch):
    """Records heartbeat pings instead of sending them."""
    sent = []
    monkeypatch.setattr(run_daily_ingest, "HEALTHCHECK_URL", "https://hc-ping.com/abc")
    monkeypatch.setattr(run_daily_ingest.requests, "post", lambda url, data=None, timeout=None: sent.append(url))
    return sent


class TestMain:
    def test_exits_non_zero_when_any_script_fails(self, monkeypatch, pings):
        monkeypatch.setattr(run_daily_ingest, "run_all", lambda: ["ingest_player_stats.py"])

        with pytest.raises(SystemExit) as exc:
            run_daily_ingest.main()

        assert exc.value.code == 1
        assert pings == ["https://hc-ping.com/abc/start", "https://hc-ping.com/abc/fail"]

    def test_pings_start_then_success(self, monkeypatch, pings):
        monkeypatch.setattr(run_daily_ingest, "run_all", lambda: [])

        run_daily_ingest.main()

        assert pings == ["https://hc-ping.com/abc/start", "https://hc-ping.com/abc"]


class TestPing:
    def test_does_nothing_without_a_url(self, monkeypatch):
        sent = []
        monkeypatch.setattr(run_daily_ingest, "HEALTHCHECK_URL", "")

        run_daily_ingest.ping(post=lambda *a, **k: sent.append(a))

        assert sent == []

    def test_a_failed_ping_never_breaks_the_run(self, monkeypatch):
        monkeypatch.setattr(run_daily_ingest, "HEALTHCHECK_URL", "https://hc-ping.com/abc")

        def down(*args, **kwargs):
            raise run_daily_ingest.requests.ConnectionError("hc-ping.com unreachable")

        run_daily_ingest.ping(post=down)  # no exception
