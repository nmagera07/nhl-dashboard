"""
Run NHL Intelligence's eval suite against real providers:

    cd intelligence && .venv/bin/python -m evals.run                 # every case, gemini and groq
    .venv/bin/python -m evals.run --providers groq --cases scenario,pdo_reading

Each case's correct answer is computed live from the dashboard API, the
agent answers it exactly as the app would, and the answer is scored on:
tool (right tool and arguments), facts / number (right answer), grounded
(no percentages without a source), and judge (fuzzy rubric, graded by a
different provider). Results print as a scorecard and are saved to
evals/results/ so runs can be compared over time.

Uses real free-tier requests (~2-3 per case per provider, plus judge
calls), so it runs on demand rather than in CI. Cases are paced per
provider to stay under per-minute token caps.
"""

import argparse
import asyncio
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv

from app.config import Settings
from app.dashboard import DashboardClient
from app.main import ChatContext, ChatRequest, IntelligenceService
from app.providers import ProviderChain, providers_from_env

from .cases import CASES
from .checks import grounded_percentages, mentions_any, percent_near, tool_called
from .judge import judge

DEFAULT_API = "https://nhl-dashboard-api.bravecoast-a5240643.westus2.azurecontainerapps.io"
PACE_SECONDS = {"groq": 30, "gemini": 6}  # Groq's free tier caps tokens per minute
RESULTS = Path(__file__).parent / "results"
JUDGES = ("gemini", "groq")


async def run_case(service, case, truth, judge_chain):
    calls = 0
    real = service.chain.complete_with_tools

    async def counted(*args, **kwargs):
        nonlocal calls
        calls += 1
        return await real(*args, **kwargs)

    service.chain.complete_with_tools = counted
    trace, answer, error = [], "", None
    started = time.monotonic()
    try:
        request = ChatRequest(message=case.question, context=ChatContext(**case.context))
        async for event in service.run_agent(request):
            if event[0] == "tool_result":
                trace.append(event[1:])
            elif event[0] == "answer":
                answer = event[1]
    except Exception as exc:  # a provider outage or rate limit is a failed case, not a crashed run
        error = f"{type(exc).__name__}: {exc}"
    finally:
        service.chain.complete_with_tools = real
    seconds = time.monotonic() - started

    checks = []
    if error:
        checks.append({"name": "answered", "passed": False, "detail": error})
    else:
        if truth.get("tool"):
            names, args = truth["tool"]
            checks.append(vars(tool_called(trace, names, args)))
        if truth.get("facts"):
            checks.append(vars(mentions_any(answer, truth["facts"])))
        if truth.get("percent") is not None:
            checks.append(vars(percent_near(answer, truth["percent"])))
        checks.append(vars(grounded_percentages(answer, [r for _, _, r in trace])))
        if truth.get("rubric"):
            checks.append(vars(await judge(judge_chain, case.question, answer, truth["rubric"])))
    return {
        "case": case.id, "question": case.question, "answer": answer, "seconds": round(seconds, 1),
        "model_calls": calls, "tools": [f"{n}({a})" for n, a, _ in trace], "checks": checks,
        "passed": all(c["passed"] for c in checks),
    }


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--providers", default="gemini,groq")
    parser.add_argument("--cases", default="", help="comma-separated case ids (default: all)")
    parser.add_argument("--api", default=os.getenv("NHL_DASHBOARD_API_URL", DEFAULT_API))
    args = parser.parse_args()

    load_dotenv()
    available = {p.name: p for p in providers_from_env()}
    wanted = [n.strip() for n in args.providers.split(",") if n.strip()]
    missing = [n for n in wanted if n not in available]
    if missing:
        raise SystemExit(f"No API key configured for: {', '.join(missing)}")
    cases = [c for c in CASES if not args.cases or c.id in args.cases.split(",")]

    async with httpx.AsyncClient(base_url=args.api, timeout=60) as http:
        async def api(path):
            response = await http.get(path)
            response.raise_for_status()
            return response.json()

        truths = {}
        for case in cases:  # one truth per case, shared by every provider
            truths[case.id] = await case.truth(api)

        report = {"started": datetime.now(timezone.utc).isoformat(timespec="seconds"), "api": args.api, "runs": {}}
        for name in wanted:
            provider = available[name]
            # Only strong hosted models judge; a small local model misgraded a correct answer.
            judges = [p for p in available.values() if p.name in JUDGES and p.name != name] or [provider]
            service = IntelligenceService(
                Settings(args.api, [], providers=[provider]),
                dashboard=DashboardClient(args.api), chain=ProviderChain([provider]),
            )
            results = []
            for i, case in enumerate(cases):
                if truths[case.id].get("skip"):
                    results.append({"case": case.id, "skipped": truths[case.id]["skip"], "passed": True, "checks": []})
                    continue
                if i:
                    await asyncio.sleep(PACE_SECONDS.get(name, 10))
                result = await run_case(service, case, truths[case.id], ProviderChain(judges))
                results.append(result)
                mark = "✓" if result["passed"] else "✗"
                fails = "; ".join(f"{c['name']}: {c['detail']}" for c in result["checks"] if not c["passed"])
                print(f"  {mark} {name:<7} {case.id:<18} {result['seconds']:>5}s  {result['model_calls']} calls  {fails}", flush=True)
            report["runs"][name] = {"model": provider.model, "results": results}

    print("\nScorecard")
    check_names = ["tool", "facts", "number", "grounded", "judge"]
    print(f"  {'provider':<9}{'cases':>8}  " + "  ".join(f"{c:>8}" for c in check_names))
    for name, run in report["runs"].items():
        scored = [r for r in run["results"] if "skipped" not in r]
        row = []
        for check in check_names:
            relevant = [c for r in scored for c in r["checks"] if c["name"] == check]
            row.append(f"{sum(c['passed'] for c in relevant)}/{len(relevant)}" if relevant else "-")
        passed = sum(r["passed"] for r in scored)
        print(f"  {name:<9}{passed:>4}/{len(scored):<3}  " + "  ".join(f"{v:>8}" for v in row))

    RESULTS.mkdir(exist_ok=True)
    path = RESULTS / f"{datetime.now().strftime('%Y-%m-%d_%H%M')}.json"
    path.write_text(json.dumps(report, indent=2))
    print(f"\nSaved {path.relative_to(Path.cwd()) if path.is_relative_to(Path.cwd()) else path}")


if __name__ == "__main__":
    asyncio.run(main())
