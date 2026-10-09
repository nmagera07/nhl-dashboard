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
        assert response.json() == {"status": "ok", "database": "connected", "commit": "unknown"}

    def test_reports_the_commit_the_image_was_built_from(self, client, db_router, monkeypatch):
        import api

        monkeypatch.setattr(api, "GIT_SHA", "f2c2a18")
        db_router.when("select 1", [])

        assert client.get("/health").json()["commit"] == "f2c2a18"

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


class TestPlayoffOddsHistory:
    POINTS = [
        {"as_of_date": "2026-10-08", "team_abbrev": "PIT", "playoff_pct": 0.42},
        {"as_of_date": "2026-10-09", "team_abbrev": "PIT", "playoff_pct": 0.45},
    ]

    def test_defaults_to_the_latest_season(self, client, db_router):
        db_router.when("select distinct season_id", [{"season_id": 20262027}, {"season_id": 20252026}])
        db_router.when("where season_id = %s", self.POINTS)

        response = client.get("/playoff-odds/history")

        assert response.status_code == 200
        body = response.json()
        assert body["season_id"] == 20262027
        assert body["available_seasons"] == [20262027, 20252026]
        assert [p["playoff_pct"] for p in body["points"]] == [0.42, 0.45]
        assert db_router.calls[-1][1] == (20262027,)

    def test_a_specific_season(self, client, db_router):
        db_router.when("select distinct season_id", [{"season_id": 20262027}, {"season_id": 20252026}])
        db_router.when("where season_id = %s", self.POINTS)

        response = client.get("/playoff-odds/history?season_id=20252026")

        assert response.json()["season_id"] == 20252026
        assert db_router.calls[-1][1] == (20252026,)

    def test_a_season_without_odds_returns_no_points_and_skips_the_query(self, client, db_router):
        db_router.when("select distinct season_id", [{"season_id": 20262027}])

        response = client.get("/playoff-odds/history?season_id=20102011")

        assert response.status_code == 200
        assert response.json()["points"] == []
        assert len(db_router.calls) == 1

    def test_no_odds_at_all(self, client, db_router):
        db_router.when("select distinct season_id", [])

        response = client.get("/playoff-odds/history")

        assert response.json() == {"season_id": None, "available_seasons": [], "points": []}

    def test_rejects_a_malformed_season(self, client, db_router):
        response = client.get("/playoff-odds/history?season_id=2026")

        assert response.status_code == 422
        assert db_router.calls == []


class TestSeasonSim:
    def test_returns_the_latest_inputs(self, client, db_router):
        payload = {"season_id": 20262027, "teams": {}, "games": []}
        db_router.when("from season_sim_inputs", [{"payload": payload}])

        response = client.get("/season-sim")

        assert response.status_code == 200
        assert response.json() == payload

    def test_404_before_the_first_run(self, client, db_router):
        db_router.when("from season_sim_inputs", [])

        response = client.get("/season-sim")

        assert response.status_code == 404
