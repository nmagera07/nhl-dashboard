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
# What the model sees: the same, with odds as percentages.
SCENARIO_FOR_MODEL = {**SCENARIO, "baseline": {"playoff_pct": 60.0}, "with_scenario": {"playoff_pct": 73.0}}
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

        assert result == SCENARIO_FOR_MODEL
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
        assert "roster_moves" not in pit  # no moves in this fixture

    async def test_explain_odds_includes_roster_moves(self, monkeypatch):
        monkeypatch.setitem(WHY["teams"], "PIT", {**WHY_TEAM(0.2, 9), "roster": -0.09, "roster_change_per_game": -0.3,
                                                  "goalies": 0.05, "goalies_per_game": 0.08})
        pit = (await self.call("explain_odds", {"team": "PIT"}))["teams"][0]

        assert pit["roster_moves"] == {"goals_per_game_gained_or_lost": -0.3, "effect": -0.09, "push": "pulls down"}
        assert pit["goaltending"] == {"goals_per_game_saved_vs_average_tandem": 0.08, "effect": 0.05, "push": "pushes up"}

    async def test_explain_odds_v24_roster_stands_in_for_last_season(self, monkeypatch):
        monkeypatch.setitem(WHY["teams"], "PIT", {**WHY_TEAM(0.2, 9), "last_season": 0, "last_season_per_game": 0,
                                                  "roster": 0.12, "roster_per_game": 0.16})
        pit = (await self.call("explain_odds", {"team": "PIT"}))["teams"][0]

        assert pit["roster"] == {"players_goals_per_game_vs_average_roster": 0.16, "weight_vs_this_season_pct": 86,
                                 "effect": 0.12, "push": "pushes up"}
        assert "last_season" not in pit and "roster_moves" not in pit

    async def test_next_meeting_includes_a_back_to_back(self, monkeypatch):
        monkeypatch.setitem(SIM_INPUTS, "model", {"home_edge": 0.16, "scale": 1.457, "home_b2b": -0.306, "away_b2b": 0.53})
        monkeypatch.setitem(SIM_INPUTS, "games", [["2026-10-10", "PIT", "COL", False, True], *SIM_INPUTS["games"]])
        meeting = (await self.call("explain_odds", {"team": "PIT", "opponent": "COL"}))["matchup"]["next_meeting"]

        # (0.2 - 0.6 + 0.16 + 0.53) / 1.457 -> PIT is now favored at home against a tired COL.
        assert meeting["PIT_win_pct"] == 55.0 and meeting["back_to_back"] == ["COL"]
        assert "second night of a back-to-back" in meeting["note"]

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

    async def test_simulated_odds_come_back_as_percentages(self):
        result = await self.call("simulate_scenario", {"team": "PIT", "games": 4, "wins": 4})
        assert result["baseline"]["playoff_pct"] == 60.0 and result["with_scenario"]["playoff_pct"] == 73.0

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

    # The Players page moved to /players/leaders?view=table (19 fields). These
    # tools need the full 38-field default, so they must never add a query.
    async def test_find_player_requests_the_full_leaders_view(self):
        seen = []
        await self.call("find_player", {"name": "crosby"}, seen)
        leaders = [p for p in seen if p.startswith("/players/leaders")]
        assert leaders and set(leaders) == {"/players/leaders"}

    async def test_get_leaders_requests_the_full_leaders_view(self):
        seen = []
        await self.call("get_leaders", {"category": "goals"}, seen)
        leaders = [p for p in seen if p.startswith("/players/leaders")]
        assert leaders and set(leaders) == {"/players/leaders"}


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
        answer = "".join(json.loads(e[6:])["text"] for e in events if '"type": "delta"' in e)
        assert "60% to 73%" in answer
        done = json.loads(events[-1][6:])
        assert {"label": "Season simulation (playoff-odds model)", "endpoint": "tool:simulate_scenario"} in done["evidence"]
        # The second request carried the tool call and its result back to the model.
        second = calls[1][1]["messages"]
        assert second[-2]["tool_calls"][0]["function"]["name"] == "simulate_scenario"
        assert second[-1]["role"] == "tool" and json.loads(second[-1]["content"]) == SCENARIO_FOR_MODEL

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


