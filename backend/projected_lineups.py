"""
Tonight's projected lineups from NHL.com: for every game, NHL.com posts a
"{Away} at {Home} projected lineups" article a few hours before puck drop
(for a 6 p.m. game, around 2 p.m.) with each team's forward lines (left
wing, center, right wing), defense pairs, goalies (the projected starter
first), scratches, and injuries.

The article comes from the NHL's content API (the one the news feed
uses), at a predictable address: the two teams' full names and the date,
e.g. columbus-blue-jackets-minnesota-wild-game-preview-october-18-2026.
Only the lineup facts are kept, not NHL.com's writing; the page credits
and links the article for the full status report.
"""

import re
import unicodedata
from datetime import date

import requests

STORY_URL = "https://forge-dapi.d3.nhle.com/v2/content/en-us/stories/{slug}"
ARTICLE_URL = "https://www.nhl.com/news/{slug}"
HEADERS = {"User-Agent": "nhl-dashboard (personal project)"}
MONTHS = ("january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
          "november", "december")


def slugify(text):
    """'Montréal Canadiens' -> 'montreal-canadiens', 'St. Louis Blues' -> 'st-louis-blues'."""
    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", plain).strip("-")


def article_slug(away_name, home_name, day: date):
    return f"{slugify(away_name)}-{slugify(home_name)}-game-preview-{MONTHS[day.month - 1]}-{day.day}-{day.year}"


def _clean(line):
    """Strip markdown emphasis and trailing spaces: '***Scratched:** A, B*' -> 'Scratched: A, B'."""
    return re.sub(r"[*_]+", "", line).strip()


def _names(text):
    return [n.strip() for n in text.split(",") if n.strip() and n.strip().lower() != "none"]


def _injured(text):
    """'Dante Fabbro (broken hand), Ivan Provorov (lower body)' -> [{"name", "detail"}]."""
    out = []
    for part in re.findall(r"[^,(]+(?:\([^)]*\))?", text):
        part = part.strip()
        if not part or part.lower() == "none":
            continue
        m = re.match(r"(.+?)\s*\((.+)\)$", part)
        out.append({"name": m[1].strip(), "detail": m[2].strip()} if m else {"name": part, "detail": None})
    return out


def _split_by_position(entries):
    """
    The player lines, in article order, as forwards / defense / goalies.
    Read from the bottom up, since an 11-forward night has a two-man fourth
    line and lists the seventh defenseman alone: the last two single names
    are the goalies (starter first), single names just above them are extra
    defensemen, the last three two-man lines are the pairs, and everything
    above is forward lines.
    """
    entries = list(entries)
    singles = []
    while entries and len(entries[-1]) == 1:
        singles.insert(0, entries.pop()[0])
    goalies = singles[-2:]
    extra_d = singles[:-2]
    pairs = []
    while entries and len(entries[-1]) == 2 and len(pairs) < 3:
        pairs.insert(0, entries.pop())
    defense = pairs + [[d] for d in extra_d]
    return {"forwards": entries, "defense": defense, "goalies": goalies}


def parse(markdown):
    """
    {team nickname as written ("Blue Jackets"): {"forwards": [[LW, C, RW], ...],
    "defense": [[D, D], ..., maybe [extra D]], "goalies": [starter, backup],
    "scratched": [...], "injured": [{"name", "detail"}]}} from the article's
    markdown.
    """
    teams, entries, current = {}, {}, None
    for raw in markdown.splitlines():
        line = _clean(raw)
        if not line:
            continue
        header = re.match(r"(.+?) projected lineup$", line, re.IGNORECASE)
        if header:
            current = header[1].strip()
            teams[current] = {"scratched": [], "injured": []}
            entries[current] = []
            continue
        if current is None:
            continue
        lower = line.lower()
        if lower.startswith("status report"):
            current = None
        elif lower.startswith("scratched:"):
            teams[current]["scratched"] = _names(line.split(":", 1)[1])
        elif lower.startswith("injured:"):
            teams[current]["injured"] = _injured(line.split(":", 1)[1])
        elif not teams[current]["scratched"] and not teams[current]["injured"]:
            players = [p.strip() for p in re.split(r"\s*(?:--|—|–)\s*", line) if p.strip()]
            if 1 <= len(players) <= 3 and all(len(p.split()) <= 4 for p in players):
                entries[current].append(players)
    for team, rows in entries.items():
        teams[team].update(_split_by_position(rows))
    return teams


def lineup(away_name, home_name, day: date, get=None):
    """
    {"url", "published", "away": {...}, "home": {...}} for a game, or None
    before NHL.com posts it. away_name/home_name: full team names. The
    article lists the away team first.
    """
    slug = article_slug(away_name, home_name, day)
    if get is None:
        response = requests.get(STORY_URL.format(slug=slug), headers=HEADERS, timeout=15)
        if response.status_code == 404:
            return None
        response.raise_for_status()
        story = response.json()
    else:
        story = get(STORY_URL.format(slug=slug))
        if story is None:
            return None
    markdown = "\n".join(p.get("content", "") for p in story.get("parts", []) if p.get("type") == "markdown")
    teams = list(parse(markdown).values())
    if len(teams) != 2 or not all(t["forwards"] for t in teams):
        return None  # not a lineup article we can read
    return {"url": ARTICLE_URL.format(slug=slug), "published": story.get("contentDate"),
            "away": teams[0], "home": teams[1]}
