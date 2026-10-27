from datetime import date


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


def test_team_schedule_returns_the_summary(client, monkeypatch):
    import api

    summary = {"team": "PIT", "live": None, "recent": [], "upcoming": [], "plays_today": False}
    monkeypatch.setattr(api, "team_schedule", lambda abbrev: summary)
    response = client.get("/teams/PIT/schedule")
    assert response.status_code == 200
    assert response.json() == summary


def test_team_schedule_rejects_a_malformed_abbreviation(client):
    response = client.get("/teams/PITT/schedule")
    assert response.status_code == 422


def test_team_schedule_reports_an_nhl_outage(client, monkeypatch):
    import api

    def unavailable(abbrev):
        raise api.NHLGamesUnavailable("The NHL live game feed is temporarily unavailable.")

    monkeypatch.setattr(api, "team_schedule", unavailable)
    response = client.get("/teams/PIT/schedule")
    assert response.status_code == 503


class TestSharePreview:
    GAME = {"gameState": "FUT", "startTimeUTC": "2026-10-19T00:00:00Z", "awayTeam": {"abbrev": "PIT"}, "homeTeam": {"abbrev": "COL"}}

    def test_share_text_and_image(self, client, db_router, monkeypatch):
        import api
        monkeypatch.setattr(api, "game_boxscore", lambda game_id: self.GAME)
        db_router.when("from game_predictions", {"home_win_prob": 0.663})
        body = client.get("/games/2026020150/share").json()
        assert body["url"] == "https://puckpulse.io/games/2026020150"
        assert body["image"].endswith("/og/game/2026020150.png") and "66% chance" in body["description"]
        image = client.get("/og/game/2026020150.png")
        assert image.status_code == 200 and image.headers["content-type"] == "image/png"
        assert image.content[:8] == b"\x89PNG\r\n\x1a\n"


    def test_live_game_preview_carries_the_curve(self, client, db_router, monkeypatch):
        import api
        live = {"gameState": "LIVE", "periodDescriptor": {"number": 2},
                "awayTeam": {"abbrev": "FLA", "score": 1, "id": 13}, "homeTeam": {"abbrev": "OTT", "score": 2, "id": 9}}
        pbp = {"gameType": 2, "gameState": "LIVE", "homeTeam": {"id": 9, "abbrev": "OTT", "score": 2},
               "awayTeam": {"id": 13, "abbrev": "FLA", "score": 1}, "rosterSpots": [],
               "plays": [{"typeDescKey": "goal", "timeInPeriod": "09:34", "eventId": 5, "details": {"eventOwnerTeamId": 9},
                          "periodDescriptor": {"number": 2, "periodType": "REG"}}]}
        monkeypatch.setattr(api, "game_boxscore", lambda game_id: live)
        monkeypatch.setattr(api, "game_play_by_play", lambda game_id: pbp)
        db_router.when("from game_predictions", {"home_win_prob": 0.52, "home_goals": 2.9, "away_goals": 2.8})
        body = client.get("/games/2026020153/share").json()
        assert body["description"].startswith("Biggest swing: OTT (OTT), 2nd 9:34 · OTT")
        assert client.get("/og/game/2026020153.png").status_code == 200

    def test_preview_survives_the_play_by_play_being_down(self, client, db_router, monkeypatch):
        import api
        final = {"gameState": "OFF", "awayTeam": {"abbrev": "FLA", "score": 1}, "homeTeam": {"abbrev": "OTT", "score": 3}}
        monkeypatch.setattr(api, "game_boxscore", lambda game_id: final)

        def down(game_id):
            raise api.NHLGamesUnavailable("down")

        monkeypatch.setattr(api, "game_play_by_play", down)
        db_router.when("from game_predictions", {"home_win_prob": 0.52})
        assert client.get("/games/2026020153/share").json()["description"] == "Box score and highlights on PuckPulse."
        assert client.get("/og/game/2026020153.png").status_code == 200


