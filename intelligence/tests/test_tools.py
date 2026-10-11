"""The agent loop (main.run_agent) and the tools it can call (tools.ToolRunner)."""

import json

import httpx
import pytest

from app.config import Settings
from app.dashboard import DashboardClient
from app.main import ChatContext, ChatRequest, IntelligenceService, MAX_TOOL_ROUNDS
from app.providers import Provider, ProviderChain
from app.tools import TOOLS, ToolRunner
from tests.fakes import fake_factory, tool_call

STANDINGS = [
    {"team_abbrev": "PIT", "team_name": "Pittsburgh Penguins", "common_name": "Penguins", "conference": "Eastern",
     "division": "Metropolitan", "season_id": 20262027, "snapshot_date": "2026-10-10", "league_sequence": 9,
     "games_played": 5, "wins": 3, "losses": 2, "ot_losses": 0, "points": 6, "division_sequence": 3, "wildcard_sequence": 0},
    {"team_abbrev": "COL", "team_name": "Colorado Avalanche", "common_name": "Avalanche", "conference": "Western",
     "division": "Central", "season_id": 20262027, "snapshot_date": "2026-10-10", "league_sequence": 1,
     "games_played": 5, "wins": 5, "losses": 0, "ot_losses": 0, "points": 10, "division_sequence": 1, "wildcard_sequence": 0},
    *({"team_abbrev": t, "team_name": n, "common_name": n.split()[-1], "conference": "Eastern", "division": "Metropolitan",
       "season_id": 20262027, "snapshot_date": "2026-10-10", "league_sequence": 20} for t, n in
      [("WSH", "Washington Capitals"), ("CBJ", "Columbus Blue Jackets")]),
]
SIM_INPUTS = {
    "as_of_date": "2026-10-10",
    "model": {"home_edge": 0.264, "scale": 1.47},
    "teams": {"PIT": {"rating": 0.2, "conference": "Eastern"}, "COL": {"rating": 0.6, "conference": "Western"},
              "CBJ": {"rating": -0.4, "conference": "Eastern"}},
    "games": [["2026-10-11", "PIT", "COL"], ["2026-10-12", "CBJ", "PIT"], ["2026-10-13", "COL", "CBJ"]],
}
SCENARIO = {"team": "PIT", "scenario": "4-0-0 over the next 4 games", "baseline": {"playoff_pct": 0.6}, "with_scenario": {"playoff_pct": 0.73}}
HISTORY = {"season_id": 20262027, "available_seasons": [20262027], "points": [
    {"as_of_date": "2026-10-01", "team_abbrev": "PIT", "playoff_pct": 0.5},
    {"as_of_date": "2026-10-03", "team_abbrev": "PIT", "playoff_pct": 0.4},
    {"as_of_date": "2026-10-10", "team_abbrev": "PIT", "playoff_pct": 0.6},
]}
TEAM_SCHEDULE = {"team": "PIT", "live": None, "regular_season_games_left": 79, "upcoming": [
    {"id": 76, "date": "2026-10-10", "start_time_utc": "2026-10-10T23:00:00Z", "opponent": "COL", "home": True},
    {"id": 90, "date": "2026-10-13", "start_time_utc": "2026-10-13T23:30:00Z", "opponent": "CBJ", "home": False},
], "recent": [
    {"id": 68, "date": "2026-10-09", "opponent": "CBJ", "home": False, "team_score": 2, "opponent_score": 3, "result": "OTL", "last_period_type": "SO"},
    {"id": 53, "date": "2026-10-07", "opponent": "WSH", "home": False, "team_score": 3, "opponent_score": 5, "result": "L", "last_period_type": "REG"},
]}
WHY_TEAM = lambda rating, rank: {  # noqa: E731
    "games_played": 5, "goal_diff": 4, "xg_diff": 0.2, "goals": 0.057, "xg": 0.003, "last_season": rating - 0.06,
    "last_season_per_game": 0.3, "last_season_share": 0.857, "rating": rating, "rating_rank": rank,
    "schedule": {"games_left": 79, "home_games": 40, "effect": 0.01, "rank": 12},
}
WHY = {"season_id": 20262027, "as_of_date": "2026-10-10", "teams": {"PIT": WHY_TEAM(0.2, 9), "COL": WHY_TEAM(0.6, 1), "CBJ": WHY_TEAM(-0.4, 30)}}
ODDS = [{"season_id": 20262027, "as_of_date": "2026-10-10", "team_abbrev": "PIT", "playoff_pct": 0.61},
        {"season_id": 20262027, "as_of_date": "2026-10-10", "team_abbrev": "COL", "playoff_pct": 0.93}]
