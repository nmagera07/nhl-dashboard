"""GET /, GET /health, GET /teams, and GET /playoff-odds."""


class TestRoot:
    def test_root_ok(self, client, db_router):
        # GET / is a static payload -- no DB call. GET /health is the one
        # that actually exercises the database (see TestHealth below).
        response = client.get("/")

        assert response.status_code == 200
        assert response.json() == {
            "status": "ok",
            "message": "NHL Stats Dashboard API is running",
            "version": "0.1.0",
        }
        assert db_router.calls == []


class TestHealth:
    def test_healthy_when_the_database_responds(self, client, db_router):
        db_router.when("select 1", [])

        response = client.get("/health")

        assert response.status_code == 200
        assert response.json() == {"status": "ok", "database": "connected"}

    def test_returns_503_when_the_database_is_unreachable(self, client, db_router):
        def unreachable(params):
            raise Exception("connection refused")

        db_router.when("select 1", unreachable)

        response = client.get("/health")

        assert response.status_code == 503
        assert response.json()["detail"] == "Database unreachable"

    def test_exempt_from_the_default_rate_limit(self, client, db_router):
        # Monitors/probes can poll far more often than 60/minute -- confirm
        # /health doesn't trip the same limit that /teams would.
        db_router.when("select 1", [])

        statuses = [client.get("/health").status_code for _ in range(70)]

        assert all(s == 200 for s in statuses)


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
