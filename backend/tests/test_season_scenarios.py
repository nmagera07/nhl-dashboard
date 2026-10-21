"""season_scenarios: what-if simulations, and their API endpoints."""

import pytest

import season_scenarios as sc

MODEL = {"home_edge": 0.264, "scale": 1.47, "ot_probability": 0.221, "shootout_share_of_ot": 0.32}


def _payload():
    atlantic, metro = ["BOS", "TOR", "MTL", "OTT"], ["NYR", "NJD", "PHI", "PIT", "CBJ"]
    names = atlantic + metro
    teams = {
        t: {"points": 0, "wins": 0, "losses": 0, "ot_losses": 0, "regulation_wins": 0, "row": 0,
            "division": "Atlantic" if t in atlantic else "Metropolitan", "conference": "Eastern",
            "rating": 0.0, "rating_sd": 0.1}
        for t in names
    }
    games, day = [], 1
    for _ in range(3):
        for i, home in enumerate(names):
            for away in names[i + 1:]:
                games.append([f"2026-11-{day:02d}", home, away])
        day += 1
    return {"as_of_date": "2026-10-31", "model": MODEL, "teams": teams, "games": games}


class TestScenario:
    def test_winning_raises_the_odds_and_losing_lowers_them(self):
        p = _payload()
        win = sc.scenario(p, "ott", games=5, wins=5, trials=400)
        lose = sc.scenario(p, "OTT", games=5, wins=0, trials=400)

        assert win["baseline"] == lose["baseline"]  # same seed, same baseline
        assert win["with_scenario"]["playoff_pct"] > win["baseline"]["playoff_pct"] > lose["with_scenario"]["playoff_pct"]
        assert win["with_scenario"]["avg_points"] > lose["with_scenario"]["avg_points"]
        assert win["scenario"] == "5-0-0 over the next 5 games" and len(win["games"]) == 5

    def test_forced_results_are_exact(self):
        # Winning all 5 adds exactly 10 points to every simulated season vs losing them all in regulation.
        p = _payload()
        win = sc.scenario(p, "OTT", games=5, wins=5, trials=300)
        lose = sc.scenario(p, "OTT", games=5, wins=0, trials=300)
        assert win["with_scenario"]["avg_points"] - lose["with_scenario"]["avg_points"] >= 10

    def test_rejects_impossible_records_and_unknown_teams(self):
        with pytest.raises(ValueError):
            sc.scenario(_payload(), "OTT", games=3, wins=3, ot_losses=1, trials=10)
        with pytest.raises(sc.UnknownTeam):
            sc.scenario(_payload(), "XYZ", games=3, wins=1, trials=10)


class TestPlayedSinceSnapshot:
    def test_games_finished_since_the_snapshot_are_skipped(self):
        p = _payload()
        first = next(g for g in p["games"] if "OTT" in g[1:])
        played = frozenset({tuple(first)})

        stale = sc.scenario(p, "OTT", games=2, wins=1, trials=20)
        fresh = sc.scenario(p, "OTT", games=2, wins=1, trials=20, played=played)

        assert stale["games"][0].startswith(first[0]) and fresh["games"][0] == stale["games"][1]


class TestPlayoffPath:
    def test_more_wins_never_means_worse_odds(self):
        path = sc.playoff_path(_payload(), "CBJ", games=6, trials_per_record=300)

        odds = [row["playoff_pct"] for row in path["by_record"]]
        assert [row["record"] for row in path["by_record"]] == ["0-6", "1-5", "2-4", "3-3", "4-2", "5-1", "6-0"]
        assert odds == sorted(odds)