@pytest.mark.asyncio
class TestNewsTools:
    async def call(self, name, args):
        def handler(request):
            path = request.url.path
            if path == "/standings/latest":
                return httpx.Response(200, json=STANDINGS)
            if path == "/injuries":
                team = request.url.params.get("team")
                teams = {"PIT": [{"player": "Justin Brazeau", "status": "Injured Reserve", "injury": "Lower Body", "note": None}], "COL": []}
                return httpx.Response(200, json={"source": "ESPN", "teams": {team: teams.get(team, [])} if team else teams})
            if path == "/news":
                return httpx.Response(200, json={"headlines": [{"title": "Penguins respond", "source": "NHL.com", "published": "2026-10-11T12:00:00Z", "summary": ""}]})
            if path == "/transactions":
                return httpx.Response(200, json={"transactions": [{"date": "2026-10-11", "team": "PIT", "description": "Recalled F X."}]})
            return httpx.Response(404, json={})
        async with httpx.AsyncClient(base_url="https://dashboard.test", transport=httpx.MockTransport(handler)) as client:
            return json.loads(await ToolRunner(DashboardClient("https://dashboard.test", client)).run(name, json.dumps(args)))

    async def test_injuries_for_a_team_by_name(self):
        result = await self.call("get_injuries", {"team": "Penguins"})
        assert result["teams"] == {"PIT": [{"player": "Justin Brazeau", "status": "Injured Reserve", "injury": "Lower Body"}]}
        assert "aren't on the report" in result["note"]

    async def test_a_player_is_found_on_any_team_by_name(self):
        result = await self.call("get_injuries", {"player": "brazeau"})
        assert result["matches"] == [{"team": "PIT", "player": "Justin Brazeau", "status": "Injured Reserve", "injury": "Lower Body"}]
        missing = await self.call("get_injuries", {"player": "Sidney Crosby"})
        assert missing["matches"] == [] and "isn't" not in missing["note"] and "doesn't guarantee" in missing["note"]

    async def test_league_injuries_skip_teams_with_nobody_hurt(self):
        assert list((await self.call("get_injuries", {}))["teams"]) == ["PIT"]

    async def test_news_brings_headlines_and_transactions(self):
        result = await self.call("get_news", {"team": "PIT"})
        assert result["headlines"][0] == {"title": "Penguins respond", "source": "NHL.com", "published": "2026-10-11T12:00"}
        assert result["transactions"][0]["description"] == "Recalled F X."


SIDE = lambda price, fair, ours, **kw: {"price": price, "fair": fair, "ours": ours, "value": False, "ev": -0.02, **kw}  # noqa: E731
BETS = {"date": "2026-10-20", "games": {"150": {
    "home": "VAN", "away": "CAR", "b2b": {"home": False, "away": True},
    "moneyline": {"home": SIDE(150, 135, 0.426, book="BetRivers", value=True, ev=0.064), "away": SIDE(-170, -135, 0.574, book="DraftKings")},
    "puck_line": {"home_spread": 1.5, "home": SIDE(-160, -170, 0.63), "away": SIDE(135, 170, 0.37)},
    "total": {"line": 6.5, "over": SIDE(-110, 105, 0.49), "under": SIDE(-110, -105, 0.51)},
    "goalies": {"home": [{"name": "Kevin Lankinen", "prob": 0.62}], "away": [{"name": "Pyotr Kochetkov", "prob": 0.52}]},
    "nhl_starters": {"home": "Kevin Lankinen", "away": "Pyotr Kochetkov"},
    "reported_starters": {"home": {"name": "Leevi Merilainen", "status": "confirmed"}, "away": None},
}}}
LINEUP = {"available": True, "published": "2026-10-20T19:43:15.303Z",
          "home": {"abbrev": "VAN", "forwards": [["Cotter", "Chytil", "Boeser"]], "defense": [["Hughes", "Hronek"]],
                   "goalies": ["Kevin Lankinen", "Leevi Merilainen"], "scratched": ["Mancini"], "injured": []},
          "away": {"abbrev": "CAR"}}
FANTASY = {"sources": ["RotoWire", "DobberHockey"], "updates": [
    {"player": "Jesper Wallstedt", "team": "MIN", "title": "Slated to face Oilers", "summary": "Expected in the road crease.",
     "published": "2026-10-20T18:42:00Z"},
    {"player": "Devon Levi", "team": "EDM", "title": "Guarding goal Tuesday", "summary": "", "published": "2026-10-20T18:35:00Z"}],
    "articles": [{"title": "Buying low on Brayden Point", "source": "DobberHockey"}]}
