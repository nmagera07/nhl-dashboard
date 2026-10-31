"""
Known data-check failures for the investigator evals (evals/agents.py).
Each is a report like the morning check sends, the NHL lookups' answers
(fixed, so a case plays out the same every run), and what a good
explanation does: the lookups it makes, its Action line ("none", or the
script to look at), and words its cause line should use.
"""

from dataclasses import dataclass, field

DAY = "2026-10-31"
FLA, VGK, CGY = 2026020215, 2026020214, 2026020216
WPG_FLA = f"WPG @ FLA ({FLA})"


def status(game_id, state, away, home, final=None):
    return {"game_id": game_id, "status": state, "final": state == "final" if final is None else final,
            "date": "2026-10-30", "away": away, "home": home}


def shifts(game_id, rows, home_report, away_report):
    return {"game_id": game_id, "shift_chart_rows": rows, "shift_chart_posted": rows >= 100,
            "toi_reports_posted": {"home": home_report, "away": away_report}}


@dataclass
class Case:
    id: str
    failures: list[dict]
    lookups: dict = field(default_factory=dict)  # {(tool, game_id or date as text): result}
    must_call: list[tuple[str, str]] = field(default_factory=list)
    action: str | None = None  # "none", "investigate" (anything but none), or a script it should name
    cause: list[str] = field(default_factory=list)  # the cause line mentions one of these
    rubric: str = ""
    history: list[dict] = field(default_factory=list)

    @property
    def report(self) -> dict:
        return {"date": DAY, "failures": self.failures, "history": self.history}


CASES = [
    Case(
        "shift_chart_late",
        [{"name": "Last night: 5-on-5 shift data", "detail": f"missing {WPG_FLA}"},
         {"name": "Last night: WAR v2 stints", "detail": f"missing {WPG_FLA}"}],
        {("nhl_game_status", str(FLA)): status(FLA, "final", "WPG", "FLA"),
         ("nhl_shift_data", str(FLA)): shifts(FLA, 0, True, True)},
        [("nhl_shift_data", str(FLA)), ("nhl_game_status", str(FLA))],
        "none", ["time-on-ice", "time on ice", "TOI"],
        "Pass only if it says the shift chart isn't posted but the time-on-ice reports are, and that the next "
        "nightly run fills it in, so nothing needs doing.",
    ),
    Case(
        "nothing_posted_yet",
        [{"name": "Last night: xG", "detail": f"missing {WPG_FLA}"},
         {"name": "Last night: 5-on-5 shift data", "detail": f"missing {WPG_FLA}"}],
        {("nhl_game_status", str(FLA)): status(FLA, "final", "WPG", "FLA"),
         ("nhl_shift_data", str(FLA)): shifts(FLA, 0, False, False)},
        [("nhl_shift_data", str(FLA)), ("nhl_game_status", str(FLA))],
        "none", ["shift chart", "shift data", "posted"],
        "Pass only if it says the NHL hasn't posted the shift chart or the time-on-ice reports yet and that the "
        "nightly run keeps retrying, so it fixes itself.",
    ),
    Case(
        "postponed",
        [{"name": "Last night: Result", "detail": f"missing SEA @ CGY ({CGY})"},
         {"name": "Last night: predictions graded", "detail": f"ungraded SEA @ CGY ({CGY})"}],
        {("nhl_game_status", str(CGY)): status(CGY, "postponed", "SEA", "CGY")},
        [("nhl_game_status", str(CGY))],
        "none", ["postponed"],
        "Pass only if it says the game was postponed, so a missing result and grade are expected.",
    ),
    Case(
        # The NHL's "OFF" (shown to the agent as final) misled the first version into "not final yet".
        "final_but_no_result",
        [{"name": "Last night: Result", "detail": f"missing NJD @ VGK ({VGK})"}],
        {("nhl_game_status", str(VGK)): status(VGK, "final", "NJD", "VGK")},
        [("nhl_game_status", str(VGK))],
        "investigate", ["final"],
        "Pass only if it says the game is final, so its result should have been recorded and wasn't, and that "
        "this needs a look (the live notifier's logs); it must not say the game hasn't finished or that it fixes itself.",
    ),
    Case(
        "stale_war",
        [{"name": "WAR updated", "detail": "last updated 2026-10-30"}],
        action="war.py", cause=["war.py", "WAR"],
        rubric="Pass only if it says last night's war.py run failed or skipped and points at war.py in the job's "
               "logs (rerunning the job is a fine next step); it must not say it fixes itself or needs nothing.",
    ),
    Case(
        "playoff_odds_broken",
        [{"name": "Playoff odds add up", "detail": "32 teams, odds sum to 15.20 spots"}],
        action="simulate_playoff_odds.py", cause=["simulat", "playoff odds"],
        rubric="Pass only if it says the playoff odds simulation output is wrong (the odds should add up to the "
               "playoff spots) and points at simulate_playoff_odds.py.",
    ),
    Case(
        "recurring_standings",
        [{"name": "Standings updated", "detail": "last updated 2026-10-28"}],
        action="ingest_standings.py", cause=["ingest_standings", "Standings"],
        rubric="Pass only if it shows this isn't a one-off (several mornings in a row, or stale since Oct. 28) "
               "and points at ingest_standings.py.",
        history=[{"date": "2026-10-30", "failed": ["Standings updated"]},
                 {"date": "2026-10-29", "failed": ["Standings updated"]},
                 {"date": "2026-10-28", "failed": []}],
    ),
    Case(
        "lopsided_xg",
        [{"name": "Last night's xG in range", "detail": f"unusual: SEA 0.41 ({CGY})"}],
        {("nhl_game_status", str(CGY)): status(CGY, "final", "SEA", "CGY")},
        [("nhl_game_status", str(CGY))],
        "investigate", ["SEA", "lopsided", "0.41"],
        rubric="Pass only if it explains that the unusual xG is either a genuinely lopsided game or a play-by-play "
               "feed problem, without claiming to know which, and gives a next step (such as comparing with the "
               "box score); it must not say it fixes itself.",
    ),
]
