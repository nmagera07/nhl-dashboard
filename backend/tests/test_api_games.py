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


def test_games_calendar_returns_the_month(client, monkeypatch):
    import api

    calendar = {"season_start": "2026-09-29", "season_end": "2027-06-10", "days": [{"date": "2026-10-06", "games": 9}]}
    seen = []
    monkeypatch.setattr(api, "month_calendar", lambda year, month: seen.append((year, month)) or calendar)

    response = client.get("/games/calendar/2026-10")

    assert response.status_code == 200
    assert response.json() == calendar
    assert seen == [(2026, 10)]


def test_games_calendar_rejects_a_malformed_month(client):
    assert client.get("/games/calendar/2026-13").status_code == 422
    assert client.get("/games/calendar/october").status_code == 422
