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
