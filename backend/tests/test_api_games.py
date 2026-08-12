def test_games_today_returns_live_feed(client, monkeypatch):
    import api

    games = [{"id": 2026020001, "gameState": "LIVE"}]
    monkeypatch.setattr(api, "today_games", lambda: games)
    response = client.get("/games/today")
    assert response.status_code == 200
    assert response.json() == {"games": games}


def test_games_by_date_returns_historical_feed(client, monkeypatch):
    import api

    games = [{"id": 2023020001, "gameState": "OFF"}]
    monkeypatch.setattr(api, "games_on_date", lambda game_date: games)
    response = client.get("/games/date/2023-10-10")
    assert response.status_code == 200
    assert response.json() == {"games": games}


def test_game_boxscore_returns_gamecenter_data(client, monkeypatch):
    import api

    boxscore = {"id": 2026020001, "gameState": "FINAL", "awayTeam": {"score": 3}}
    monkeypatch.setattr(api, "game_boxscore", lambda game_id: boxscore)
    response = client.get("/games/2026020001/boxscore")
    assert response.status_code == 200
    assert response.json() == boxscore


def test_game_boxscore_rejects_invalid_id(client):
    response = client.get("/games/0/boxscore")
    assert response.status_code == 422
