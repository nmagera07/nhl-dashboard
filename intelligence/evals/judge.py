"""
LLM-as-a-judge for the fuzzy checks plain rules can't make ("did it read a
PDO of 91.9 as bad luck?"). A different provider grades than the one that
answered when possible, so a model isn't grading its own homework.
"""

import json
import re

from app.providers import AllProvidersFailed, ProviderChain

from .checks import CheckResult

JUDGE_SYSTEM = (
    "You grade answers from a hockey stats assistant against a rubric. Be strict and literal: "
    "pass only if the answer clearly meets the rubric. If it fails, quote the answer's exact words that fail "
    "(re-read them first: don't fail an answer for something it doesn't say). Reply with JSON only: "
    '{"pass": true or false, "reason": "one short sentence"}'
)


MAX_SOURCE_CHARS = 12000  # Groq's free tier caps tokens per minute


async def judge(chain: ProviderChain, question: str, answer: str, rubric: str, sources: str | None = None) -> CheckResult:
    """sources: the data the writer had, so the judge can check claims against it, not just read them."""
    data = f"\n\nData the writer had:\n{sources[:MAX_SOURCE_CHARS]}" if sources else ""
    messages = [
        {"role": "system", "content": JUDGE_SYSTEM},
        {"role": "user", "content": f"Question: {question}{data}\n\nAnswer: {answer}\n\nRubric: {rubric}"},
    ]
    # Reasoning models (Groq's gpt-oss) spend part of the budget thinking;
    # 200 tokens left it nothing to answer with.
    try:
        message, provider, _ = await chain.complete_with_tools(messages, None, 800)
    except AllProvidersFailed:  # a busy judge is a failed check, not a crashed run
        return CheckResult("judge", False, "no judge available (rate limited)")
    text = message.content or ""
    match = re.search(r"\{.*\}", text, re.S)
    try:
        verdict = json.loads(match.group(0)) if match else {}
    except ValueError:
        verdict = {}
    if "pass" not in verdict:
        return CheckResult("judge", False, f"unreadable verdict from {provider.name}: {text[:80]!r}")
    return CheckResult("judge", bool(verdict["pass"]), f"{provider.name}: {verdict.get('reason', '')}")
