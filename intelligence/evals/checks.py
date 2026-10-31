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


# Agent checks: the pregame brief and the data-check investigator. A brief's
# numbers are already checked in code before it's published (briefs.py);
# these check what that can't: a real fact attached to the wrong thing.

ODDS = re.compile(r"(?<![\w.])([+\-−])(\d{3,})(?![\d.])")
from app.briefs import CLAUSE  # noqa: E402 -- the same clauses the brief's own checks use
STATUS = re.compile(r"\b(confirmed|expected|projected|likely|probable)\b", re.I)


def _clauses(text: str):
    """[(line, clause)] for each clause of each line."""
    return [(i, c) for i, line in enumerate(text.splitlines()) for c in CLAUSE.split(line) if c.strip()]


def team_aliases(standings) -> dict[str, list[str]]:
    """{abbrev: names a writer uses}: PIT, Pittsburgh Penguins, Penguins, Pittsburgh (and Montreal for Montréal)."""
    import unicodedata
    out = {}
    for row in standings:
        full, common = row.get("team_name") or "", row.get("common_name") or ""
        names = [full, common, full.replace(common, "").strip()]
        names += [unicodedata.normalize("NFKD", n).encode("ascii", "ignore").decode() for n in names]
        out[row["team_abbrev"]] = list(dict.fromkeys(n for n in names if n))
    return out


def teams_in(text: str, aliases: dict[str, list[str]]) -> set[str]:
    found = set()
    for abbrev, names in aliases.items():
        if re.search(rf"\b{abbrev}\b", text) or any(re.search(rf"\b{re.escape(n)}\b", text, re.I) for n in names):
            found.add(abbrev)
    return found


def goalie_status(brief: str, starters: dict[str, str]) -> CheckResult:
    """
    A goalie called "confirmed" really is (starters: {name: status} with
    status confirmed / expected / projected). Calling a confirmed starter
    "projected" undersells it but isn't wrong, so only overclaiming fails.
    """
    wrong, notes = [], []
    for _, clause in _clauses(brief):
        for name, status in starters.items():
            if name.split()[-1].lower() not in clause.lower():
                continue
            said = {w.lower() for w in STATUS.findall(clause)}
            if "confirmed" in said and status != "confirmed":
                wrong.append(f"{name} called confirmed, really {status}")
            elif said and status == "confirmed" and "confirmed" not in said:
                notes.append(f"{name} called {'/'.join(sorted(said))}, really confirmed")
    detail = "; ".join(wrong or notes) or "no overclaimed starters"
    return CheckResult("goalie_status", not wrong, detail)


def goalies_named(brief: str, starters: dict[str, str]) -> CheckResult:
    """Coverage: every known starter is named (by last name). Informational."""
    missing = [n for n in starters if n.split()[-1].lower() not in brief.lower()]
    return CheckResult("goalies_named", not missing, f"missing {missing}" if missing else f"{len(starters)} named")


def back_to_back(brief: str, b2b_teams: set[str], aliases) -> CheckResult:
    """A bullet that says back-to-back names a team that really is on one."""
    bad = [line.strip() for line in brief.splitlines()
           if re.search(r"back[-‐‑ ]to[-‐‑ ]back", line, re.I) and not (teams_in(line, aliases) & b2b_teams)]
    return CheckResult("back_to_back", not bad, f"no team on one in: {bad[0][:80]}" if bad else "ok")


def odds_on_team(brief: str, prices: dict[str, set[str]], aliases) -> CheckResult:
    """
    Every American price is one the tools gave for a team named in the same
    clause (or the clause before it on that line, for "..., with PuckPulse's
    fair price at -194"). prices: {abbrev: {"-225", "-194", ...}}.
    """
    wrong, line_teams, last_line = [], set(), None
    for line, clause in _clauses(brief):
        if line != last_line:
            line_teams, last_line = set(), line
        named = teams_in(clause, aliases)
        scope = named or line_teams
        line_teams = named or line_teams
        for sign, digits in ODDS.findall(clause):
            price = ("-" if sign in "-−" else "+") + digits
            if scope and not any(price in prices.get(t, set()) for t in scope):
                wrong.append(f"{price} for {'/'.join(sorted(scope))}")
    return CheckResult("odds_on_team", not wrong, f"wrong team: {wrong}" if wrong else "every price on its team")


def bet_prices(tool_results) -> dict[str, set[str]]:
    """{abbrev: prices} from the get_bets results an agent saw (moneyline and puck line, best and fair)."""
    out = {}
    for raw in tool_results:
        try:
            data = json.loads(raw)
        except (TypeError, ValueError):
            continue
        for game in data.get("games", []) if isinstance(data, dict) else []:
            for market in ("moneyline", "puck_line"):
                for key, side in (game.get(market) or {}).items():
                    if isinstance(side, dict):
                        team = key.split()[0]
                        out.setdefault(team, set()).update(
                            p for p in (side.get("best_price"), side.get("puckpulse_fair_price")) if p)
    return out


def action_matches(text: str, expected: str) -> CheckResult:
    """
    The investigator's "Action:" line: expected "none" (it fixes itself, or
    nothing to do), "investigate" (anything but none), or a script name it
    should point at.
    """
    action = next((line for line in text.splitlines() if line.strip().startswith("Action:")), "")
    says_none = bool(re.search(r"\bnone\b|fix(es)? itself|no action|nothing to do", action, re.I))
    if expected == "none":
        ok = says_none
    elif expected == "investigate":
        ok = bool(action) and not says_none
    else:
        ok = expected.lower() in action.lower()
    return CheckResult("action", ok, f"wanted {expected!r}, got {action[:90]!r}")
