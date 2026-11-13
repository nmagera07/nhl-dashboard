"""
run_daily_ingest.py -- the daily job's entry point. Subprocesses are
faked, so no ingestion script actually runs.
"""

import sys
from types import SimpleNamespace

import pytest

import run_daily_ingest
from run_daily_ingest import retry_failed, run_all


def _fake_runner(exit_codes):
    calls = []

    def runner(cmd):
        calls.append(cmd)
        return SimpleNamespace(returncode=exit_codes[cmd[-1]])

    return runner, calls


class TestRunAll:
    def test_runs_standings_first_since_the_others_depend_on_it(self):
        runner, calls = _fake_runner(
            {"ingest_standings.py": 0, "ingest_advanced_stats.py": 0, "war.py": 0, "ingest_xg.py": 0, "simulate_playoff_odds.py": 0, "game_predictions.py": 0, "goalie_starts.py": 0, "market_odds.py": 0, "daily_digest.py": 0, "ingest_player_stats.py": 0, "team_lines.py": 0, "moneypuck_odds.py": 0}
        )

        assert run_all(runner=runner) == []
        assert [cmd[-1] for cmd in calls] == [
            "ingest_standings.py",
            "ingest_xg.py",  # before the odds, which use it
            "ingest_advanced_stats.py",  # after ingest_xg, whose 5-on-5 rows it sums
            "war.py",  # after ingest_xg, whose goalie xG it uses
            "simulate_playoff_odds.py",
            "game_predictions.py",  # after the odds, whose ratings it logs
            "goalie_starts.py",  # after ingest_xg, whose starters it reads
            "market_odds.py",  # after the predictions, whose games it looks up
            "daily_digest.py",  # after the odds, which it reads
            "ingest_player_stats.py",
            "team_lines.py",  # after rosters
            "moneypuck_odds.py",
        ]
        assert all(cmd[0] == sys.executable for cmd in calls)

    def test_a_failed_script_does_not_stop_the_next_one(self):
        runner, calls = _fake_runner(
            {"ingest_standings.py": 0, "ingest_advanced_stats.py": 1, "war.py": 0, "ingest_xg.py": 0, "simulate_playoff_odds.py": 0, "game_predictions.py": 0, "goalie_starts.py": 0, "market_odds.py": 0, "daily_digest.py": 0, "ingest_player_stats.py": 0, "team_lines.py": 0, "moneypuck_odds.py": 0}
        )

        assert run_all(runner=runner, sleep=lambda s: None) == ["ingest_advanced_stats.py"]
        assert len(calls) == 13  # 12 scripts + the failed one's quick retry


def _flaky_runner(fail_times):
    """Each script fails its first fail_times[script] runs, then works."""
    calls = []

    def runner(cmd):
        calls.append(cmd[-1])
        left = fail_times.get(cmd[-1], 0)
        fail_times[cmd[-1]] = left - 1
        return SimpleNamespace(returncode=1 if left > 0 else 0)

    return runner, calls


class TestQuickRetry:
    def test_a_short_outage_is_retried_before_the_scripts_that_depend_on_it(self):
        runner, calls = _flaky_runner({"ingest_standings.py": 1, "ingest_xg.py": 1})
        waits = []

        assert run_all(runner=runner, sleep=waits.append) == []
        assert calls[:5] == ["ingest_standings.py", "ingest_standings.py", "ingest_xg.py", "ingest_xg.py",
                             "ingest_advanced_stats.py"]  # 11-13: WAR and the odds now see last night's games
        assert waits == [run_daily_ingest.QUICK_RETRY_WAIT_SECONDS] * 2

    def test_a_long_outage_stops_waiting_once_the_budget_is_spent(self):
        runner, calls = _flaky_runner({s: 5 for s in run_daily_ingest.SCRIPTS})
        waits = []

        failed = run_all(runner=runner, sleep=waits.append)

        assert failed == run_daily_ingest.SCRIPTS  # all left for the end-of-run retry
        assert sum(waits) <= run_daily_ingest.QUICK_RETRY_BUDGET_SECONDS
        assert len(calls) == len(run_daily_ingest.SCRIPTS) + len(waits)


class TestRetryFailed:
    def test_a_script_that_works_the_second_time_is_not_a_failure(self):
        runner, calls = _fake_runner({"game_predictions.py": 0, "market_odds.py": 1})

        assert retry_failed(["game_predictions.py", "market_odds.py"], started=0, runner=runner, clock=lambda: 60) == ["market_odds.py"]
        assert [cmd[-1] for cmd in calls] == ["game_predictions.py", "market_odds.py"]

    def test_no_retry_once_the_run_is_near_the_job_timeout(self):
        runner, calls = _fake_runner({"game_predictions.py": 0})

        late = run_daily_ingest.RETRY_UNTIL_SECONDS + 1
        assert retry_failed(["game_predictions.py"], started=0, runner=runner, clock=lambda: late) == ["game_predictions.py"]
        assert calls == []


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
        monkeypatch.setattr(run_daily_ingest, "retry_failed", lambda failed, started: failed)

        with pytest.raises(SystemExit) as exc:
            run_daily_ingest.main()

        assert exc.value.code == 1
        assert pings == ["https://hc-ping.com/abc/start", "https://hc-ping.com/abc/fail"]

    def test_succeeds_when_the_retry_fixes_every_failure(self, monkeypatch, pings):
        monkeypatch.setattr(run_daily_ingest, "run_all", lambda: ["game_predictions.py"])
        monkeypatch.setattr(run_daily_ingest, "retry_failed", lambda failed, started: [])

        run_daily_ingest.main()

        assert pings == ["https://hc-ping.com/abc/start", "https://hc-ping.com/abc"]

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