class TestEndpoints:
    @pytest.fixture(autouse=True)
    def no_live_games(self, monkeypatch):
        import api

        monkeypatch.setattr(api, "team_schedule", lambda team: {"recent": []})

    def test_scenario_is_cached_per_day_of_inputs(self, client, db_router, monkeypatch):
        import api

        api._SCENARIO_CACHE.clear()
        db_router.when("from season_sim_inputs", [{"payload": _payload()}])
        calls = []
        real = sc.scenario
        monkeypatch.setattr(sc, "scenario", lambda *a, **k: calls.append(1) or real(*a, **{**k, "trials": 50}))

        first = client.get("/season-sim/scenario?team=OTT&games=3&wins=2")
        second = client.get("/season-sim/scenario?team=ott&games=3&wins=2")

        assert first.status_code == 200 and first.json() == second.json()
        assert len(calls) == 1

    def test_bad_requests(self, client, db_router):
        import api

        api._SCENARIO_CACHE.clear()
        db_router.when("from season_sim_inputs", [{"payload": _payload()}])

        assert client.get("/season-sim/scenario?team=XYZ&games=3&wins=1").status_code == 404
        assert client.get("/season-sim/scenario?team=OTT&games=3&wins=4").status_code == 400
        assert client.get("/season-sim/path?team=OTT&games=40").status_code == 422

    def test_tonights_finished_game_drops_out_of_the_window(self, client, db_router, monkeypatch):
        import api

        api._SCENARIO_CACHE.clear()
        p = _payload()
        first = next(g for g in p["games"] if "OTT" in g[1:])
        db_router.when("from season_sim_inputs", [{"payload": p}])
        home = first[1] == "OTT"
        monkeypatch.setattr(api, "team_schedule", lambda team: {"recent": [
            {"date": first[0], "home": home, "opponent": first[2] if home else first[1]}]})

        body = client.get("/season-sim/scenario?team=OTT&games=1&wins=1").json()

        assert not body["games"][0].startswith(f"{first[0]} {'vs' if home else '@'} {first[2] if home else first[1]}")


def _with_players():
    p = _payload()
    p["players"] = {
        "8470001": {"name": "Star Center", "team": "OTT", "pos": "C", "gp": 10, "value": 0.3},
        "8470002": {"name": "Depth Winger", "team": "BOS", "pos": "L", "gp": 10, "value": 0.01},
    }
    return p


class TestRosterChange:
    def test_losing_a_star_costs_the_team_and_his_new_team_gains(self):
        result = sc.roster_change(_with_players(), [(8470001, "BOS")], trials=400)

        by_team = {t["team"]: t for t in result["teams"]}
        assert set(by_team) == {"BOS", "OTT"}
        assert by_team["OTT"]["rating_change"] == -0.3 and by_team["BOS"]["rating_change"] == 0.3
        assert by_team["OTT"]["with_change"]["playoff_pct"] < by_team["OTT"]["baseline"]["playoff_pct"]
        assert by_team["BOS"]["with_change"]["playoff_pct"] > by_team["BOS"]["baseline"]["playoff_pct"]
        assert result["moves"][0] == {"player": "Star Center", "position": "C", "from": "OTT", "to": "BOS",
                                      "value_goals_per_game": 0.3, "games_this_season": 10}

    def test_a_player_who_is_just_gone_only_moves_his_team(self):
        result = sc.roster_change(_with_players(), [(8470001, None)], trials=200)

        assert [t["team"] for t in result["teams"]] == ["OTT"]

    def test_a_swap_nets_out(self):
        result = sc.roster_change(_with_players(), [(8470001, "BOS"), (8470002, "OTT")], trials=50)

        assert {t["team"]: t["rating_change"] for t in result["teams"]} == {"BOS": 0.29, "OTT": -0.29}

    def test_bad_moves(self):
        with pytest.raises(sc.UnknownPlayer):
            sc.roster_change(_with_players(), [(8479999, None)], trials=10)
        with pytest.raises(ValueError, match="already plays"):
            sc.roster_change(_with_players(), [(8470001, "OTT")], trials=10)
        with pytest.raises(sc.UnknownTeam):
            sc.roster_change(_with_players(), [(8470001, "XYZ")], trials=10)
        with pytest.raises(ValueError, match="aren't available"):
            sc.roster_change(_payload(), [(8470001, None)], trials=10)