LOTTERY = {"projected": [{"team": "VAN", "missed_playoffs": 0.98, "picks": [0.15, 0.13, 0.12] + [0.04] * 13},
                         {"team": "PIT", "missed_playoffs": 0.8, "picks": [0.05, 0.05, 0.05] + [0.05] * 13}],
           "today": [{"team": "VAN", "position": 1, "points": 4, "picks": [0.255] + [0.05] * 15}],
           "mock": {"year": 2027, "projected": [
               {"pick": 1, "team": "VAN", "prospect": {"name": "Landon DuPont", "pos": "D", "team": "University of Michigan"}},
               {"pick": 6, "team": "PIT", "prospect": {"name": "Alexis Joseph", "pos": "C", "team": "Saint John Sea Dogs"}}]}}
CARD = {"as_of": "2026-10-19", "week": {"games": 51, "moneyline": {"games": 22, "brier_ours": 0.2264, "brier_books": 0.2192},
                                        "value_bets": {"bets": 0, "wins": 0, "list": []}, "disagreements": [{"x": 1}]},
        "season": {"games": 140, "moneyline": {"games": 80, "brier_ours": 0.23, "brier_books": 0.229}}}


@pytest.mark.asyncio
class TestBettingLineupFantasyDraft:
    @pytest.fixture(autouse=True)
    def today(self, monkeypatch):
        import app.tools
        monkeypatch.setattr(app.tools, "_today", lambda: "2026-10-20")

    async def call(self, name, args, lineup=LINEUP):
        van_schedule = {"team": "VAN", "live": None, "upcoming": [
            {"id": 150, "date": "2026-10-20", "start_time_utc": "2026-10-21T02:00:00Z", "home": True, "opponent": "CAR"}], "recent": []}
        routes = {"/standings/latest": STANDINGS + [{"team_abbrev": "VAN", "team_name": "Vancouver Canucks", "common_name": "Canucks"},
                                                    {"team_abbrev": "CAR", "team_name": "Carolina Hurricanes", "common_name": "Hurricanes"},
                                                    {"team_abbrev": "MIN", "team_name": "Minnesota Wild", "common_name": "Wild"}],
                  "/bets": BETS, "/games/date/2026-10-20": {"games": [{"id": 150, "gameState": "PRE", "startTimeUTC": "2026-10-21T02:00:00Z"}]},
                  "/teams/VAN/schedule": van_schedule, "/games/150/lineup": lineup, "/fantasy": FANTASY,
                  "/draft-lottery": LOTTERY, "/report-card": CARD,
                  "/teams/VAN/lines": {"team": "VAN", "game": {"date": "2026-10-17", "opponent": "TBL", "home": False},
                                       "lines": [{"players": ["Cotter", "Chytil", "Boeser"]}]},
                  "/teams/PIT/schedule": {"team": "PIT", "live": None, "upcoming": [{"id": 9, "date": "2026-10-22"}], "recent": []}}

        def handler(request):
            return httpx.Response(200, json=routes.get(request.url.path, {}))
        async with httpx.AsyncClient(base_url="https://dashboard.test", transport=httpx.MockTransport(handler)) as client:
            return json.loads(await ToolRunner(DashboardClient("https://dashboard.test", client)).run(name, json.dumps(args)))

    async def test_bets_for_one_game_with_value_and_goalies(self):
        result = await self.call("get_bets", {"team": "Canucks"})
        (game,) = result["games"]
        assert game["game"] == "CAR @ VAN" and game["start"] == "10:00 PM ET" and game["second_night_of_back_to_back"] == ["CAR"]
        assert game["moneyline"]["VAN"] == {"best_price": "+150", "book": "BetRivers", "puckpulse_fair_price": "+135",
                                            "puckpulse_chance_pct": 42.6, "value": "yes, expected return +6.4%"}
        assert game["puck_line"]["VAN +1.5"]["best_price"] == "-160" and "total" in game
        assert game["goalies"]["home"] == "Leevi Merilainen: confirmed by beat reporters (via RotoWire)"
        assert game["goalies"]["away"] == "Pyotr Kochetkov: projected by NHL.com's lineup"
        assert "21+" in result["note"] and "not a sure thing" in result["note"]
        assert result["value_flags"] == ["CAR @ VAN: VAN moneyline +150, yes, expected return +6.4%"]

    async def test_the_whole_slate_keeps_to_moneylines_for_games_not_started(self):
        (game,) = (await self.call("get_bets", {}))["games"]
        assert "puck_line" not in game and "total" not in game and "goalies" not in game
        assert game["moneyline"]["CAR"]["best_price"] == "-170"

    async def test_no_value_is_said_plainly(self, monkeypatch):
        monkeypatch.setitem(BETS["games"]["150"]["moneyline"], "home", SIDE(150, 135, 0.426, book="BetRivers"))
        assert (await self.call("get_bets", {}))["value_flags"].startswith("None right now")

    async def test_games_already_started_are_only_listed_on_the_slate(self, monkeypatch):
        live = {"games": [{"id": 150, "gameState": "LIVE", "startTimeUTC": "2026-10-21T02:00:00Z"}]}
        monkeypatch.setitem(BETS, "date", "2026-10-20")
        original = self.call

        async def call(name, args):
            import app.tools
            async def fake_get(runner, path):
                if path.startswith("/games/date/"):
                    return live
                return await real_get(runner, path)
            real_get = app.tools.ToolRunner._get
            monkeypatch.setattr(app.tools.ToolRunner, "_get", fake_get)
            return await original(name, args)
        slate = await call("get_bets", {})
        assert "games" not in slate and slate["already_started"] == ["CAR @ VAN"]
        one = await call("get_bets", {"team": "VAN"})
        assert "last lines before puck drop" in one["games"][0]["state"]

    async def test_bets_for_a_team_without_a_game(self):
        assert "no game" in (await self.call("get_bets", {"team": "PIT"}))["error"]

    async def test_report_card_drops_the_long_lists(self):
        result = await self.call("get_report_card", {})
        assert result["last_week"]["moneyline"] == {"games": 22, "brier_puckpulse": 0.2264, "brier_books": 0.2192}
        assert result["last_week"]["value_bets"] == {"bets": 0, "wins": 0} and "disagreements" not in json.dumps(result)

    async def test_lineup_with_the_reported_starter_and_nhl_lines(self):
        result = await self.call("get_lineup", {"team": "VAN"})
        assert result["game_today"] == "vs CAR, 10:00 PM ET" and result["starting_goalie"].startswith("Leevi Merilainen: confirmed")
        assert "goalies" not in result["nhl_com_projected_lineup"]
        assert result["nhl_com_projected_lineup"]["forward_lines"] == [["Cotter", "Chytil", "Boeser"]]
        assert result["nhl_com_projected_lineup"]["scratched"] == ["Mancini"] and "puck drop" in result["caveat"]

    async def test_lineup_before_nhl_com_posts_it_falls_back_to_last_games_lines(self):
        result = await self.call("get_lineup", {"team": "VAN"}, lineup={"available": False})
        assert result["last_game_lines"] == {"game": "2026-10-17 at TBL", "lines_by_minutes_together": [["Cotter", "Chytil", "Boeser"]]}
        assert "hasn't posted" in result["note"]

    async def test_lineup_without_a_game_today(self):
        result = await self.call("get_lineup", {"team": "PIT"})
        assert result["note"].startswith("No game today")

    async def test_fantasy_news_for_a_player_and_an_honest_miss(self):
        result = await self.call("get_fantasy_news", {"player": "wallstedt"})
        assert result["updates_newest_first"] == [{"player": "Jesper Wallstedt", "team": "MIN", "update": "Slated to face Oilers",
                                                   "detail": "Expected in the road crease.", "published": "2026-10-20T18:42"}]
        assert "articles" not in result
        missing = await self.call("get_fantasy_news", {"player": "Crosby"})
        assert not missing.get("updates_newest_first") and "not the same as no news" in missing["note"]

    async def test_fantasy_news_for_everything_includes_articles(self):
        result = await self.call("get_fantasy_news", {})
        assert len(result["updates_newest_first"]) == 2 and result["articles"] == [{"title": "Buying low on Brayden Point", "source": "DobberHockey"}]

    async def test_draft_lottery_for_one_team(self):
        result = await self.call("get_draft_lottery", {"team": "PIT"})
        assert result["projected"] == {"team": "PIT", "no1_pick_pct": 5.0, "top3_pct": 15.0, "in_lottery_pct": 80.0}
        assert result["mock_draft_pick"] == [{"pick": 6, "team": "PIT", "prospect": "Alexis Joseph", "position": "C", "club": "Saint John Sea Dogs"}]
        assert "2027 rankings" in result["note"]

    async def test_draft_lottery_top_of_the_order(self):
        result = await self.call("get_draft_lottery", {})
        assert result["projected_top"][0]["team"] == "VAN" and result["mock_draft_first_10"][0]["prospect"] == "Landon DuPont"
        assert result["if_season_ended_today_top"][0]["no1_pick_pct"] == 25.5



