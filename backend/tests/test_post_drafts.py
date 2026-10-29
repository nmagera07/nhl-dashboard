"""post_drafts: last night's candidate stories, and storing the agent's pick."""

import json
from datetime import date

import requests

import post_drafts as pd

DAY = date(2026, 10, 27)
SWING = {"payload": {"games": 11, "game": {"id": 2026020188, "away": "CBJ", "home": "PHI", "away_score": 4, "home_score": 3,
                                           "last_period": "OT"},
                     "goal": {"team": "PHI", "scorer": "J. Drysdale", "effect": "ties it", "when": "0:11 left in the 3rd",
                              "before": 0.0145, "after": 0.5027}}}
GAMES = [
    {"game_id": 2026020197, "away_abbrev": "VAN", "home_abbrev": "ANA", "home_win_prob": 0.656, "away_score": 6, "home_score": 5,
     "ended": "OT", "home_won": False},
    {"game_id": 2026020196, "away_abbrev": "OTT", "home_abbrev": "VGK", "home_win_prob": 0.567, "away_score": 1, "home_score": 4,
     "ended": "REG", "home_won": True},
]
MOVERS = [{"team_abbrev": "OTT", "before": 0.5901, "after": 0.4835}, {"team_abbrev": "BOS", "before": 0.7726, "after": 0.7424}]


class Cursor:
    def __init__(self, swing=SWING, games=GAMES, movers=MOVERS):
        self.answers = {"swing_of_the_night": [swing] if swing else [], "game_predictions": games, "playoff_odds": movers}
        self.sql, self.rows = [], []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        self.sql.append((sql, params))
        self.rows = next((rows for table, rows in self.answers.items() if f"FROM {table}" in sql), [])

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows


class Conn:
    def __init__(self, cur):
        self.cur, self.commits = cur, 0

    def cursor(self, **kwargs):
        return self.cur

    def commit(self):
        self.commits += 1


def test_candidates_link_to_pages_the_site_has():
    stories = pd.candidates(Cursor(), DAY)
    assert [s["id"] for s in stories] == ["swing", "upset-2026020197", "odds-OTT"]  # BOS moved 3 points: too small
    swing, upset, odds = stories
    assert swing["link"] == "https://puckpulse.io/s/2026-10-27" and swing["image"].endswith("/og/swing/2026-10-27.png")
    assert swing["facts"]["result"] == {"winner": "CBJ", "loser": "PHI", "score": "4-3 (OT)"}
    assert (swing["facts"]["team_win_chance_before_pct"], swing["facts"]["team_win_chance_after_pct"]) == (1, 50)
    assert upset["link"] == "https://puckpulse.io/g/2026020197" and upset["facts"]["winner_pregame_win_chance_pct"] == 34
    assert upset["facts"]["result"] == {"winner": "VAN", "loser": "ANA", "score": "6-5 (OT)"}
    assert odds["link"] == "https://puckpulse.io/t/OTT" and odds["facts"]["playoff_odds_after_pct"] == 48


def test_no_upset_when_every_winner_was_likely():
    assert pd.upset_story(Cursor(games=GAMES[1:]), DAY) is None


class Response:
    def __init__(self, body):
        self.body = body

    def raise_for_status(self):
        pass

    def json(self):
        return self.body


def test_the_agents_pick_is_stored(monkeypatch):
    monkeypatch.setattr(pd, "INTELLIGENCE_URL", "https://intel.test")
    monkeypatch.setattr(pd, "DIGEST_TOKEN", "s3cret")
    sent = []

    def post(url, json, headers, timeout):
        sent.append((url, json, headers))
        return Response({"pick": "upset-2026020197", "x_text": "VAN won 6-5 in OT with a 34% chance.",
                         "reddit_title": "VAN steals one in Anaheim", "model": "Groq", "problems": [], "tools": []})

    cur = Cursor()
    assert pd.run(Conn(cur), DAY, post) == "upset-2026020197"
    url, body, headers = sent[0]
    assert url == "https://intel.test/posts/draft" and headers == {"X-Digest-Token": "s3cret"}
    assert body["date"] == "2026-10-27" and [c["id"] for c in body["candidates"]] == ["swing", "upset-2026020197", "odds-OTT"]
    assert "link" not in body["candidates"][0]  # the agent picks and writes; links and cards stay ours
    saved = next(p for s, p in cur.sql if "INSERT INTO post_drafts" in s)
    assert saved[:6] == (DAY, "upset-2026020197", "https://puckpulse.io/g/2026020197",
                         "https://nhl-dashboard-api.bravecoast-a5240643.westus2.azurecontainerapps.io/og/game/2026020197.png",
                         "VAN won 6-5 in OT with a 34% chance.", "VAN steals one in Anaheim")
    assert len(json.loads(saved[7])) == 3


def test_nothing_is_stored_without_a_passing_draft(monkeypatch):
    monkeypatch.setattr(pd, "INTELLIGENCE_URL", "https://intel.test")
    monkeypatch.setattr(pd, "DIGEST_TOKEN", "s3cret")
    for post in (lambda *a, **k: Response({"pick": None, "problems": ["These numbers aren't in the facts: 7."]}),
                 lambda *a, **k: (_ for _ in ()).throw(requests.ConnectionError("cold start")),
                 lambda *a, **k: Response({"pick": "made-up", "x_text": "x", "reddit_title": "r"})):
        cur = Cursor()
        assert pd.run(Conn(cur), DAY, post) is None
        assert not [s for s, _ in cur.sql if "INSERT INTO post_drafts" in s]


def test_a_night_without_games_drafts_nothing():
    cur = Cursor(swing=None, games=[], movers=[])
    assert pd.run(Conn(cur), DAY, lambda *a, **k: (_ for _ in ()).throw(AssertionError("asked"))) is None
