"""GET /players/leaders and GET /players/{player_id}."""

import pytest

from response_models import LEADER_TABLE_FIELDS, PlayerLeader


@pytest.fixture(autouse=True)
def no_war_yet(db_router):
    """Player pages also ask for WAR (tests/test_war.py covers it); here there's none yet."""
    db_router.when("from player_war", None)


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

    @staticmethod
    def _leader_rows(roster_skater_row):
        skater = dict(roster_skater_row, team_name="Colorado Avalanche", team_logo_url="https://x/COL.svg")
        second = dict(skater, player_id=8478402, first_name="Connor", last_name="McDavid", team_abbrev="EDM",
                      team_name="Edmonton Oilers", team_logo_url=None, points=100)
        goalie = dict(skater, player_id=8476945, first_name="Connor", last_name="Hellebuyck", position_code="G",
                      team_abbrev="WPG", team_name="Winnipeg Jets", goals=None, assists=None, points=None,
                      wins=47, losses=12, ot_losses=3, goals_against_avg=2.0, save_pctg=0.925, shutouts=8)
        return [skater, second, goalie]

    def test_default_returns_every_player_leader_field(self, client, db_router, roster_skater_row):
        db_router.when("t.logo_url as team_logo_url", self._leader_rows(roster_skater_row))

        body = client.get("/players/leaders").json()

        assert len(PlayerLeader.model_fields) == 39
        for row in body:
            assert set(row) == set(PlayerLeader.model_fields)

    def test_view_full_matches_default(self, client, db_router, roster_skater_row):
        db_router.when("t.logo_url as team_logo_url", self._leader_rows(roster_skater_row))

        default = client.get("/players/leaders")
        full = client.get("/players/leaders?view=full")

        assert full.status_code == 200
        assert full.json() == default.json()

    def test_view_table_has_only_table_fields(self, client, db_router, roster_skater_row):
        db_router.when("t.logo_url as team_logo_url", self._leader_rows(roster_skater_row))

        response = client.get("/players/leaders?view=table")

        assert response.status_code == 200
        assert len(LEADER_TABLE_FIELDS) == 21  # +avg_toi_seconds (TOI column), +war (WAR column)
        for row in response.json():
            assert set(row) == set(LEADER_TABLE_FIELDS)

    def test_view_table_same_rows_order_and_values_as_full(self, client, db_router, roster_skater_row):
        db_router.when("t.logo_url as team_logo_url", self._leader_rows(roster_skater_row))

        full = client.get("/players/leaders").json()
        table = client.get("/players/leaders?view=table").json()

        assert len(table) == len(full) == 3
        assert [r["player_id"] for r in table] == [r["player_id"] for r in full]
        for t, f in zip(table, full):
            assert t == {k: f[k] for k in LEADER_TABLE_FIELDS}

    def test_unknown_view_is_422(self, client, db_router):
        db_router.when("t.logo_url as team_logo_url", [])

        assert client.get("/players/leaders?view=bogus").status_code == 422

    def test_empty_result_both_views(self, client, db_router):
        db_router.when("t.logo_url as team_logo_url", [])

        for url in ("/players/leaders?view=full", "/players/leaders?view=table"):
            response = client.get(url)
            assert response.status_code == 200
            assert response.json() == []