PLAYERS = [
    {"player_id": 87, "first_name": "Sidney", "last_name": "Crosby", "team_abbrev": "PIT", "position_code": "C", "points": 5, "goals": 2},
    {"player_id": 71, "first_name": "Evgeni", "last_name": "Malkin", "team_abbrev": "PIT", "position_code": "C", "points": 4, "goals": 1},
    {"player_id": 9, "first_name": "Sidney", "last_name": "Smith", "team_abbrev": "BOS", "position_code": "D", "points": 1, "goals": 0},
    {"player_id": 8477946, "first_name": "Dylan", "last_name": "Larkin", "team_abbrev": "COL", "position_code": "C", "points": 6, "goals": 3},
    {"player_id": 8471000, "first_name": "Tristan", "last_name": "Jarry", "team_abbrev": "PIT", "position_code": "G", "points": 0, "goals": 0},
]


def dashboard(seen=None):
    def handler(request):
        path = request.url.path + (f"?{request.url.query.decode()}" if request.url.query else "")
        if seen is not None:
            seen.append(path)
        routes = {
            "/standings/latest": STANDINGS, "/playoff-odds": ODDS, "/season-sim": SIM_INPUTS, "/playoff-odds/why": WHY,
            "/playoff-odds/history": HISTORY, "/players/leaders": PLAYERS,
            "/players/87": {"first_name": "Sidney", "last_name": "Crosby", "position_code": "C"},
        }
        if request.url.path == "/season-sim/roster-change":
            moves = request.url.params.get_list("move")
            if moves[0].startswith("8471000"):
                return httpx.Response(404, json={"detail": "No value for player 8471000 (goalie, or not on a roster)."})
            return httpx.Response(200, json={"moves": moves, "teams": []})
        if request.url.path == "/season-sim/scenario":
            return httpx.Response(200, json=SCENARIO)
        if request.url.path == "/teams/PIT/schedule":
            return httpx.Response(200, json=TEAM_SCHEDULE)
        if request.url.path == "/games/date/2026-10-07":
            return httpx.Response(200, json={"games": [{"id": 53, "awayTeam": {"abbrev": "PIT"}, "homeTeam": {"abbrev": "WSH"}}]})
        if request.url.path.startswith("/games/") and request.url.path.endswith("/boxscore"):
            gid = int(request.url.path.split("/")[2])
            return httpx.Response(200, json={"id": gid, "gameState": "OFF", "awayTeam": {"abbrev": "PIT", "score": 2}, "homeTeam": {"abbrev": "CBJ" if gid == 68 else "WSH", "score": 3}})
        return httpx.Response(200, json=routes.get(request.url.path, {}))
    return httpx.AsyncClient(base_url="https://dashboard.test", transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
class TestTools:
    async def call(self, name, args, seen=None):
        async with dashboard(seen) as client:
            return json.loads(await ToolRunner(DashboardClient("https://dashboard.test", client)).run(name, json.dumps(args)))

    async def test_every_tool_has_a_runner(self):
        names = {t["function"]["name"] for t in TOOLS}
        assert all(hasattr(ToolRunner, f"_tool_{n}") for n in names)

    async def test_team_names_resolve_to_abbreviations(self):
        seen = []
        result = await self.call("simulate_scenario", {"team": "Penguins", "games": 4, "wins": 4}, seen)

        assert result == SCENARIO
        assert "/season-sim/scenario?team=PIT&games=4&wins=4&ot_losses=0" in seen

    async def test_unknown_teams_come_back_as_errors_the_model_can_read(self):
        result = await self.call("get_team", {"team": "Quebec Nordiques"})
        assert "Unknown team" in result["error"]

    async def test_junk_arguments_are_ignored(self):
        result = await self.call("get_leaders", {"": ""})  # what Groq's model actually sent
        assert "points" in result

    async def test_leaders_by_category(self):
        assert list(await self.call("get_leaders", {"category": "goals"})) == ["goals"]

    async def test_bad_arguments_and_unknown_tools_are_errors_not_crashes(self):
        assert "error" in await self.call("simulate_scenario", {"team": "PIT"})  # missing games/wins
        assert "Unknown tool" in (await self.call("drop_tables", {}))["error"]

    async def test_schedule_comes_from_the_live_feed_with_model_strength_ranks(self):
        # The model's snapshot (SIM_INPUTS) still lists Oct 11/12 games; the live
        # schedule is the truth for dates, so last night's game can't show up as "next".
        result = await self.call("get_schedule", {"team": "PIT", "games": 2})

        assert result["regular_season_games_left"] == 79
        assert result["next"] == [
            {"date": "2026-10-10", "start": "7:00 PM ET", "opponent": "COL", "home": True, "opponent_strength_rank": 1},
            {"date": "2026-10-13", "start": "7:30 PM ET", "opponent": "CBJ", "home": False, "opponent_strength_rank": 3},
        ]

    async def test_schedule_strength_ranks_easiest_first(self):
        result = await self.call("rank_schedule_strength", {})
        # PIT faces COL (0.6) and CBJ (-0.4): 0.1. CBJ faces PIT and COL: 0.4. COL faces PIT and CBJ: -0.1.
        assert [r["team"] for r in result["easiest_first"]] == ["COL", "PIT", "CBJ"]

    async def test_explain_odds_breaks_down_one_team(self):
        result = await self.call("explain_odds", {"team": "Penguins"})

        pit = result["teams"][0]
        assert pit["team"] == "PIT" and pit["name"] == "Pittsburgh Penguins" and pit["playoff_pct"] == 61.0 and pit["rating_rank"] == "9 of 3"
        assert pit["goals"] == {"goal_diff": 4, "games_played": 5, "effect": 0.057, "push": "pushes up"}
        assert pit["xg"]["push"] == "negligible" and pit["schedule"]["push"] == "negligible"
        assert pit["schedule"]["rank"] == "12th easiest of 3" and pit["last_season"]["xg_diff_per_game"] == 0.3
        assert "above its chance quality" in pit["goals_vs_xg"]  # +4 goals on +0.2 xG in 5 games
        assert pit["last_season"]["weight_vs_this_season_pct"] == 86
        assert "matchup" not in result and "negligible" in result["how_to_read"]

    async def test_explain_odds_compares_two_teams_and_their_next_meeting(self):
        result = await self.call("explain_odds", {"team": "PIT", "opponent": "COL"})

        assert [t["team"] for t in result["teams"]] == ["PIT", "COL"]
        meeting = result["matchup"]["next_meeting"]
        # The live schedule has PIT hosting COL on 10-10: (0.2 - 0.6 + 0.264) / 1.47 -> 47.7%.
        assert meeting["date"] == "2026-10-10" and meeting["home_team"] == "PIT"
        assert meeting["PIT_win_pct"] == 47.7 and meeting["COL_win_pct"] == 52.3
        assert result["matchup"]["rating_gap"] == -0.4

    async def test_explain_odds_finds_a_later_meeting_in_the_models_schedule(self):
        # No live schedule for COL in the fake, so it falls back to the model's.
        result = await self.call("explain_odds", {"team": "COL", "opponent": "CBJ"})

        meeting = result["matchup"]["next_meeting"]
        assert meeting["date"] == "2026-10-13" and meeting["home_team"] == "COL"
        assert meeting["COL_win_pct"] > 70

    async def test_explain_odds_rejects_the_same_team_twice(self):
        assert "error" in await self.call("explain_odds", {"team": "PIT", "opponent": "Penguins"})

    async def test_roster_change_with_no_destination(self):
        result = await self.call("simulate_roster_change", {"player": "Larkin"})

        assert result["moves"] == ["8477946:NONE"] and "replacement-level" in result["how_to_read"]

    async def test_roster_change_trade_for_a_named_return(self):
        result = await self.call("simulate_roster_change", {"player": "Dylan Larkin", "player_back": "Sidney Crosby"})

        # Larkin goes to Crosby's team; Crosby comes to Larkin's.
        assert result["moves"] == ["8477946:PIT", "87:COL"]

    async def test_roster_change_to_a_named_team(self):
        result = await self.call("simulate_roster_change", {"player": "Larkin", "to_team": "Penguins"})

        assert result["moves"] == ["8477946:PIT"]

    async def test_roster_change_errors_reach_the_model(self):
        assert "goalie" in (await self.call("simulate_roster_change", {"player": "Jarry"}))["error"]
        assert "multiple_matches" in await self.call("simulate_roster_change", {"player": "Sidney"})

    async def test_playoff_odds_history(self):
        result = await self.call("get_playoff_odds", {"team": "PIT"})
        assert (result["now_pct"], result["week_ago_pct"], result["season_start_pct"], result["low_pct"]) == (60.0, 40.0, 50.0, 40.0)

    async def test_recent_results(self):
        result = await self.call("get_recent_results", {"team": "PIT"})

        assert result["recent_newest_first"][0] == {"date": "2026-10-09", "opponent": "CBJ", "home": False, "result": "OTL", "score": "2-3", "decided_in": "SO"}
        assert "in_progress" not in result

    async def test_get_game_finds_the_latest_by_date_or_by_opponent(self):
        seen = []
        await self.call("get_game", {"team": "PIT"}, seen)
        await self.call("get_game", {"team": "PIT", "opponent": "WSH"}, seen)
        await self.call("get_game", {"team": "PIT", "date": "2026-10-07"}, seen)

        assert [p for p in seen if p.endswith("/boxscore")] == ["/games/68/boxscore", "/games/53/boxscore", "/games/53/boxscore"]

    async def test_get_game_explains_misses(self):
        assert "didn't play" in (await self.call("get_game", {"team": "COL", "date": "2026-10-07"}))["error"]
        assert "YYYY-MM-DD" in (await self.call("get_game", {"team": "PIT", "date": "last tuesday"}))["error"]

    async def test_find_player(self):
        assert (await self.call("find_player", {"name": "crosby"}))["name"] == "Sidney Crosby"
        ambiguous = await self.call("find_player", {"name": "Sidney"})
        assert ambiguous["multiple_matches"] == ["Sidney Crosby (PIT)", "Sidney Smith (BOS)"]
        assert "at least part" in (await self.call("find_player", {"name": "S"}))["error"]


def service(turns, calls):
    providers = [Provider("groq", "Groq", None, "k", "m")]
    return ProviderChain(providers, client_factory=fake_factory({"groq": turns}, calls))


@pytest.mark.asyncio
class TestAgentLoop:
    async def test_calls_a_tool_then_answers_from_its_result(self):
        calls = []
        chain = service((
            [tool_call("simulate_scenario", '{"team":"PIT","games":4,"wins":4}')],
            "Winning all four lifts Pittsburgh from 60% to 73%.",
        ), calls)
        async with dashboard() as client:
            svc = IntelligenceService(Settings("https://dashboard.test", [], providers=chain.providers),
                                      dashboard=DashboardClient("https://dashboard.test", client), chain=chain)
            events = [e async for e in svc.answer_stream(ChatRequest(message="What if PIT wins 4?", context=ChatContext(page="standings")))]

        assert json.loads(events[0][6:]) == {"type": "status", "text": "Simulating 2,000 seasons…"}
        assert "60% to 73%" in events[1]
        done = json.loads(events[2][6:])
        assert {"label": "Season simulation (playoff-odds model)", "endpoint": "tool:simulate_scenario"} in done["evidence"]
        # The second request carried the tool call and its result back to the model.
        second = calls[1][1]["messages"]
        assert second[-2]["tool_calls"][0]["function"]["name"] == "simulate_scenario"
        assert second[-1]["role"] == "tool" and json.loads(second[-1]["content"]) == SCENARIO

    async def test_stops_calling_tools_after_the_round_limit(self):
        calls = []
        loop_forever = [tool_call("get_leaders", "{}")]
        chain = service(tuple([loop_forever] * MAX_TOOL_ROUNDS + ["Here's what I found."]), calls)
        async with dashboard() as client:
            svc = IntelligenceService(Settings("https://dashboard.test", [], providers=chain.providers),
                                      dashboard=DashboardClient("https://dashboard.test", client), chain=chain)
            response = await svc.answer(ChatRequest(message="Leaders?", context=ChatContext(page="standings")))

        assert response.answer == "Here's what I found."
        assert len(calls) == MAX_TOOL_ROUNDS + 1
        assert "tools" not in calls[-1][1]  # the last round has to answer