@pytest.mark.asyncio
class TestScoresLeadersStandings:
    @pytest.fixture(autouse=True)
    def today(self, monkeypatch):
        import app.tools
        monkeypatch.setattr(app.tools, "_today", lambda: "2026-10-21")

    async def call(self, name, args):
        team = lambda a, s=None: {"abbrev": a, **({"score": s} if s is not None else {})}  # noqa: E731
        goalie = lambda n, gp, sv, gaa: {"first_name": n, "last_name": n, "team_abbrev": "X", "position_code": "G",  # noqa: E731
                                         "games_played": gp, "save_pctg": sv, "goals_against_avg": gaa, "wins": 1}
        routes = {
            "/standings/latest": STANDINGS, "/playoff-odds": ODDS,
            "/games/date/2026-10-20": {"games": [
                {"awayTeam": team("SJS", 4), "homeTeam": team("MTL", 3), "gameState": "OFF", "gameOutcome": {"lastPeriodType": "OT"}},
                {"awayTeam": team("COL", 3), "homeTeam": team("NJD", 4), "gameState": "FINAL", "gameOutcome": {"lastPeriodType": "REG"}}]},
            "/games/date/2026-10-21": {"games": [
                {"awayTeam": team("PHI", 1), "homeTeam": team("BUF", 0), "gameState": "LIVE", "periodDescriptor": {"number": 2}},
                {"awayTeam": team("FLA"), "homeTeam": team("OTT"), "gameState": "FUT", "startTimeUTC": "2026-10-21T23:30:00Z"}]},
            "/games/date/2026-10-22": {"games": []},
            "/players/leaders": [
                {"first_name": "Connor", "last_name": "McDavid", "team_abbrev": "EDM", "position_code": "C", "games_played": 9, "assists": 20, "points": 26},
                {"first_name": "Jack", "last_name": "Eichel", "team_abbrev": "VGK", "position_code": "C", "games_played": 11, "assists": 13, "points": 18},
                goalie("Hot", 1, 0.990, 0.5), goalie("Ullmark", 7, 0.945, 1.33), goalie("Oettinger", 7, 0.940, 1.13)],
            "/goalies/advanced": {"goalies": [{"name": "Lucky Night", "team": "X", "games_played": 1, "gsax": 3.0},
                                              {"name": "Linus Ullmark", "team": "OTT", "games_played": 7, "gsax": 8.5, "gsax_per_60": 1.21}]},
        }

        def handler(request):
            return httpx.Response(200, json=routes.get(request.url.path, {}))
        async with httpx.AsyncClient(base_url="https://dashboard.test", transport=httpx.MockTransport(handler)) as client:
            return json.loads(await ToolRunner(DashboardClient("https://dashboard.test", client)).run(name, json.dumps(args)))

    async def test_last_nights_finals_with_ot(self):
        result = await self.call("get_scores", {"date": "2026-10-20"})
        assert result["games"] == [{"game": "SJS @ MTL", "score": "SJS 4, MTL 3", "status": "Final (OT)"},
                                   {"game": "COL @ NJD", "score": "COL 3, NJD 4", "status": "Final"}]

    async def test_tonights_games_live_and_upcoming(self):
        result = await self.call("get_scores", {})
        assert result["games"] == [{"game": "PHI @ BUF", "score": "PHI 1, BUF 0", "status": "Live, 2nd period"},
                                   {"game": "FLA @ OTT", "status": "7:30 PM ET"}]
        assert "No NHL games" in (await self.call("get_scores", {"date": "2026-10-22"}))["note"]

    async def test_goalie_rate_stats_skip_one_hot_night(self):
        save = (await self.call("get_leaders", {"category": "save_pct"}))["save_pct"]
        assert [g["name"] for g in save] == ["Ullmark Ullmark", "Oettinger Oettinger"] and save[0]["save_pct"] == 0.945
        gaa = (await self.call("get_leaders", {"category": "gaa"}))["gaa"]
        assert [g["name"] for g in gaa] == ["Oettinger Oettinger", "Ullmark Ullmark"] and gaa[0]["gaa"] == 1.13
        gsax = await self.call("get_leaders", {"category": "gsax"})
        assert [g["name"] for g in gsax["gsax"]] == ["Linus Ullmark"] and "above 0" in gsax["note"]

    async def test_assists_and_bad_categories(self):
        assists = (await self.call("get_leaders", {"category": "assists"}))["assists"]
        assert [(p["name"], p["a"]) for p in assists] == [("Connor McDavid", 20), ("Jack Eichel", 13)]
        assert "category must be" in (await self.call("get_leaders", {"category": "hits"}))["error"]

    async def test_league_standings_come_as_a_table_with_names(self):
        result = await self.call("get_standings", {})
        assert result["columns"][0] == "name" and result["columns"][1] == "team"
        assert result["teams_best_first"][0][:2] == ["Colorado Avalanche", "COL"]


