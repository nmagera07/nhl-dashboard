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
            "tag": "goal-2026020068-2-1",
        }

    def test_two_goals_posted_together_both_alert(self):
        # The NHL feed sometimes adds two goals at once; only the newest used to alert.
        game = _game("LIVE", [_goal("PIT", 1, "05:00", 1, 0), _goal("CBJ", 1, "06:10", 1, 1, assists=())])

        candidates, claim_only = n.events_for([game], NOW)

        assert [e["key"] for e in candidates] == ["goal:2026020068:PIT:1-0", "goal:2026020068:CBJ:1-1"]  # oldest first
        assert claim_only == []

    def test_an_outage_backlog_sends_only_the_newest_few(self):
        goals = [_goal("PIT", 1, f"0{i}:00", i, 0) for i in range(1, 6)]
        candidates, claim_only = n.events_for([_game("LIVE", goals)], NOW)
        assert [e["key"].split(":")[-1] for e in candidates] == ["3-0", "4-0", "5-0"]
        assert [e["key"].split(":")[-1] for e in claim_only] == ["1-0", "2-0"]

    def test_puck_drop_in_the_first_minutes_only(self):
        def live(seconds_left, period=1):
            return {**_game("LIVE"), "periodDescriptor": {"number": period}, "clock": {"secondsRemaining": seconds_left}}

        (start,), _ = n.events_for([live(1150)], NOW)
        assert start["key"] == "start:2026020068" and start["kind"] == "goals" and start["ttl"] == 900
        assert start["payload"]["title"] == "🏒 Puck drop: PIT @ CBJ" and start["payload"]["url"] == "/games/2026020068"
        assert n.events_for([live(800)], NOW) == ([], [])  # 13 minutes in: too late to announce
        assert n.events_for([live(1150, period=2)], NOW) == ([], [])
        assert n.events_for([{**_game("PRE"), "periodDescriptor": {"number": 1}, "clock": {"secondsRemaining": 1200}}], NOW) == ([], [])

    def test_a_corrected_goal_time_is_the_same_goal(self):
        # The NHL posts a goal, then fixes its time a few seconds later: one alert, not two.
        first = n.events_for([_game("LIVE", [_goal("CHI", 1, "17:49", 1, 2)])], NOW)[0][0]
        fixed = n.events_for([_game("LIVE", [_goal("CHI", 1, "17:50", 1, 2)])], NOW)[0][0]
        assert first["key"] == fixed["key"]

    def test_each_goal_is_its_own_notification(self):
        game = _game("LIVE", [_goal("PIT", 1, "05:00", 1, 0), _goal("CBJ", 1, "06:10", 1, 1)])
        (older, newest), _ = n.events_for([game], NOW)
        final = n.final_event(_game("FINAL", away_score=1, home_score=1))
        assert len({newest["payload"]["tag"], older["payload"]["tag"], final["payload"]["tag"]}) == 3

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
    def default_send(sub, payload, ttl=None, urgency=None):
        sent.append((sub["endpoint"], payload["title"], ttl))
        return 201

    monkeypatch.setattr(push, "send", send or default_send)
    count = n.run(now=NOW, fetch=lambda: {"games": games})
    return count, sent, cur


SUB = {"endpoint": "https://fcm.googleapis.com/x", "p256dh": "k", "auth": "a"}


class TestRun:
    def test_sends_a_new_goal_to_followers(self, monkeypatch):
        count, sent, _ = _run(monkeypatch, [_game("LIVE", [_goal("PIT", 1, "05:00", 1, 0)])], subs=[SUB])

        assert count == 1 and sent == [(SUB["endpoint"], "🚨 PIT goal! PIT 1, CBJ 0", 60 * 60)]

    def test_never_sends_the_same_event_twice(self, monkeypatch):
        count, sent, _ = _run(
            monkeypatch, [_game("LIVE", [_goal("PIT", 1, "05:00", 1, 0)])],
            already_sent={"goal:2026020068:PIT:1-0"}, subs=[SUB],
        )

        assert count == 0 and sent == []

    def test_no_live_games_means_no_database_work(self, monkeypatch):
        monkeypatch.setattr(n.psycopg2, "connect", lambda url: (_ for _ in ()).throw(AssertionError("connected")))

        assert n.run(now=NOW, fetch=lambda: {"games": [_game("FUT")]}) == 0

    def test_removes_subscriptions_the_browser_dropped(self, monkeypatch):
        def gone(sub, payload, ttl=None, urgency=None):
            raise push.SubscriptionGone("410")

        _, _, cur = _run(monkeypatch, [_game("LIVE", [_goal("PIT", 1, "05:00", 1, 0)])], subs=[SUB], send=gone)

        assert ("DELETE FROM push_subscriptions WHERE endpoint = %s", (SUB["endpoint"],)) in cur.sql


    def test_finals_get_a_longer_ttl_than_goals(self, monkeypatch):
        _, sent, _ = _run(monkeypatch, [_game("FINAL", away_score=2, home_score=3)], subs=[SUB])

        assert sent == [(SUB["endpoint"], "Final: PIT 2, CBJ 3", 3 * 60 * 60)]