class TestRosterChangeEndpoint:
    def test_simulates_and_caches(self, client, db_router, monkeypatch):
        db_router.when("from season_sim_inputs", [{"payload": _with_players()}])
        calls = []
        real = sc.roster_change
        monkeypatch.setattr(sc, "roster_change", lambda *a, **k: calls.append(a) or real(*a, trials=20))

        first = client.get("/season-sim/roster-change?move=8470001:bos")
        second = client.get("/season-sim/roster-change?move=8470001:BOS")

        assert first.status_code == 200 and first.json() == second.json()
        assert len(calls) == 1 and calls[0][1] == [(8470001, "BOS")]

    def test_bad_requests(self, client, db_router):
        db_router.when("from season_sim_inputs", [{"payload": _with_players()}])

        assert client.get("/season-sim/roster-change?move=larkin:DET").status_code == 422
        assert client.get("/season-sim/roster-change?move=8470001:NONE&move=8470001:BOS").status_code == 422
        assert client.get("/season-sim/roster-change?move=8479999:NONE").status_code == 404
        assert client.get("/season-sim/roster-change?move=8470001:OTT").status_code == 400

    def test_the_browser_payload_leaves_out_player_values(self, client, db_router):
        db_router.when("from season_sim_inputs", [{"payload": _with_players()}])

        assert "players" not in client.get("/season-sim").json()


class TestInjuryReturn:
    def test_back_sooner_is_worth_more(self):
        result = sc.injury_return(_with_players(), 8470001, back="2026-11-02", trials=600)
        s = result["scenarios"]
        assert result["team"] == "OTT" and result["player"] == "Star Center" and result["expected_return"] == "2026-11-02"
        assert result["team_games_missed_before_return"] == 8  # every OTT game on Nov 1
        assert s["healthy_now"]["avg_points"] > s["back_on_return_date"]["avg_points"] > s["out_for_season"]["avg_points"]

    def test_the_return_date_only_cuts_the_games_before_it(self):
        payload = _with_players()
        before = sc.injury_return(payload, 8470001, back="2026-10-01", trials=200)["scenarios"]
        after = sc.injury_return(payload, 8470001, back="2026-12-01", trials=200)["scenarios"]
        assert before["back_on_return_date"] == before["healthy_now"]  # back before any game: no games missed
        assert after["back_on_return_date"] == after["out_for_season"]  # back after the last game: all missed

    def test_without_a_date_only_healthy_and_out(self):
        result = sc.injury_return(_with_players(), 8470001, trials=50)
        assert set(result["scenarios"]) == {"healthy_now", "out_for_season"} and result["team_games_missed_before_return"] is None

    def test_unknown_players_and_missing_values(self):
        with pytest.raises(sc.UnknownPlayer):
            sc.injury_return(_with_players(), 8479999, trials=10)
        with pytest.raises(ValueError, match="aren't available"):
            sc.injury_return(_payload(), 8470001, trials=10)


class TestInjuryEndpoint:
    def test_simulates_and_caches(self, client, db_router, monkeypatch):
        db_router.when("from season_sim_inputs", [{"payload": _with_players()}])
        calls = []
        real = sc.injury_return
        monkeypatch.setattr(sc, "injury_return", lambda *a, **k: calls.append(a) or real(*a, trials=20))

        first = client.get("/season-sim/injury?player=8470001&back=2026-11-02")
        second = client.get("/season-sim/injury?player=8470001&back=2026-11-02")

        assert first.status_code == 200 and first.json() == second.json()
        assert len(calls) == 1 and calls[0][1:] == (8470001, "2026-11-02")
        assert set(first.json()["scenarios"]) == {"healthy_now", "back_on_return_date", "out_for_season"}

    def test_bad_requests(self, client, db_router):
        db_router.when("from season_sim_inputs", [{"payload": _with_players()}])
        assert client.get("/season-sim/injury?player=8479999").status_code == 404
        assert client.get("/season-sim/injury?player=8470001&back=soon").status_code == 422
        assert client.get("/season-sim/injury").status_code == 422