class TestPlayerDetail:
    def test_happy_path_nested_season_and_advanced_stats(
        self, client, db_router, player_bio_row, player_season_stat_row, player_advanced_stat_row
    ):
        db_router.when("where p.player_id = %s", player_bio_row)
        db_router.when("from player_season_stats where player_id", [player_season_stat_row])
        db_router.when("from player_advanced_stats where player_id", player_advanced_stat_row)
        db_router.when("from player_advanced_stats a join players", [
            {"corsi_for_pct": c, "xgoals_for_pct": x, "individual_xgoals": i, "icetime_seconds": 45200, "position_code": "C"}
            for c, x, i in ((0.45, 0.44, 5.0), (0.50, 0.50, 8.0), (0.52, 0.51, 10.0), (0.574, 0.552, 12.63))])
        db_router.when("from player_career_totals where player_id", [])
        db_router.when("from player_season_history where player_id", [])

        response = client.get("/players/8477492")

        assert response.status_code == 200
        body = response.json()
        assert body["first_name"] == "Nathan"
        assert body["season_stats"] == [player_season_stat_row]
        assert body["advanced_stats"]["corsi_for_pct"] == 0.574
        assert body["advanced_stats"]["pdo"] == 101.4
        # Best of the four forwards on every measure (ties count half: his own row is one of the four).
        pct = body["advanced_percentiles"]
        assert pct["group"] == "forwards" and pct["peers"] == 4
        assert pct["corsi"] == pct["xg"] == pct["ixg60"] == 88

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
        db_router.when("from player_season_history where player_id", [])

        response = client.get("/players/8477492")

        assert response.status_code == 200
        body = response.json()
        assert body["season_stats"] == []
        assert body["advanced_stats"] is None

    def test_unknown_player_id_404s(self, client, db_router):
        db_router.when("where p.player_id = %s", None)

        response = client.get("/players/99999999")

        assert response.status_code == 404
        assert "99999999" in response.json()["detail"]
        # Neither follow-up query should run once the player itself 404s.
        assert not any("player_season_stats" in q.lower() for q, _ in db_router.calls)
        assert not any("player_advanced_stats" in q.lower() for q, _ in db_router.calls)
        assert not any("player_career_totals" in q.lower() for q, _ in db_router.calls)
        assert not any("player_season_history" in q.lower() for q, _ in db_router.calls)

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
        db_router.when("from player_season_history where player_id", [])

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
        db_router.when("from player_season_history where player_id", [])

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
        db_router.when("from player_season_history where player_id", [])

        response = client.get("/players/8477492")

        assert response.status_code == 200
        assert response.json()["career_totals"] == {"regular_season": None, "playoffs": None}

    def test_season_history_happy_path_skater(
        self,
        client,
        db_router,
        player_bio_row,
        player_season_history_skater_row,
        player_season_history_skater_playoffs_row,
    ):
        # A skater with both a regular-season and a playoffs row for the
        # same season -- two separate entries, not merged together.
        db_router.when("where p.player_id = %s", player_bio_row)
        db_router.when("from player_season_stats where player_id", [])
        db_router.when("from player_advanced_stats where player_id", [])
        db_router.when("from player_career_totals where player_id", [])
        db_router.when(
            "from player_season_history where player_id",
            [player_season_history_skater_row, player_season_history_skater_playoffs_row],
        )

        response = client.get("/players/8477492")

        assert response.status_code == 200
        season_history = response.json()["season_history"]
        assert len(season_history) == 2
        assert season_history[0]["season_id"] == 20242025
        assert season_history[0]["season_type"] == "regular_season"
        assert season_history[0]["points"] == 109
        assert season_history[1]["season_type"] == "playoffs"
        assert season_history[1]["points"] == 15

    def test_season_history_happy_path_goalie(
        self, client, db_router, player_bio_row, player_season_history_goalie_row
    ):
        db_router.when("where p.player_id = %s", player_bio_row)
        db_router.when("from player_season_stats where player_id", [])
        db_router.when("from player_advanced_stats where player_id", [])
        db_router.when("from player_career_totals where player_id", [])
        db_router.when(
            "from player_season_history where player_id", [player_season_history_goalie_row]
        )

        response = client.get("/players/8477492")

        assert response.status_code == 200
        season_history = response.json()["season_history"]
        assert len(season_history) == 1
        assert season_history[0]["wins"] == 11
        assert season_history[0]["goals_against_avg"] == 2.9016
        assert season_history[0]["save_pctg"] == 0.9012

    def test_player_with_no_season_history_rows_returns_empty_list(
        self, client, db_router, player_bio_row
    ):
        # Ingestion hasn't backfilled this player's history yet -- an
        # empty list, not an error.
        db_router.when("where p.player_id = %s", player_bio_row)
        db_router.when("from player_season_stats where player_id", [])
        db_router.when("from player_advanced_stats where player_id", [])
        db_router.when("from player_career_totals where player_id", [])
        db_router.when("from player_season_history where player_id", [])

        response = client.get("/players/8477492")

        assert response.status_code == 200
        assert response.json()["season_history"] == []

    def test_non_integer_player_id_is_rejected_before_touching_the_db(self, client, db_router):
        # player_id: int in the route signature -- FastAPI's own request
        # validation should reject this with a 422 before the endpoint
        # function (and therefore the DB layer) ever runs.
        response = client.get("/players/not-a-number")

        assert response.status_code == 422
        assert db_router.calls == []


