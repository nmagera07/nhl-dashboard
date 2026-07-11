"""
GET /teams/{team_abbrev}/roster

Locks in the fixed 404-vs-empty-list behavior: a bogus team abbreviation
404s (checked against `teams` first), a real team with zero roster rows
returns 200 with [].
"""


class TestTeamRoster:
    def test_happy_path_real_team_with_data(self, client, db_router, roster_skater_row, roster_goalie_row):
        db_router.when("select 1 from teams where team_abbrev", {"?column?": 1})
        db_router.when("where p.team_abbrev = %s", [roster_skater_row, roster_goalie_row])

        response = client.get("/teams/COL/roster")

        assert response.status_code == 200
        body = response.json()
        assert len(body) == 2
        assert body[0]["first_name"] == "Nathan"
        # goalie-only fields null on the skater, skater-only fields null on the goalie
        assert body[0]["wins"] is None
        assert body[1]["goals"] is None
        assert body[1]["wins"] == 31

    def test_real_team_with_no_roster_rows_returns_200_empty_list(self, client, db_router):
        # Real team (passes the teams existence check), but the roster
        # query itself comes back empty -- e.g. a new team before its
        # first roster ingestion run.
        db_router.when("select 1 from teams where team_abbrev", {"?column?": 1})
        db_router.when("where p.team_abbrev = %s", [])

        response = client.get("/teams/XXT/roster")

        assert response.status_code == 200
        assert response.json() == []

    def test_bogus_team_abbreviation_404s(self, client, db_router):
        # Existence check itself comes back empty -- the roster query
        # should never even run.
        db_router.when("select 1 from teams where team_abbrev", None)

        response = client.get("/teams/ZZZ/roster")

        assert response.status_code == 404
        assert "ZZZ" in response.json()["detail"]
        assert not any("where p.team_abbrev" in q.lower() for q, _ in db_router.calls)

    def test_team_abbrev_is_uppercased_before_querying(self, client, db_router):
        seen_params = []

        def capture(params):
            seen_params.append(params)
            return {"?column?": 1}

        db_router.when("select 1 from teams where team_abbrev", capture)
        db_router.when("where p.team_abbrev = %s", [])

        client.get("/teams/col/roster")

        assert seen_params == [("COL",)]