class _ReminderCursor(_Cursor):
    def execute(self, query, params=None):
        super().execute(query, params)
        if "FROM push_events_sent" in query:
            self._one = (1,) if params[0] in self.already_sent else None

    def fetchone(self):
        return self._one


SWING = {"available": True, "goal": {"scorer": "R. Rakell", "team": "PIT", "effect": "ties it",
                                     "when": "1:06 left in the 3rd", "before": 0.0706, "after": 0.5473}}
MORNING = datetime(2026, 10, 25, 14, 30, tzinfo=timezone.utc)  # 10:30 AM ET


def _remind(monkeypatch, now=MORNING, swing=SWING, already_sent=()):
    cur = _ReminderCursor(already_sent, [SUB])

    def fake_execute_values(cursor, query, rows, fetch=False):
        fresh = [(k,) for (k,) in rows if k not in cursor.already_sent]
        cursor.already_sent.update(k for (k,) in rows)
        return fresh

    monkeypatch.setattr(n.psycopg2, "connect", lambda url: _Conn(cur))
    monkeypatch.setattr(n.psycopg2.extras, "execute_values", fake_execute_values)
    sent = []
    monkeypatch.setattr(push, "send", lambda sub, payload, ttl=None, urgency=None: sent.append(payload) or 201)
    asked = []
    count = n.creator_reminder(now=now, fetch=lambda day: asked.append(day) or swing)
    return count, sent, asked, cur


class TestCreatorReminder:
    def test_the_morning_after_tells_the_creator_the_swing_is_ready(self, monkeypatch):
        count, sent, asked, cur = _remind(monkeypatch)
        assert count == 1 and asked == ["2026-10-24"]
        assert sent[0]["title"] == "Swing of the Night is ready"
        assert sent[0]["body"] == "R. Rakell ties it with 1:06 left in the 3rd · PIT 7% → 55%. Tap to post it."
        assert sent[0]["url"] == "/post-kit?date=2026-10-24"
        assert any("WHERE is_creator" in q for q, _ in cur.sql)  # the creator's devices only

    def test_once_a_day(self, monkeypatch):
        count, sent, asked, _ = _remind(monkeypatch, already_sent={"swing-ready:2026-10-24"})
        assert (count, sent, asked) == (0, [], [])

    def test_only_in_the_morning_and_not_after_a_night_without_games(self, monkeypatch):
        assert _remind(monkeypatch, now=datetime(2026, 10, 25, 3, 0, tzinfo=timezone.utc))[0] == 0
        count, sent, _, cur = _remind(monkeypatch, swing={"available": False})
        assert (count, sent) == (0, []) and "swing-ready:2026-10-24" in cur.already_sent  # claimed: don't ask again


class TestDeliveryLog:
    def test_every_push_is_logged_with_what_the_push_service_said(self, monkeypatch):
        _, _, cur = _run(monkeypatch, [_game("LIVE", [_goal("PIT", 1, "05:00", 1, 0)])], subs=[SUB])
        logged = [p for q, p in cur.sql if "INSERT INTO push_deliveries" in q]
        assert len(logged) == 1
        key, device, status, outcome, ttl = logged[0]
        assert key.startswith("goal:") and device == n.device_label(SUB["endpoint"])
        assert (status, outcome) == (201, "accepted")

    def test_a_gone_subscription_is_logged_and_removed(self, monkeypatch):
        def gone(sub, payload, ttl=None, urgency=None):
            raise push.SubscriptionGone("410")

        _, _, cur = _run(monkeypatch, [_game("LIVE", [_goal("PIT", 1, "05:00", 1, 0)])], subs=[SUB], send=gone)
        logged = [p for q, p in cur.sql if "INSERT INTO push_deliveries" in q]
        assert logged[0][2:4] == (None, "gone")

    def test_device_label_tells_devices_apart_without_the_whole_endpoint(self):
        assert n.device_label("https://fcm.googleapis.com/fcm/send/abcdefXYZ123") == "fcm.googleapis.com ...XYZ123"


def test_precompute_asks_the_api_for_last_nights_swing():
    asked = []

    class Ok:
        def raise_for_status(self):
            pass

    now = datetime(2026, 10, 27, 7, 40, tzinfo=timezone.utc)  # 3:40 AM ET
    assert n.precompute_swing(now, get=lambda url, timeout: asked.append(url) or Ok())
    assert asked == [n.SWING_URL.format(day="2026-10-26")]

    def down(url, timeout):
        raise n.requests.ConnectionError()
    assert not n.precompute_swing(now, get=down)
