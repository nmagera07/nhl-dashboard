"""era.py and GET /era/scoring."""

import era


class Resp:
    def __init__(self, rows):
        self.rows = rows

    def raise_for_status(self):
        pass

    def json(self):
        return {"data": self.rows}


def test_season_scoring_is_goals_per_team_game():
    rows = [{"goalsFor": 300, "gamesPlayed": 82}, {"goalsFor": 200, "gamesPlayed": 82}]
    assert era.season_scoring(20252026, get=lambda *a, **k: Resp(rows)) == round(500 / 164, 4)
    assert era.season_scoring(20042005, get=lambda *a, **k: Resp([])) is None  # the lockout


def test_the_table_covers_every_season_since_1917():
    seasons = era.load()["seasons"]
    assert min(seasons) == "19171918" and "20042005" not in seasons
    assert all(1.0 < v < 5.0 for v in seasons.values())


def test_endpoint_adds_this_season_live(client, monkeypatch):
    monkeypatch.setattr(era, "season_scoring", lambda season_id: 3.1)
    body = client.get("/era/scoring").json()
    assert body["reference_season"] == int(max(era.load()["seasons"]))
    assert len(body["seasons"]) == len(era.load()["seasons"]) + 1