class TestGoalieAdvancedStats:
    def _routes(self, db_router, bio, goalie_rows):
        db_router.when("where p.player_id = %s", bio)
        db_router.when("from player_season_stats where player_id", [])
        db_router.when("from player_advanced_stats where player_id", None)
        db_router.when("from goalie_advanced_stats", goalie_rows)
        db_router.when("from player_career_totals where player_id", [])
        db_router.when("from player_season_history where player_id", [])

    def test_goalies_get_gsax_worked_out(self, client, db_router, player_bio_row):
        row = {"season_id": 20262027, "games_played": 5, "icetime_seconds": 18000, "shots_faced": 150,
               "goals_allowed": 10, "xgoals_against": 13.5, "high_danger_shots": 30, "high_danger_goals": 5,
               "high_danger_xgoals": 6.2}
        self._routes(db_router, dict(player_bio_row, position_code="G"), row)

        stats = client.get("/players/8477492").json()["goalie_advanced_stats"]

        assert stats["gsax"] == 3.5 and stats["gsax_per_60"] == 0.7  # 3.5 over 5 hours
        assert stats["high_danger_gsax"] == 1.2

    def test_before_the_table_exists_goalies_just_get_none(self, client, db_router, player_bio_row):
        import psycopg2.errors

        def missing(params):
            raise psycopg2.errors.UndefinedTable("relation \"goalie_advanced_stats\" does not exist")

        self._routes(db_router, dict(player_bio_row, position_code="G"), missing)

        response = client.get("/players/8477492")

        assert response.status_code == 200 and response.json()["goalie_advanced_stats"] is None

    def test_skaters_never_query_it(self, client, db_router, player_bio_row):
        self._routes(db_router, dict(player_bio_row, position_code="C"), None)

        assert client.get("/players/8477492").json()["goalie_advanced_stats"] is None
        assert not any("goalie_advanced_stats" in sql for sql, _ in db_router.calls)


class TestGoaliesAdvanced:
    def test_best_first_by_goals_saved_above_expected(self, client, db_router):
        db_router.when("from goalie_advanced_stats g join players", [
            {"player_id": 1, "first_name": "Linus", "last_name": "Ullmark", "team_abbrev": "OTT", "games_played": 7,
             "icetime_seconds": 7 * 3600, "shots_faced": 200, "goals_allowed": 11, "xgoals_against": 19.5,
             "high_danger_goals": 4, "high_danger_xgoals": 6.25},
            {"player_id": 2, "first_name": "Tristan", "last_name": "Jarry", "team_abbrev": "PIT", "games_played": 6,
             "icetime_seconds": 0, "shots_faced": 0, "goals_allowed": 20, "xgoals_against": 15.0,
             "high_danger_goals": None, "high_danger_xgoals": None},
            {"player_id": 3, "first_name": "No", "last_name": "Data", "team_abbrev": "BOS", "games_played": 1,
             "icetime_seconds": 3600, "shots_faced": 10, "goals_allowed": None, "xgoals_against": None,
             "high_danger_goals": None, "high_danger_xgoals": None}])
        goalies = client.get("/goalies/advanced").json()["goalies"]
        assert [g["name"] for g in goalies] == ["Linus Ullmark", "Tristan Jarry"]
        assert goalies[0] == {"player_id": 1, "name": "Linus Ullmark", "team": "OTT", "games_played": 7, "gsax": 8.5,
                              "gsax_per_60": 1.21, "high_danger_gsax": 2.25, "save_pct": 0.945}
        assert goalies[1]["gsax_per_60"] is None and goalies[1]["save_pct"] is None
