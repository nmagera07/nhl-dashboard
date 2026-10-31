"""
Evals for the scheduled agents, the pregame brief and the data-check
investigator:

    cd intelligence && .venv/bin/python -m evals.agents briefs              # today's games not yet started
    .venv/bin/python -m evals.agents briefs --providers groq --games 3
    .venv/bin/python -m evals.agents investigator --cases postponed,stale_war

Briefs run live, exactly as the scheduled job does, on today's slate. Each
is scored on: published (some draft passed the code checks), first_draft
(no rewrite needed), goalie_status (no one called "confirmed" who isn't),
back_to_back and odds_on_team (a real fact on the right team), judge (a
different provider grades it against the data the writer had), and
goalies_named (coverage, informational: doesn't fail a brief).

Investigator cases replay known failures against fixed NHL lookups, so
they're repeatable; each is scored on the lookups it made, its Action
line, the cause it names, and a judge.

Like evals.run: real free-tier requests, on demand, results saved to
evals/results/.
"""

import argparse
import asyncio
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv

from app import briefs, investigate
from app.dashboard import DashboardClient
from app.main import today_eastern
from app.providers import ProviderChain, providers_from_env
from app.tools import ToolRunner

from .checks import (CheckResult, action_matches, back_to_back, bet_prices, goalie_status, goalies_named,
                     mentions_any, odds_on_team, team_aliases)
from .investigator_cases import CASES as INVESTIGATOR_CASES
from .judge import judge
from .run import DEFAULT_API, JUDGES, RESULTS

# A brief is ~2 calls of ~5k tokens; Groq's free tier allows ~8k a minute.
PACE_SECONDS = {"groq": 60, "gemini": 8}
INFO_CHECKS = {"goalies_named"}  # reported, but don't fail a case

BRIEF_RUBRIC = (
    "Pass only if every claim matches the data the writer had (right team for each price, injury, and goalie; "
    "a goalie's status as given; no invented facts), the bullets are useful to someone deciding whether to bet "
    "this game rather than filler (it picks 3 of: goalies, key absences, rest, recent form, price vs. "
    "PuckPulse's fair price; it needn't cover all), and nothing "
    "tells the reader to bet or calls a bet a sure thing.")


class Recorder:
    """Wraps a tool runner and keeps every result, so checks see what the agent saw."""

    def __init__(self, runner):
        self.runner, self.results = runner, []

    async def run(self, name, arguments):
        output = await self.runner.run(name, arguments)
        self.results.append(output)
        return output


def _status(board: dict, side: str) -> tuple[str, str] | None:
    """(name, confirmed / expected / projected) for a side's starter, the way briefs' get_lineup ranks them."""
    reported = (board.get("reported_starters") or {}).get(side)
    if reported:
        return reported["name"], reported.get("status", "expected").lower()
    nhl = (board.get("nhl_starters") or {}).get(side)
    if nhl:
        return nhl, "projected"
    top = ((board.get("goalies") or {}).get(side) or [None])[0]
    return (top["name"], "projected") if top else None


async def brief_games(api, limit: int) -> list[dict]:
    """Today's games not yet started, with what the checks need to know about each."""
    day = datetime.strptime(today_eastern(), "%A, %B %d, %Y").date().isoformat()
    board, scores = await api(f"/bets?date={day}"), await api(f"/games/date/{day}")
    states = {str(g["id"]): g.get("gameState") for g in scores.get("games", [])}
    games = []
    for game_id, b in (board.get("games") or {}).items():
        if states.get(game_id) not in ("FUT", "PRE"):
            continue
        starters = dict(s for s in (_status(b, side) for side in ("away", "home")) if s)
        b2b = {b[side] for side in ("away", "home") if (b.get("b2b") or {}).get(side)}
        games.append({"game": briefs.Game(int(game_id), b["away"], b["home"], day), "starters": starters, "b2b": b2b})
    return games[:limit]


async def run_brief(chain, judge_chain, dashboard, case, aliases) -> dict:
    game = case["game"]
    recorder = Recorder(ToolRunner(dashboard))
    started = time.monotonic()
    try:
        draft = await briefs.write_brief(chain, recorder, game, today_eastern())
    except Exception as exc:  # a provider outage is a failed case, not a crashed run
        return {"case": f"{game.away}@{game.home}", "passed": False, "seconds": round(time.monotonic() - started, 1),
                "checks": [{"name": "published", "passed": False, "detail": f"{type(exc).__name__}: {exc}"}]}
    seconds = time.monotonic() - started
    checks = [CheckResult("published", draft.text is not None, "; ".join(draft.problems) or "ok"),
              CheckResult("first_draft", not draft.first_problems, "; ".join(draft.first_problems) or "no rewrite")]
    text = draft.text or ""
    if text:
        checks += [goalie_status(text, case["starters"]), back_to_back(text, case["b2b"], aliases),
                   odds_on_team(text, bet_prices(recorder.results), aliases), goalies_named(text, case["starters"])]
        checks.append(await judge(judge_chain, f"Pregame brief for {game.away} @ {game.home}", text, BRIEF_RUBRIC,
                                  sources="\n".join(recorder.results)))
    return {"case": f"{game.away}@{game.home}", "text": draft.text, "model": draft.model, "tools": draft.tools,
            "seconds": round(seconds, 1), "checks": [vars(c) for c in checks],
            "passed": all(c.passed for c in checks if c.name not in INFO_CHECKS)}