class TestTeamSharePreview:
    def test_team_share_text(self, client, db_router):
        db_router.when("from teams t", {"team_name": "Buffalo Sabres", "wins": 3, "losses": 3, "ot_losses": 0, "points": 6})
        db_router.when("from playoff_odds", {"playoff_pct": 0.177})
        body = client.get("/teams/buf/share").json()
        assert body["url"] == "https://puckpulse.io/teams/BUF"
        assert body["title"] == "Buffalo Sabres: 17.7% to make the playoffs"
        assert "image" not in body  # the site's card image is used

    def test_unknown_team_is_404(self, client):
        assert client.get("/teams/XYZ/share").status_code == 404
        assert client.get("/teams/BUFF/share").status_code == 422


class TestSwingOfTheNight:
    GAMES = [{"id": 2026020149, "gameState": "OFF", "gameType": 2, "gameOutcome": {"lastPeriodType": "SO"},
              "awayTeam": {"abbrev": "DET", "score": 3}, "homeTeam": {"abbrev": "SEA", "score": 4}},
             {"id": 2026020150, "gameState": "FUT", "gameType": 2, "awayTeam": {"abbrev": "A"}, "homeTeam": {"abbrev": "B"}}]
    CURVE = {"available": True, "playoff": False, "points": [[0, 0.55], [3583, 0.98], [3583, 0.52], [3900, 1.0]],
             "goals": [{"second": 1000, "team": "home", "scorer": "J. Eberle", "before": 0.55, "after": 0.7},
                       {"second": 3583, "team": "away", "scorer": "A. DeBrincat", "before": 0.98, "after": 0.52}]}

    def setup(self, monkeypatch):
        import api
        calls = []
        monkeypatch.setattr(api, "games_on_date", lambda day: self.GAMES)
        monkeypatch.setattr(api, "_win_curve", lambda game_id: calls.append(game_id) or self.CURVE)
        return calls

    def test_last_nights_swing_from_the_scorers_side(self, client, monkeypatch):
        calls = self.setup(monkeypatch)
        body = client.get("/swing-of-the-night?date=2026-10-20").json()
        assert calls == [2026020149]  # finished games only
        assert body["goal"] == {"scorer": "A. DeBrincat", "team": "DET", "side": "away", "second": 3583,
                                "when": "0:17 left in the 3rd", "effect": "ties it", "before": 0.02, "after": 0.48}
        assert body["game"]["last_period"] == "SO"

    def test_share_card_and_image(self, client, monkeypatch):
        self.setup(monkeypatch)
        share = client.get("/swing/2026-10-20/share").json()
        assert share["title"] == "Swing of the Night, Oct 20: A. DeBrincat ties it with 0:17 left in the 3rd"
        assert share["game_id"] == 2026020149 and share["image"].endswith("/og/swing/2026-10-20.png")
        image = client.get("/og/swing/2026-10-20.png")
        assert image.status_code == 200 and image.content[:8] == b"\x89PNG\r\n\x1a\n"

    def test_a_settled_night_is_saved_and_read_back(self, client, monkeypatch, db_router):
        calls = self.setup(monkeypatch)
        monkeypatch.setattr(self, "GAMES", self.GAMES[:1])  # every game final
        saved = {}
        db_router.when("select payload from swing_of_the_night", lambda params: saved.get(params[0]))
        db_router.when("insert into swing_of_the_night", lambda params: saved.setdefault(params[0], {"payload": params[1].adapted}))
        first = client.get("/swing-of-the-night?date=2026-10-20").json()
        assert "settled" not in first and list(saved) == [date(2026, 10, 20)]
        import api
        api.daily_cache.clear()  # as after a restart
        assert client.get("/swing-of-the-night?date=2026-10-20").json() == first
        assert calls == [2026020149]  # built once; the second came from the saved row

    def test_a_night_still_playing_isnt_saved(self, client, monkeypatch, db_router):
        self.setup(monkeypatch)  # one game hasn't started
        db_router.when("select payload from swing_of_the_night", None)
        client.get("/swing-of-the-night?date=2026-10-20")
        assert not [q for q, _ in db_router.calls if "INSERT" in q]

    def test_a_night_without_games(self, client, monkeypatch):
        import api
        monkeypatch.setattr(api, "games_on_date", lambda day: [])
        assert client.get("/swing-of-the-night?date=2026-07-01").json() == {"available": False, "date": "2026-07-01"}
        assert client.get("/swing/2026-07-01/share").status_code == 404
