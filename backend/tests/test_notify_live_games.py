"""notify_live_games: turning the live scoreboard into goal/final notifications."""

from datetime import datetime, timezone

import notify_live_games as n
import push

NOW = datetime(2026, 10, 10, 1, 0, tzinfo=timezone.utc)


def _goal(team, period, time, away_score, home_score, name="S. Crosby", to_date=5, assists=("E. Malkin",), strength="ev"):
    return {
        "period": period, "periodDescriptor": {"number": period, "periodType": "REG" if period <= 3 else "OT", "maxRegulationPeriods": 3},
        "timeInPeriod": time, "teamAbbrev": team, "name": {"default": name}, "goalsToDate": to_date,
        "assists": [{"name": {"default": a}} for a in assists], "awayScore": away_score, "homeScore": home_score, "strength": strength,
    }


def _game(state, goals=(), start="2026-10-09T23:00:00Z", away_score=0, home_score=0, game_id=2026020068, last="REG"):
    return {
        "id": game_id, "gameState": state, "startTimeUTC": start, "goals": list(goals),
        "awayTeam": {"abbrev": "PIT", "score": away_score}, "homeTeam": {"abbrev": "CBJ", "score": home_score},
        "gameOutcome": {"lastPeriodType": last},
    }


class TestEvents:
    def test_a_goal_reads_like_a_notification(self):
        game = _game("LIVE", [_goal("PIT", 2, "12:34", 2, 1, assists=("E. Malkin", "K. Letang"), strength="pp")])

        (event,), _ = n.events_for([game], NOW)

        assert event["kind"] == "goals" and event["teams"] == ["PIT", "CBJ"]
        assert event["payload"] == {
            "title": "🚨 PIT goal! PIT 2, CBJ 1",
            "body": "S. Crosby (5) from E. Malkin, K. Letang · power play · 2nd 12:34",
            "url": "/games/2026020068",
            "tag": "game-2026020068",
        }

    def test_only_the_newest_goal_is_sent_and_older_ones_are_claimed_quietly(self):
        game = _game("LIVE", [_goal("PIT", 1, "05:00", 1, 0), _goal("CBJ", 1, "06:10", 1, 1, assists=())])

        candidates, claim_only = n.events_for([game], NOW)

        assert [e["payload"]["body"] for e in candidates] == ["S. Crosby (5), unassisted · 1st 06:10"]
        assert [e["key"] for e in claim_only] == ["goal:2026020068:1:05:00:PIT"]

    def test_final_with_overtime(self):
        game = _game("FINAL", [_goal("PIT", 4, "02:11", 3, 2)], away_score=3, home_score=2, last="OT")

        candidates, _ = n.events_for([game], NOW)

        assert [e["kind"] for e in candidates] == ["goals", "finals"]  # the OT winner and the final
        assert candidates[1]["payload"]["title"] == "Final (OT): PIT 3, CBJ 2"
        assert candidates[1]["payload"]["body"].startswith("PIT wins")

    def test_ignores_old_games_and_games_not_started(self):
        yesterday = _game("OFF", [_goal("PIT", 1, "05:00", 1, 0)], start="2026-10-09T00:00:00Z")
        upcoming = _game("FUT", game_id=2)

        assert n.events_for([yesterday, upcoming], NOW) == ([], [])

    def test_official_games_only_send_the_final_not_goals(self):
        candidates, _ = n.events_for([_game("OFF", [_goal("PIT", 1, "05:00", 1, 0)], away_score=1)], NOW)

        assert [e["kind"] for e in candidates] == ["finals"]


class _Cursor:
    """Records SQL; claims behave like ON CONFLICT DO NOTHING against `already_sent`."""

    def __init__(self, already_sent=(), subs=()):
        self.already_sent = set(already_sent)
        self.subs = list(subs)
        self.sql = []
        self._rows = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, query, params=None):
        self.sql.append((query, params))
        self._rows = [(s["endpoint"], s["p256dh"], s["auth"]) for s in self.subs] if "FROM push_subscriptions" in query else []

    def fetchall(self):
        return self._rows


class _Conn:
    def __init__(self, cur):
        self.cur = cur

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def cursor(self):
        return self.cur

    def commit(self):
        pass


def _run(monkeypatch, games, already_sent=(), subs=(), send=None):
    cur = _Cursor(already_sent, subs)

    def fake_execute_values(cursor, query, rows, fetch=False):
        fresh = [(k,) for (k,) in rows if k not in cursor.already_sent]
        cursor.already_sent.update(k for (k,) in rows)
        return fresh

    monkeypatch.setattr(n.psycopg2, "connect", lambda url: _Conn(cur))
    monkeypatch.setattr(n.psycopg2.extras, "execute_values", fake_execute_values)
    sent = []
    def default_send(sub, payload, ttl=None):
        sent.append((sub["endpoint"], payload["title"], ttl))
        return 201

    monkeypatch.setattr(push, "send", send or default_send)
    count = n.run(now=NOW, fetch=lambda: {"games": games})
    return count, sent, cur


SUB = {"endpoint": "https://fcm.googleapis.com/x", "p256dh": "k", "auth": "a"}


class TestRun:
    def test_sends_a_new_goal_to_followers(self, monkeypatch):
        count, sent, _ = _run(monkeypatch, [_game("LIVE", [_goal("PIT", 1, "05:00", 1, 0)])], subs=[SUB])

        assert count == 1 and sent == [(SUB["endpoint"], "🚨 PIT goal! PIT 1, CBJ 0", 15 * 60)]

    def test_never_sends_the_same_event_twice(self, monkeypatch):
        count, sent, _ = _run(
            monkeypatch, [_game("LIVE", [_goal("PIT", 1, "05:00", 1, 0)])],
            already_sent={"goal:2026020068:1:05:00:PIT"}, subs=[SUB],
        )

        assert count == 0 and sent == []

    def test_no_live_games_means_no_database_work(self, monkeypatch):
        monkeypatch.setattr(n.psycopg2, "connect", lambda url: (_ for _ in ()).throw(AssertionError("connected")))

        assert n.run(now=NOW, fetch=lambda: {"games": [_game("FUT")]}) == 0

    def test_removes_subscriptions_the_browser_dropped(self, monkeypatch):
        def gone(sub, payload, ttl=None):
            raise push.SubscriptionGone("410")

        _, _, cur = _run(monkeypatch, [_game("LIVE", [_goal("PIT", 1, "05:00", 1, 0)])], subs=[SUB], send=gone)

        assert ("DELETE FROM push_subscriptions WHERE endpoint = %s", (SUB["endpoint"],)) in cur.sql


    def test_finals_get_a_longer_ttl_than_goals(self, monkeypatch):
        _, sent, _ = _run(monkeypatch, [_game("FINAL", away_score=2, home_score=3)], subs=[SUB])

        assert sent == [(SUB["endpoint"], "Final: PIT 2, CBJ 3", 3 * 60 * 60)]