class FixedLookups:
    """The investigator's NHL lookups, answered from a case's fixtures."""

    def __init__(self, fixtures: dict):
        self.fixtures, self.calls = fixtures, []

    async def run(self, name, arguments):
        args = json.loads(arguments or "{}")
        key = args.get("game_id") or args.get("date")
        self.calls.append((name, str(key)))
        result = self.fixtures.get((name, str(key)), {"error": "Not found."})
        return json.dumps(result, separators=(",", ":"))


async def run_investigation(chain, judge_chain, case) -> dict:
    lookups = FixedLookups(case.lookups)
    started = time.monotonic()
    try:
        draft = await investigate.explain(chain, lookups, case.report)
    except Exception as exc:
        return {"case": case.id, "passed": False, "seconds": round(time.monotonic() - started, 1),
                "checks": [{"name": "published", "passed": False, "detail": f"{type(exc).__name__}: {exc}"}]}
    checks = [CheckResult("published", draft.text is not None, "; ".join(draft.problems) or "ok"),
              CheckResult("first_draft", not draft.first_problems, "; ".join(draft.first_problems) or "no rewrite")]
    missing = [f"{n}({k})" for n, k in case.must_call if (n, k) not in lookups.calls]
    checks.append(CheckResult("tool", not missing, f"didn't call {missing}" if missing else f"{len(lookups.calls)} lookups"))
    text = draft.text or ""
    if text:
        if case.action:
            checks.append(action_matches(text, case.action))
        if case.cause:
            checks.append(mentions_any(text.splitlines()[0], case.cause, name="cause"))
        sources = json.dumps({"report": case.report, "lookups": {f"{n}({k})": v for (n, k), v in case.lookups.items()}})
        checks.append(await judge(judge_chain, "Explain this morning's failed data check", text, case.rubric, sources))
    return {"case": case.id, "text": draft.text, "model": draft.model, "lookups": lookups.calls,
            "seconds": round(time.monotonic() - started, 1), "checks": [vars(c) for c in checks],
            "passed": all(c.passed for c in checks)}


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("suite", choices=("briefs", "investigator"))
    parser.add_argument("--providers", default="gemini,groq")
    parser.add_argument("--games", type=int, default=5, help="briefs: how many of today's games")
    parser.add_argument("--cases", default="", help="investigator: comma-separated case ids (default: all)")
    parser.add_argument("--api", default=DEFAULT_API)
    args = parser.parse_args()

    load_dotenv()
    available = {p.name: p for p in providers_from_env()}
    wanted = [n.strip() for n in args.providers.split(",") if n.strip()]
    missing = [n for n in wanted if n not in available]
    if missing:
        raise SystemExit(f"No API key configured for: {', '.join(missing)}")

    async with httpx.AsyncClient(base_url=args.api, timeout=60) as http:
        async def api(path):
            response = await http.get(path)
            response.raise_for_status()
            return response.json()

        if args.suite == "briefs":
            cases = await brief_games(api, args.games)
            aliases = team_aliases(await api("/standings/latest"))
            if not cases:
                raise SystemExit("No games left to brief today.")
        else:
            cases = [c for c in INVESTIGATOR_CASES if not args.cases or c.id in args.cases.split(",")]

        report = {"suite": args.suite, "started": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                  "api": args.api, "runs": {}}
        for n, name in enumerate(wanted):
            if n:  # the last provider's cases were judged by this one: let its per-minute cap reset
                await asyncio.sleep(PACE_SECONDS.get(name, 10))
            provider = available[name]
            judges = [p for p in available.values() if p.name in JUDGES and p.name != name] or [provider]
            chain, judge_chain = ProviderChain([provider]), ProviderChain(judges)
            # Each case also calls the judge, so pace for the slower of the two (Groq's per-minute cap).
            pace = max(PACE_SECONDS.get(p.name, 10) for p in [provider, *judges])
            results = []
            for i, case in enumerate(cases):
                if i:
                    await asyncio.sleep(pace)
                if args.suite == "briefs":
                    result = await run_brief(chain, judge_chain, DashboardClient(args.api), case, aliases)
                else:
                    result = await run_investigation(chain, judge_chain, case)
                results.append(result)
                mark = "✓" if result["passed"] else "✗"
                fails = "; ".join(f"{c['name']}: {c['detail']}" for c in result["checks"]
                                  if not c["passed"] and c["name"] not in INFO_CHECKS)
                print(f"  {mark} {name:<7} {result['case']:<22} {result['seconds']:>5}s  {fails}", flush=True)
            report["runs"][name] = {"model": provider.model, "results": results}

    print("\nScorecard")
    names = list(dict.fromkeys(c["name"] for run in report["runs"].values() for r in run["results"] for c in r["checks"]))
    print(f"  {'provider':<9}{'cases':>8}  " + "  ".join(f"{n[:13]:>13}" for n in names))
    for name, run in report["runs"].items():
        row = []
        for check in names:
            relevant = [c for r in run["results"] for c in r["checks"] if c["name"] == check]
            row.append(f"{sum(c['passed'] for c in relevant)}/{len(relevant)}" if relevant else "-")
        passed = sum(r["passed"] for r in run["results"])
        print(f"  {name:<9}{passed:>4}/{len(run['results']):<3}  " + "  ".join(f"{v:>13}" for v in row))

    RESULTS.mkdir(exist_ok=True)
    path = RESULTS / f"{args.suite}_{datetime.now().strftime('%Y-%m-%d_%H%M')}.json"
    path.write_text(json.dumps(report, indent=2, default=str))
    print(f"\nSaved {path}")


if __name__ == "__main__":
    asyncio.run(main())
