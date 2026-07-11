"""GET / and GET /teams and GET /playoff-odds."""


class TestRoot:
    def test_root_ok(self, client, db_router):
        # No DB call should happen for the health-check route.
        response = client.get("/")

        assert response.status_code == 200
        assert response.json() == {
            "status": "ok",
            "message": "NHL Stats Dashboard API is running",
            "version": "0.1.0",
        }
        assert db_router.calls == []


class TestListTeams:
    def test_happy_path(self, client, db_router, team_row):
        db_router.when("from teams order by team_name", [team_row])

        response = client.get("/teams")

        assert response.status_code == 200
        body = response.json()
        assert body == [team_row]

    def test_empty_result(self, client, db_router):
        db_router.when("from teams order by team_name", [])

        response = client.get("/teams")

        assert response.status_code == 200
        assert response.json() == []


class TestPlayoffOdds:
    def test_happy_path(self, client, db_router, playoff_odds_row):
        db_router.when("from playoff_odds po", [playoff_odds_row])

        response = client.get("/playoff-odds")

        assert response.status_code == 200
        body = response.json()
        assert len(body) == 1
        assert body[0]["team_abbrev"] == "BUF"
        assert body[0]["playoff_pct"] == 1.0

    def test_empty_result(self, client, db_router):
        db_router.when("from playoff_odds po", [])

        response = client.get("/playoff-odds")

        assert response.status_code == 200
        assert response.json() == []