@pytest.mark.asyncio
class TestInjuryReturnTool:
    @pytest.fixture(autouse=True)
    def today(self, monkeypatch):
        import app.tools
        monkeypatch.setattr(app.tools, "_today", lambda: "2026-10-21")

    async def call(self, args, injured=True, seen=None):
        scenarios = {"healthy_now": {"playoff_pct": 0.993, "avg_points": 112.0},
                     "back_on_return_date": {"playoff_pct": 0.99, "avg_points": 111.2},
                     "out_for_season": {"playoff_pct": 0.962, "avg_points": 106.9}}
        routes = {
            "/players/leaders": [{"player_id": 8482093, "first_name": "Seth", "last_name": "Jarvis", "team_abbrev": "CAR", "position_code": "R"}],
            "/injuries": {"teams": {"CAR": [{"player": "Seth Jarvis", "status": "Injured Reserve", "injury": "Shoulder",
                                             "expected_return": "2026-11-01"}] if injured else []}},
            "/fantasy": {"updates": [{"player": "Seth Jarvis", "title": "Activated by Carolina", "summary": "Activated Wednesday.",
                                      "published": "2026-10-21T21:58:00Z"}]},
        }

        def handler(request):
            if seen is not None:
                seen.append(f"{request.url.path}?{request.url.query.decode()}")
            if request.url.path == "/season-sim/injury":
                back = request.url.params.get("back")
                body = {"player": "Seth Jarvis", "team": "CAR", "value_goals_per_game": 0.18, "expected_return": back,
                        "team_games_missed_before_return": 5 if back and back > "2026-10-21" else 0,
                        "scenarios": scenarios if back else {k: v for k, v in scenarios.items() if k != "back_on_return_date"}}
                return httpx.Response(200, json=body)
            return httpx.Response(200, json=routes.get(request.url.path, {}))
        async with httpx.AsyncClient(base_url="https://dashboard.test", transport=httpx.MockTransport(handler)) as client:
            return json.loads(await ToolRunner(DashboardClient("https://dashboard.test", client)).run("simulate_injury_return", json.dumps(args)))

    async def test_still_out_uses_his_expected_return(self):
        seen = []
        result = await self.call({"player": "Jarvis"}, seen=seen)
        assert any("player=8482093&back=2026-11-01" in s for s in seen)
        assert result["return_date_basis"] == "his expected return on the injury report"
        assert result["playoff_odds_pct"] == {"healthy_now": 99.3, "back_on_return_date": 99.0, "out_for_season": 96.2}
        assert result["worth_to_team_pct_points"] == 2.8 and result["team_games_missed_before_return"] == 5
        assert result["worth_to_team_standings_points"] == 4.3  # 111.2 back on Nov 1 vs 106.9 out
        assert result["injury_report"]["injury"] == "Shoulder" and "already counts" in result["how_to_read"]

    async def test_already_activated_counts_as_available_now(self):
        seen = []
        result = await self.call({"player": "Seth Jarvis"}, injured=False, seen=seen)
        assert any("back=2026-10-21" in s for s in seen)
        assert result["return_date_basis"] == "not on the injury report, so available now"
        assert result["latest_update"]["update"] == "Activated by Carolina" and "injury_report" not in result

    async def test_a_hypothetical_date(self):
        seen = []
        result = await self.call({"player": "Jarvis", "return_date": "2026-12-15"}, seen=seen)
        assert any("back=2026-12-15" in s for s in seen) and result["return_date_basis"] == "the date asked about"
        assert "return_date must be" in (await self.call({"player": "Jarvis", "return_date": "december"}))["error"]
