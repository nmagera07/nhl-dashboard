"""
Deterministic checks for eval answers. No AI involved: these are plain
rules, so they're cheap, instant, and never wrong about what they check.
"""

import json
import re
from dataclasses import dataclass

PERCENT = re.compile(r"(?<![\d.])(\d{1,3}(?:\.\d+)?)\s?%")


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str = ""


DASHES = str.maketrans({c: "-" for c in "\u2010\u2011\u2012\u2013\u2014\u2212"})


def _norm(text: str) -> str:
    """Lowercase, with every dash variant as '-': models write 8‑2 with a non-breaking hyphen."""
    return text.translate(DASHES).lower()


def mentions_any(answer: str, options, name="facts") -> CheckResult:
    """The answer mentions at least one of the options (case-insensitive, any dash style)."""
    options = [o for o in options if o]
    hit = next((o for o in options if _norm(o) in _norm(answer)), None)
    return CheckResult(name, hit is not None, f"found '{hit}'" if hit else f"expected one of {options}")


def score_mentioned(answer: str, us: int, them: int, name="facts") -> CheckResult:
    """
    The final score is in the answer: "2-3"/"3-2" (any dash), or both numbers
    stated in words ("Pittsburgh scored 2 goals while Columbus scored 3").
    """
    text = _norm(answer)
    if f"{us}-{them}" in text or f"{them}-{us}" in text:
        return CheckResult(name, True, f"found {us}-{them}")
    numbers = re.findall(r"(?<![\d.])\d+(?!\d|\.\d|\s?%)", text)  # whole numbers, not 3.5 or 3%
    ok = str(us) in numbers and str(them) in numbers
    return CheckResult(name, ok, f"both {us} and {them} stated" if ok else f"expected the score {us}-{them}")


def percent_near(answer: str, expected_pct: float, tolerance=1.0, name="number") -> CheckResult:
    """Some percentage in the answer is within `tolerance` points of the expected one."""
    found = [float(m) for m in PERCENT.findall(answer)]
    ok = any(abs(p - expected_pct) <= tolerance for p in found)
    return CheckResult(name, ok, f"expected ~{expected_pct:.1f}%, answer has {found or 'no percentages'}")


def _numbers(value):
    """Every number inside a JSON value."""
    if isinstance(value, bool):
        return
    if isinstance(value, (int, float)):
        yield float(value)
    elif isinstance(value, dict):
        for v in value.values():
            yield from _numbers(v)
    elif isinstance(value, list):
        for v in value:
            yield from _numbers(v)
    elif isinstance(value, str):
        for m in re.findall(r"-?\d+(?:\.\d+)?", value):
            yield float(m)


def grounded_percentages(answer: str, tool_results, context=None, tolerance=0.6) -> CheckResult:
    """
    Every percentage the answer states must come from the data it was given:
    a value in a tool result or the page context (fractions like 0.728 count
    as 72.8%), or the difference between two of them ("up 13 points"). A
    percentage with no source is a made-up number.
    """
    sources = []
    for raw in list(tool_results) + ([context] if context is not None else []):
        try:
            data = json.loads(raw) if isinstance(raw, str) else raw
        except ValueError:
            data = raw
        for n in _numbers(data):
            sources.append(n)
            if 0 <= n <= 1:
                sources.append(n * 100)
    pcts = [s for s in sources if 0 <= s <= 100]
    allowed = set(round(s, 1) for s in sources)
    allowed |= {round(abs(a - b), 1) for i, a in enumerate(pcts) for b in pcts[i + 1:]}
    stated = [float(m) for m in PERCENT.findall(answer)]
    made_up = [p for p in stated if not any(abs(p - a) <= tolerance for a in allowed)]
    return CheckResult("grounded", not made_up,
                       f"unsourced: {made_up}" if made_up else f"{len(stated)} percentage(s), all sourced")


def tool_called(trace, names, args=None) -> CheckResult:
    """The agent called one of `names` (with these arguments, if given)."""
    names = [names] if isinstance(names, str) else list(names)
    for name, raw_args, _ in trace:
        if name not in names:
            continue
        try:
            got = json.loads(raw_args or "{}") if isinstance(raw_args, str) else dict(raw_args or {})
        except ValueError:
            got = {}
        if all(str(got.get(k, "")).upper() == str(v).upper() for k, v in (args or {}).items()):
            return CheckResult("tool", True, f"{name}({got})")
    called = [f"{n}({a})" for n, a, _ in trace] or ["no tools"]
    want = f"{'/'.join(names)}{args or ''}"
    return CheckResult("tool", False, f"wanted {want}, called {', '.join(called)}")
