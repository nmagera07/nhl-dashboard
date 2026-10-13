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


class TestPlayoffOddsWhy:
    def test_returns_each_teams_breakdown_from_the_latest_run(self, client, db_router):
        why = {"PIT": {"goals": 0.06, "xg": 0.0, "last_season": 0.1, "rating": 0.16}}
        payload = {"season_id": 20262027, "as_of_date": "2026-10-11", "model": {"version": "v2.1"}, "why": why}
        db_router.when("from season_sim_inputs", [{"payload": payload}])

        response = client.get("/playoff-odds/why")

        assert response.status_code == 200
        assert response.json() == {"season_id": 20262027, "as_of_date": "2026-10-11", "model_version": "v2.1", "teams": why}

    def test_an_older_run_without_a_breakdown_returns_no_teams(self, client, db_router):
        db_router.when("from season_sim_inputs", [{"payload": {"season_id": 20262027, "as_of_date": "2026-10-11", "model": {}}}])

        assert client.get("/playoff-odds/why").json()["teams"] == {}

    def test_404_before_the_first_run(self, client, db_router):
        db_router.when("from season_sim_inputs", [])

        assert client.get("/playoff-odds/why").status_code == 404


class TestPredictionTrackRecord:
    def test_scores_this_seasons_graded_predictions_and_counts_pending(self, client, db_router):
        db_router.when("WHERE home_won IS NULL", {"n": 3})
        db_router.when("FROM game_predictions", [
            {"game_id": 1, "game_date": "2026-10-10", "home_abbrev": "PIT", "away_abbrev": "DAL",
             "home_win_prob": 0.55, "home_score": 2, "away_score": 1, "ended": "SO", "home_won": True,
             "model_version": "v2.1", "source": "digest"},
        ])
        body = client.get("/predictions/track-record").json()
        assert body["games"] == 1 and body["favorite_won"] == 1.0 and body["pending"] == 3
        assert body["recent"][0]["home"] == "PIT"


def _sim_team(conf, w, l, otl):
    return {"points": 2 * w + otl, "wins": w, "losses": l, "ot_losses": otl, "regulation_wins": w,
            "division": conf[0], "conference": conf}


class TestPlayoffLine:
    def test_returns_the_sim_line_and_each_teams_record(self, client, db_router):
        payload = {
            "season_id": 20262027, "as_of_date": "2026-10-13", "games": [["2026-10-14", "BUF", "BOS"]],
            "cutline": {"Eastern": {"p25": 92, "p50": 95, "p75": 98}},
            "teams": {"BUF": _sim_team("Eastern", 3, 3, 0), "NEW": _sim_team("Eastern", 0, 0, 0)},
        }
        db_router.when("from season_sim_inputs", [{"payload": payload}])

        body = client.get("/playoff-line").json()

        assert body["source"] == "sim"
        assert body["as_of_date"] == "2026-10-13"
        assert body["games_remaining"] == 1
        assert body["cutline"] == {"Eastern": {"p25": 92, "p50": 95, "p75": 98}}
        assert body["teams"]["BUF"] == {"conference": "Eastern", "gp": 6, "pts": 6, "otl": 0, "point_pctg": 0.5}
        assert body["teams"]["NEW"]["point_pctg"] is None

    def test_older_payloads_fall_back_to_projecting_the_eighth_team(self, client, db_router):
        teams = {f"T{i}": _sim_team("Western", i, 10 - i, 0) for i in range(10)}
        db_router.when("from season_sim_inputs", [{"payload": {"as_of_date": "2026-10-13", "teams": teams, "games": []}}])

        body = client.get("/playoff-line").json()

        # 8th best is T2: 4 pts in 10 GP -> .200 x 164 = 33
        assert body["source"] == "projection"
        assert body["cutline"]["Western"] == {"p25": 33, "p50": 33, "p75": 33}

    def test_404_before_the_first_run(self, client, db_router):
        db_router.when("from season_sim_inputs", [])

        assert client.get("/playoff-line").status_code == 404

    def test_is_cacheable_daily_data(self, client, db_router):
        import api
        assert api._daily_cacheable("/playoff-line")
