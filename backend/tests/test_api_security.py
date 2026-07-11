"""
Coverage for the security-audit fixes: per-IP rate limiting and
team_abbrev path-length validation.

Rate limiting is exercised for real here (not mocked) -- these tests
deliberately exceed the configured limits within a single test to prove
slowapi is actually wired up and enforcing them, not just present in the
code. The _reset_rate_limiter autouse fixture in conftest.py gives every
test a clean window to start from.
"""


class TestRateLimiting:
    def test_default_limit_allows_normal_burst_then_429s(self, client, db_router, team_row):
        # 60/minute default -- 60 requests should all succeed, the 61st
        # should be rejected.
        db_router.when("from teams order by team_name", [team_row])

        statuses = [client.get("/teams").status_code for _ in range(60)]
        assert all(s == 200 for s in statuses)

        blocked = client.get("/teams")
        assert blocked.status_code == 429

    def test_expensive_endpoint_has_a_tighter_limit(self, client, db_router, playoff_odds_row):
        # 20/minute override on /playoff-odds -- the 21st request within
        # the window should be rejected well before the 60/minute default
        # would ever kick in.
        db_router.when("from playoff_odds po", [playoff_odds_row])

        statuses = [client.get("/playoff-odds").status_code for _ in range(20)]
        assert all(s == 200 for s in statuses)

        blocked = client.get("/playoff-odds")
        assert blocked.status_code == 429

    def test_player_leaders_has_the_same_tighter_limit(self, client, db_router, roster_skater_row):
        leader_row = dict(roster_skater_row, team_name="Colorado Avalanche", team_logo_url="https://x/COL.svg")
        db_router.when("t.logo_url as team_logo_url", [leader_row])

        statuses = [client.get("/players/leaders").status_code for _ in range(20)]
        assert all(s == 200 for s in statuses)

        blocked = client.get("/players/leaders")
        assert blocked.status_code == 429

    def test_rate_limited_response_still_carries_cors_header(self, client, db_router, playoff_odds_row):
        # CORS middleware must stay outermost so a 429 doesn't look like
        # an opaque network failure to the browser -- see the ordering
        # comment above app.add_middleware(SlowAPIMiddleware) in api.py.
        db_router.when("from playoff_odds po", [playoff_odds_row])

        for _ in range(20):
            client.get("/playoff-odds", headers={"Origin": "http://localhost:5173"})
        blocked = client.get("/playoff-odds", headers={"Origin": "http://localhost:5173"})

        assert blocked.status_code == 429
        assert blocked.headers.get("access-control-allow-origin") == "http://localhost:5173"

    def test_different_endpoints_have_independent_limit_buckets(self, client, db_router, team_row, playoff_odds_row):
        # Exhausting /playoff-odds's 20/minute limit shouldn't affect a
        # completely different, separately-limited endpoint.
        db_router.when("from playoff_odds po", [playoff_odds_row])
        db_router.when("from teams order by team_name", [team_row])

        for _ in range(21):
            client.get("/playoff-odds")

        assert client.get("/teams").status_code == 200

    def test_varying_the_path_param_does_not_reset_the_bucket(self, client, db_router):
        # Limiter uses key_style="endpoint" specifically so that
        # /teams/COL/roster and /teams/BOS/roster share one bucket per
        # client -- otherwise cycling through team abbreviations would
        # give each one its own fresh 60/minute allowance, defeating the
        # limit entirely. Alternate between two abbreviations for all 60
        # requests; the 61st (regardless of which abbreviation) should
        # still be the one that gets rejected.
        db_router.when("select 1 from teams where team_abbrev", {"?column?": 1})
        db_router.when("where p.team_abbrev = %s", [])

        abbrevs = ["COL", "BOS"]
        statuses = [client.get(f"/teams/{abbrevs[i % 2]}/roster").status_code for i in range(60)]
        assert all(s == 200 for s in statuses)

        blocked = client.get("/teams/COL/roster")
        assert blocked.status_code == 429


class TestTeamAbbrevPathValidation:
    def test_four_char_abbreviation_rejected_before_touching_the_db(self, client, db_router):
        response = client.get("/teams/ABCD/roster")

        assert response.status_code == 422
        assert db_router.calls == []

    def test_three_char_abbreviation_is_accepted(self, client, db_router):
        db_router.when("select 1 from teams where team_abbrev", {"?column?": 1})
        db_router.when("where p.team_abbrev = %s", [])

        response = client.get("/teams/COL/roster")

        assert response.status_code == 200

    def test_oversized_abbreviation_rejected_on_standings_history(self, client, db_router):
        response = client.get("/standings/TOOLONG")

        assert response.status_code == 422
        assert db_router.calls == []

    def test_oversized_abbreviation_rejected_on_season_history(self, client, db_router):
        response = client.get("/standings/TOOLONG/seasons")

        assert response.status_code == 422
        assert db_router.calls == []
