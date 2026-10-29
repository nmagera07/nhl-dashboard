"""
The post drafting agent: given last night's candidate stories (found by
the backend's post_drafts.py, each with its facts), the model picks the
one most worth posting, may look up a detail for color (a scorer's
season, the box score), and drafts an X post and a Reddit title. The
creator approves (and edits) it in the post kit; nothing posts itself.

Guardrails, as for the briefs: every number must appear in the stories'
facts or the tool results; no betting-tip wording; length limits; the
pick must be one of the candidates. One rewrite, then no draft.
"""

import json
import logging
import re

from .briefs import BANNED, NUMBER_WORDS, unsourced_numbers
from .providers import ProviderChain
from .research import Draft, research_and_write
from .tools import TOOLS, ToolRunner

logger = logging.getLogger(__name__)

POST_TOOL_NAMES = ("find_player", "get_game", "get_team", "get_recent_results")
POST_TOOLS = [t for t in TOOLS if t["function"]["name"] in POST_TOOL_NAMES]
MAX_ROUNDS = 2
MAX_TOKENS = 1500
X_MAX = 230  # the link (23 characters on X) goes after it
REDDIT_MAX = 120

INSTRUCTIONS = f"""You draft one social media post a day for PuckPulse, a free NHL stats and betting-research site. Its owner reviews and edits it before posting; you never post.
You get last night's candidate stories with their facts. Pick the ONE most likely to interest hockey fans: drama, surprise, a big name, or playoff stakes beat routine results. You may call a tool or two for a color detail (a scorer's season totals, the box score), but the facts given are usually enough.
Write in a plain, confident fan voice: specific, no hype words, no hashtags, at most one emoji. Say "PuckPulse's" model or win probability when you cite one of its numbers. Never give betting advice, never call anything a lock or a sure thing.
Say how the game ended when it's part of the story (a comeback that still lost is the story).
Numbers: write them as digits, and use only numbers that appear in the facts or the tool results (rounding is fine). Never compute new ones.
Names: write players' names exactly as they appear in the facts or tool results. Never expand an initial ("J. Drysdale") into a first name you weren't given.
Reply in exactly this format, nothing else:
PICK: <the story id>
X: <the post for X, at most {X_MAX} characters; a link to the story is added after it>
REDDIT: <a title for r/hockey-style subreddits, at most {REDDIT_MAX} characters, no clickbait>"""

FORMAT = re.compile(r"^PICK:\s*(?P<pick>\S+)\s*\nX:\s*(?P<x>.+?)\s*\nREDDIT:\s*(?P<reddit>.+?)\s*$", re.DOTALL)


def parse(text: str) -> dict | None:
    match = FORMAT.match(text.strip())
    return {k: v.strip() for k, v in match.groupdict().items()} if match else None


def check_post(ids: set[str]):
    """check(text, sources) for research_and_write, knowing the candidate ids."""
    def check(text: str, sources: str) -> list[str]:
        post = parse(text)
        if not post:
            return ["Reply in exactly the PICK / X / REDDIT format, one line each."]
        problems = []
        if post["pick"] not in ids:
            problems.append(f"PICK must be one of: {', '.join(sorted(ids))}.")
        if len(post["x"]) > X_MAX:
            problems.append(f"The X post is {len(post['x'])} characters; keep it to {X_MAX}.")
        if len(post["reddit"]) > REDDIT_MAX:
            problems.append(f"The Reddit title is {len(post['reddit'])} characters; keep it to {REDDIT_MAX}.")
        body = f"{post['x']}\n{post['reddit']}"
        banned = sorted({m.group(0).lower() for m in BANNED.finditer(body)})
        if banned:
            problems.append(f"Remove betting-tip wording: {', '.join(banned)}.")
        if "#" in body:
            problems.append("No hashtags.")
        words = sorted({m.group(0).lower() for m in NUMBER_WORDS.finditer(body)})
        if words:
            problems.append(f"Write numbers as digits from the facts, not words ({', '.join(words)}).")
        guessed = expanded_initials(body, sources)
        if guessed:
            problems.append("These first names aren't in the facts or tool results: " + ", ".join(guessed)
                            + ". Write the name as given (e.g. the initial).")
        unsourced = unsourced_numbers(body, sources)
        if unsourced:
            problems.append("These numbers aren't in the facts or tool results: " + ", ".join(unsourced) + ".")
        return problems
    return check


INITIAL = re.compile(r"\b([A-Z])\. ([A-Z][\w'-]*\w)")  # "J. Drysdale", "R. O'Reilly"


def expanded_initials(text: str, sources: str) -> list[str]:
    """Full names in text for players the sources only give as an initial ("J. Drysdale" -> "Jamie Drysdale")."""
    guessed = []
    for initial, surname in set(INITIAL.findall(sources)):
        for first in re.findall(rf"\b({initial}[a-z]+) {re.escape(surname)}\b", text):
            if f"{first} {surname}" not in sources:
                guessed.append(f"{first} {surname}")
    return sorted(set(guessed))


async def draft_post(chain: ProviderChain, runner: ToolRunner, day: str, candidates: list[dict]) -> tuple[dict | None, Draft]:
    """
    (the parsed post {pick, x, reddit} or None, the draft with model/problems/tools).
    Raises AllProvidersFailed if no provider answers.
    """
    prompt = f"Last night: {day}.\nCandidate stories (JSON): {json.dumps(candidates, separators=(',', ':'))}"
    draft = await research_and_write(chain, runner, INSTRUCTIONS, prompt, POST_TOOLS, check_post({c["id"] for c in candidates}),
                                     MAX_ROUNDS, MAX_TOKENS, "Write the post now from what you have; no more tools.")
    if draft.text is None:
        logger.warning("No post draft for %s: %s", day, "; ".join(draft.problems))
        return None, draft
    return parse(draft.text), draft
