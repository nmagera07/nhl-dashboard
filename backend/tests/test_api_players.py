"""GET /players/leaders and GET /players/{player_id}."""


class TestPlayerLeaders:
    def test_happy_path(self, client, db_router, roster_skater_row):
        leader_row = dict(roster_skater_row, team_name="Colorado Avalanche", team_logo_url="https://x/COL.svg")
        db_router.when("t.logo_url as team_logo_url", [leader_row])

        response = client.get("/players/leaders")

        assert response.status_code == 200
        body = response.json()
        assert body[0]["team_name"] == "Colorado Avalanche"
        assert body[0]["points"] == 127

    def test_empty_result(self, client, db_router):
        db_router.when("t.logo_url as team_logo_url", [])

        response = client.get("/players/leaders")

        assert response.status_code == 200
        assert response.json() == []


class TestPlayerDetail:
    def test_happy_path_nested_season_and_advanced_stats(
        self, client, db_router, player_bio_row, player_season_stat_row, player_advanced_stat_row
    ):
        db_router.when("where p.player_id = %s", player_bio_row)
        db_router.when("from player_season_stats where player_id", [player_season_stat_row])
        db_router.when("from player_advanced_stats where player_id", [player_advanced_stat_row])
        db_router.when("from player_career_totals where player_id", [])

        response = client.get("/players/8477492")

        assert response.status_code == 200
        body = response.json()
        assert body["first_name"] == "Nathan"
        assert body["season_stats"] == [player_season_stat_row]
        assert body["advanced_stats"] == [player_advanced_stat_row]

    def test_player_with_no_season_or_advanced_stats_returns_empty_nested_lists(
        self, client, db_router, player_bio_row
    ):
        # A real, found player (e.g. a rookie just added to the roster)
        # can legitimately have zero rows in either sub-table -- that's
        # not an error, it's an empty list nested inside a 200.
        db_router.when("where p.player_id = %s", player_bio_row)
        db_router.when("from player_season_stats where player_id", [])
        db_router.when("from player_advanced_stats where player_id", [])
        db_router.when("from player_career_totals where player_id", [])

        response = client.get("/players/8477492")

        assert response.status_code == 200
        body = response.json()
        assert body["season_stats"] == []
        assert body["advanced_stats"] == []

    def test_unknown_player_id_404s(self, client, db_router):
        db_router.when("where p.player_id = %s", None)

        response = client.get("/players/99999999")

        assert response.status_code == 404
        assert "99999999" in response.json()["detail"]
        # Neither follow-up query should run once the player itself 404s.
        assert not any("player_season_stats" in q.lower() for q, _ in db_router.calls)
        assert not any("player_advanced_stats" in q.lower() for q, _ in db_router.calls)
        assert not any("player_career_totals" in q.lower() for q, _ in db_router.calls)

    def test_career_totals_happy_path_skater(
        self,
        client,
        db_router,
        player_bio_row,
        player_career_totals_skater_row,
        player_career_totals_skater_playoffs_row,
    ):
        # A veteran skater with both a regular-season and a playoffs row.
        db_router.when("where p.player_id = %s", player_bio_row)
        db_router.when("from player_season_stats where player_id", [])
        db_router.when("from player_advanced_stats where player_id", [])
        db_router.when(
            "from player_career_totals where player_id",
            [player_career_totals_skater_row, player_career_totals_skater_playoffs_row],
        )

        response = client.get("/players/8477492")

        assert response.status_code == 200
        career_totals = response.json()["career_totals"]
        assert career_totals["regular_season"]["points"] == 1142
        assert career_totals["regular_season"]["goals"] == 420
        assert career_totals["playoffs"]["points"] == 130
        assert career_totals["playoffs"]["goals"] == 48

    def test_career_totals_happy_path_goalie(
        self, client, db_router, player_bio_row, player_career_totals_goalie_row
    ):
        # A goalie with only a regular-season row (no playoffs row).
        db_router.when("where p.player_id = %s", player_bio_row)
        db_router.when("from player_season_stats where player_id", [])
        db_router.when("from player_advanced_stats where player_id", [])
        db_router.when(
            "from player_career_totals where player_id", [player_career_totals_goalie_row]
        )

        response = client.get("/players/8477492")

        assert response.status_code == 200
        career_totals = response.json()["career_totals"]
        assert career_totals["regular_season"]["wins"] == 93
        assert career_totals["regular_season"]["goals_against_avg"] == 2.68124
        assert career_totals["regular_season"]["save_pctg"] == 0.909223
        assert career_totals["playoffs"] is None

    def test_player_with_no_career_totals_rows_returns_both_none(
        self, client, db_router, player_bio_row
    ):
        # Ingestion hasn't run for this player yet (or a rookie who's
        # never made the playoffs) -- zero rows in player_career_totals
        # is valid, not an error, and career_totals is still an object
        # with both sub-fields explicitly None, not omitted.
        db_router.when("where p.player_id = %s", player_bio_row)
        db_router.when("from player_season_stats where player_id", [])
        db_router.when("from player_advanced_stats where player_id", [])
        db_router.when("from player_career_totals where player_id", [])

        response = client.get("/players/8477492")

        assert response.status_code == 200
        assert response.json()["career_totals"] == {"regular_season": None, "playoffs": None}

    def test_non_integer_player_id_is_rejected_before_touching_the_db(self, client, db_router):
        # player_id: int in the route signature -- FastAPI's own request
        # validation should reject this with a 422 before the endpoint
        # function (and therefore the DB layer) ever runs.
        response = client.get("/players/not-a-number")

        assert response.status_code == 422
        assert db_router.calls == []
