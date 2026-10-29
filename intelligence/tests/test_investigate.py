import json

import httpx
import pytest

from app import investigate
from app.investigate import Lookups, check_explanation, explain
from app.providers import Provider, ProviderChain
from tests.fakes import fake_factory, tool_call

REPORT = {"date": "2026-10-14", "failures": [{"name": "Last night: 5-on-5 shift data", "detail": "missing NJD @ DET (2026020090)"}],
          "history": [{"date": "2026-10-13", "failed": []}]}
GOOD = ("Shift chart missing for NJD @ DET (2026020090), but the time-on-ice reports are posted.\n"
        "Action: none, it fixes itself on the next run.")


def nhl(request):
    url = str(request.url)
    if "shiftcharts" in url:
        return httpx.Response(200, json={"data": []})
    if "htmlreports" in url:
        return httpx.Response(200, text="<html>")
    if "/boxscore" in url:
        return httpx.Response(200, json={"gameState": "OFF", "gameDate": "2026-10-13", "awayTeam": {"abbrev": "NJD"},
                                         "homeTeam": {"abbrev": "DET"}})
    if "/score/" in url:
        return httpx.Response(200, json={"games": [{"id": 2026020090, "gameType": 2, "gameState": "PPD",
                                                    "awayTeam": {"abbrev": "NJD"}, "homeTeam": {"abbrev": "DET"}}]})
    return httpx.Response(404)


def lookups():
    return Lookups(httpx.AsyncClient(transport=httpx.MockTransport(nhl)))


class TestLookups:
    @pytest.mark.asyncio
    async def test_off_reads_as_final(self):
        result = json.loads(await lookups().run("nhl_game_status", '{"game_id": 2026020090}'))
        assert result == {"game_id": 2026020090, "status": "final", "final": True, "date": "2026-10-13", "away": "NJD",
                          "home": "DET"}

    @pytest.mark.asyncio
    async def test_shift_data_reports_the_chart_and_the_backup(self):
        result = json.loads(await lookups().run("nhl_shift_data", '{"game_id": 2026020090}'))
        assert result == {"game_id": 2026020090, "shift_chart_rows": 0, "shift_chart_posted": False,
                          "toi_reports_posted": {"home": True, "away": True}}

    @pytest.mark.asyncio
    async def test_schedule_in_plain_words(self):
        result = json.loads(await lookups().run("nhl_schedule", '{"date": "2026-10-13"}'))
        assert result["games"] == [{"game_id": 2026020090, "away": "NJD", "home": "DET", "status": "postponed"}]

    @pytest.mark.asyncio
    async def test_bad_arguments_never_reach_the_nhl(self):
        calls = []
        client = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: calls.append(r) or httpx.Response(200, json={})))
        assert "error" in json.loads(await Lookups(client).run("nhl_game_status", '{"game_id": 1}'))
        assert "error" in json.loads(await Lookups(client).run("nhl_schedule", '{"date": "../../etc"}'))
        assert "error" in json.loads(await Lookups(client).run("drop_tables", "{}"))
        assert calls == []


class TestCheck:
    SOURCES = json.dumps(REPORT)

    def test_two_lines_with_an_action(self):
        assert check_explanation(GOOD, self.SOURCES) == []
        assert check_explanation("Shift chart missing.", self.SOURCES)
        assert check_explanation("Shift chart missing.\nNothing to do.", self.SOURCES)

    def test_numbers_must_come_from_the_report_or_lookups(self):
        problems = check_explanation("Shift chart missing for 3 games.\nAction: none.", self.SOURCES)
        assert problems and "3" in problems[0]


def chain(turns, calls):
    return ProviderChain([Provider("groq", "Groq", None, "k", "m")], client_factory=fake_factory({"groq": turns}, calls))


@pytest.mark.asyncio
async def test_the_investigator_looks_things_up_then_explains():
    calls = []
    turns = ([tool_call("nhl_shift_data", '{"game_id":2026020090}'),
              tool_call("nhl_game_status", '{"game_id":2026020090}', "call_2")], GOOD)

    draft = await explain(chain(turns, calls), lookups(), REPORT)

    assert draft.text == GOOD and draft.tools == ['nhl_shift_data({"game_id":2026020090})',
                                                  'nhl_game_status({"game_id":2026020090})']
    assert {t["function"]["name"] for t in calls[0][1]["tools"]} == {"nhl_game_status", "nhl_shift_data", "nhl_schedule"}
    assert "missing NJD @ DET (2026020090)" in calls[0][1]["messages"][1]["content"]
    assert "war.py" in calls[0][1]["messages"][0]["content"]  # the runbook names each check's script


@pytest.mark.asyncio
async def test_no_explanation_when_the_rewrite_fails_too():
    turns = ("Something broke.", "Something broke again.")
    draft = await explain(chain(turns, []), lookups(), REPORT)
    assert draft.text is None and draft.problems


def test_runbook_covers_every_check_the_backend_runs():
    # Names from backend/data_checks.py: if a check is added there, give it a runbook line here.
    for name in ("updated", "Last night: xG", "Last night: 5-on-5 shift data", "Last night: WAR v2 stints",
                 "Last night: Result", "Last night: predictions graded", "Today: predictions logged",
                 "Swing of the Night saved", "Playoff odds add up", "Last night's xG in range"):
        assert name in investigate.RUNBOOK, name
