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
]
SIM_INPUTS = {
    "as_of_date": "2026-10-10",
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
PLAYERS = [
    {"player_id": 87, "first_name": "Sidney", "last_name": "Crosby", "team_abbrev": "PIT", "position_code": "C", "points": 5, "goals": 2},
    {"player_id": 71, "first_name": "Evgeni", "last_name": "Malkin", "team_abbrev": "PIT", "position_code": "C", "points": 4, "goals": 1},
    {"player_id": 9, "first_name": "Sidney", "last_name": "Smith", "team_abbrev": "BOS", "position_code": "D", "points": 1, "goals": 0},
]


def dashboard(seen=None):
    def handler(request):
        path = request.url.path + (f"?{request.url.query.decode()}" if request.url.query else "")
        if seen is not None:
            seen.append(path)
        routes = {
            "/standings/latest": STANDINGS, "/playoff-odds": [], "/season-sim": SIM_INPUTS,
            "/playoff-odds/history": HISTORY, "/players/leaders": PLAYERS,
            "/players/87": {"first_name": "Sidney", "last_name": "Crosby", "position_code": "C"},
        }
        if request.url.path == "/season-sim/scenario":
            return httpx.Response(200, json=SCENARIO)
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

    async def test_bad_arguments_and_unknown_tools_are_errors_not_crashes(self):
        assert "error" in await self.call("simulate_scenario", {"team": "PIT"})  # missing games/wins
        assert "Unknown tool" in (await self.call("drop_tables", {}))["error"]

    async def test_schedule_with_opponent_strength(self):
        result = await self.call("get_schedule", {"team": "PIT", "games": 2})

        assert result["games_left"] == 2
        assert result["next"] == [
            {"date": "2026-10-11", "opponent": "COL", "home": True, "opponent_strength_rank": 1},
            {"date": "2026-10-12", "opponent": "CBJ", "home": False, "opponent_strength_rank": 3},
        ]

    async def test_schedule_strength_ranks_easiest_first(self):
        result = await self.call("rank_schedule_strength", {})
        # PIT faces COL (0.6) and CBJ (-0.4): 0.1. CBJ faces PIT and COL: 0.4. COL faces PIT and CBJ: -0.1.
        assert [r["team"] for r in result["easiest_first"]] == ["COL", "PIT", "CBJ"]

    async def test_playoff_odds_history(self):
        result = await self.call("get_playoff_odds", {"team": "PIT"})
        assert (result["now_pct"], result["week_ago_pct"], result["season_start_pct"], result["low_pct"]) == (60.0, 40.0, 50.0, 40.0)

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
