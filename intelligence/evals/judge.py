"""
LLM-as-a-judge for the fuzzy checks plain rules can't make ("did it read a
PDO of 91.9 as bad luck?"). A different provider grades than the one that
answered when possible, so a model isn't grading its own homework.
"""

import json
import re

from app.providers import ProviderChain

from .checks import CheckResult

JUDGE_SYSTEM = (
    "You grade answers from a hockey stats assistant against a rubric. Be strict and literal: "
    "pass only if the answer clearly meets the rubric. Reply with JSON only: "
    '{"pass": true or false, "reason": "one short sentence"}'
)


async def judge(chain: ProviderChain, question: str, answer: str, rubric: str) -> CheckResult:
    messages = [
        {"role": "system", "content": JUDGE_SYSTEM},
        {"role": "user", "content": f"Question: {question}\n\nAnswer: {answer}\n\nRubric: {rubric}"},
    ]
    # Reasoning models (Groq's gpt-oss) spend part of the budget thinking;
    # 200 tokens left it nothing to answer with.
    message, provider, _ = await chain.complete_with_tools(messages, None, 800)
    text = message.content or ""
    match = re.search(r"\{.*\}", text, re.S)
    try:
        verdict = json.loads(match.group(0)) if match else {}
    except ValueError:
        verdict = {}
    if "pass" not in verdict:
        return CheckResult("judge", False, f"unreadable verdict from {provider.name}: {text[:80]!r}")
    return CheckResult("judge", bool(verdict["pass"]), f"{provider.name}: {verdict.get('reason', '')}")
