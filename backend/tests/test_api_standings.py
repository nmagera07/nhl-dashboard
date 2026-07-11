"""
GET /standings/latest, GET /standings/{team_abbrev}, and
GET /standings/{team_abbrev}/seasons.

Note: FastAPI parses `start`/`end` into datetime.date objects (per the
`Optional[date]` type hint) before the endpoint body ever runs, so
they arrive at the DB layer as date objects, not raw strings.

team_history (GET /standings/{team_abbrev}) is the second endpoint whose
404-vs-empty-list behavior was fixed -- these tests lock in: bogus
abbreviation -> 404 (checked against `teams` first, snapshots query never
runs), real team with zero snapshot rows -> 200 [].

team_season_history (.../seasons) was confirmed correct as-is and is left
untouched -- always 200, never 404, even for a bogus abbreviation.
"""


class TestLatestStandings:
    def test_happy_path(self, client, db_router, standings_row):
        db_router.when("where s.snapshot_date =", [standings_row])

        response = client.get("/standings/latest")

        assert response.status_code == 200
        body = response.json()
        assert body[0]["team_abbrev"] == "COL"
        assert body[0]["points"] == 121

    def test_empty_result(self, client, db_router):
        db_router.when("where s.snapshot_date =", [])

        response = client.get("/standings/latest")

        assert response.status_code == 200
        assert response.json() == []


class TestTeamHistory:
    def test_happy_path_real_team_with_data(self, client, db_router, standings_row):
        db_router.when("select 1 from teams where team_abbrev", {"?column?": 1})
        db_router.when("where s.team_abbrev = %s", [standings_row])

        response = client.get("/standings/COL")

        assert response.status_code == 200
        body = response.json()
        assert len(body) == 1
        assert body[0]["team_name"] == "Colorado Avalanche"

    def test_real_team_with_no_snapshots_returns_200_empty_list(self, client, db_router):
        db_router.when("select 1 from teams where team_abbrev", {"?column?": 1})
        db_router.when("where s.team_abbrev = %s", [])

        response = client.get("/standings/XXT")

        assert response.status_code == 200
        assert response.json() == []

    def test_bogus_team_abbreviation_404s(self, client, db_router):
        db_router.when("select 1 from teams where team_abbrev", None)

        response = client.get("/standings/ZZZ")

        assert response.status_code == 404
        assert "ZZZ" in response.json()["detail"]
        # The snapshots query must never run once the existence check fails.
        assert not any("where s.team_abbrev" in q.lower() for q, _ in db_router.calls)

    def test_start_end_query_params_are_passed_through(self, client, db_router):
        from datetime import date

        seen_params = []

        def capture(params):
            seen_params.append(params)
            return []

        db_router.when("select 1 from teams where team_abbrev", {"?column?": 1})
        db_router.when("where s.team_abbrev = %s", capture)

        response = client.get("/standings/COL?start=2026-01-01&end=2026-04-01")

        assert response.status_code == 200
        assert seen_params == [("COL", date(2026, 1, 1), date(2026, 4, 1))]

    def test_malformed_date_param_is_rejected_before_touching_the_db(self, client, db_router):
        db_router.when("select 1 from teams where team_abbrev", {"?column?": 1})

        response = client.get("/standings/COL?start=not-a-date")

        assert response.status_code == 422
        assert db_router.calls == []


class TestTeamSeasonHistory:
    def test_happy_path(self, client, db_router, season_final_standing_row):
        db_router.when("from season_final_standings", [season_final_standing_row])

        response = client.get("/standings/PIT/seasons")

        assert response.status_code == 200
        body = response.json()
        assert body[0]["team_abbrev"] == "PIT"
        assert body[0]["made_playoffs"] is True

    def test_bogus_abbreviation_still_returns_200_empty_not_404(self, client, db_router):
        # Confirmed-correct-as-is: this table intentionally has no FK to
        # `teams` (relocated franchises like 'ARI' are valid here despite
        # not being in `teams`), so there's no existence check to fail --
        # any abbreviation with zero rows just comes back as [].
        db_router.when("from season_final_standings", [])

        response = client.get("/standings/ZZZ/seasons")

        assert response.status_code == 200
        assert response.json() == []
        # No teams-existence check should have run for this endpoint.
        assert not any("select 1 from teams" in q.lower() for q, _ in db_router.calls)

    def test_historical_relocated_abbreviation_returns_data(self, client, db_router, season_final_standing_row):
        # 'ARI' (Arizona Coyotes, since relocated to Utah) is absent from
        # `teams` but has real rows here -- this is the case that would
        # break if this endpoint were changed to validate against `teams`.
        ari_row = dict(season_final_standing_row, team_abbrev="ARI")
        db_router.when("from season_final_standings", [ari_row])

        response = client.get("/standings/ARI/seasons")

        assert response.status_code == 200
        assert response.json()[0]["team_abbrev"] == "ARI"
