"""
News for the News tab, team pages, and PuckPulse AI: headlines that link
out, injuries, and transactions.

Sources (all public, none with a documented API, so each is parsed
defensively and fails on its own -- one source breaking never breaks the
others):
  - NHL.com stories   forge-dapi.d3.nhle.com (the feed nhl.com itself uses)
  - ESPN NHL news     site.api.espn.com .../hockey/nhl/news (its RSS feed stamps
                      every item with the feed's build time, so it can't be sorted)
  - Sportsnet RSS     sportsnet.ca/hockey/nhl/feed/
  - ESPN injuries     site.api.espn.com .../hockey/nhl/injuries
  - ESPN transactions site.api.espn.com .../hockey/nhl/transactions

We show headlines, short summaries, and facts, credit the source, and link
to the original. Each source is cached (NEWS_TTL etc.); if a refresh fails,
its last good copy is used for up to MAX_STALE_SECONDS.
"""

import email.utils
import html
import logging
import re
import threading
import time
import unicodedata
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import requests

logger = logging.getLogger(__name__)

NHL_STORIES_URL = "https://forge-dapi.d3.nhle.com/v2/content/en-us/stories?tags.slug=news&$limit=40"
ESPN_NEWS_URL = "https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/news?limit=40"
SPORTSNET_RSS_URL = "https://www.sportsnet.ca/hockey/nhl/feed/"
ESPN_INJURIES_URL = "https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/injuries"
ESPN_TRANSACTIONS_URL = "https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/transactions"
HEADERS = {"User-Agent": "PuckPulse (puckpulse.io; headlines link to the original)"}

NEWS_TTL = 15 * 60
INJURIES_TTL = 30 * 60
TRANSACTIONS_TTL = 30 * 60
MAX_STALE_SECONDS = 24 * 3600
MAX_HEADLINE_AGE = timedelta(days=7)
MAX_HEADLINES = 60

# abbrev -> (NHL team ids, full name). Ids tag NHL.com stories; Utah's
# changed from 59 (Utah Hockey Club) to 68 (Mammoth).
TEAMS = {
    "ANA": ((24,), "Anaheim Ducks"), "BOS": ((6,), "Boston Bruins"), "BUF": ((7,), "Buffalo Sabres"),
    "CAR": ((12,), "Carolina Hurricanes"), "CBJ": ((29,), "Columbus Blue Jackets"), "CGY": ((20,), "Calgary Flames"),
    "CHI": ((16,), "Chicago Blackhawks"), "COL": ((21,), "Colorado Avalanche"), "DAL": ((25,), "Dallas Stars"),
    "DET": ((17,), "Detroit Red Wings"), "EDM": ((22,), "Edmonton Oilers"), "FLA": ((13,), "Florida Panthers"),
    "LAK": ((26,), "Los Angeles Kings"), "MIN": ((30,), "Minnesota Wild"), "MTL": ((8,), "Montréal Canadiens"),
    "NJD": ((1,), "New Jersey Devils"), "NSH": ((18,), "Nashville Predators"), "NYI": ((2,), "New York Islanders"),
    "NYR": ((3,), "New York Rangers"), "OTT": ((9,), "Ottawa Senators"), "PHI": ((4,), "Philadelphia Flyers"),
    "PIT": ((5,), "Pittsburgh Penguins"), "SEA": ((55,), "Seattle Kraken"), "SJS": ((28,), "San Jose Sharks"),
    "STL": ((19,), "St. Louis Blues"), "TBL": ((14,), "Tampa Bay Lightning"), "TOR": ((10,), "Toronto Maple Leafs"),
    "UTA": ((59, 68), "Utah Mammoth"), "VAN": ((23,), "Vancouver Canucks"), "VGK": ((54,), "Vegas Golden Knights"),
    "WPG": ((52,), "Winnipeg Jets"), "WSH": ((15,), "Washington Capitals"),
}
_TWO_WORD = {"Red Wings", "Maple Leafs", "Golden Knights", "Blue Jackets"}


def _plain(text):
    """Accents off, so ESPN's "Montreal" and the NHL's "Montréal" match."""
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()


def _nickname(full_name):
    two = " ".join(full_name.split()[-2:])
    return two if two in _TWO_WORD else full_name.split()[-1]


TEAM_BY_ID = {i: abbrev for abbrev, (ids, _) in TEAMS.items() for i in ids}
TEAM_BY_NAME = {_plain(name).lower(): abbrev for abbrev, (_, name) in TEAMS.items()}
# Case-sensitive so "a wild finish" isn't the Minnesota Wild.
_TEAM_PATTERNS = {
    abbrev: re.compile(r"\b(" + re.escape(_plain(name)) + "|" + re.escape(_nickname(_plain(name))) + r")\b")
    for abbrev, (_, name) in TEAMS.items()
}


def teams_mentioned(text):
    plain = _plain(text or "")
    return sorted(abbrev for abbrev, pattern in _TEAM_PATTERNS.items() if pattern.search(plain))


def team_from_name(display_name):
    return TEAM_BY_NAME.get(_plain(display_name or "").lower())


# --- per-source cache ------------------------------------------------------

_cache: dict[str, tuple[float, object]] = {}  # source -> (fetched_at, value)
_locks: dict[str, threading.Lock] = {}
_lock = threading.Lock()


def _now():
    return time.monotonic()


def _cached(source, ttl, fetch):
    """The source's value: fresh from cache, refetched, or (if that fails) its last good copy."""
    with _lock:
        hit = _cache.get(source)
        if hit and _now() - hit[0] < ttl:
            return hit[1]
        source_lock = _locks.setdefault(source, threading.Lock())
    with source_lock:  # one upstream fetch per source at a time
        hit = _cache.get(source)
        if hit and _now() - hit[0] < ttl:
            return hit[1]
        try:
            value = fetch()
        except Exception as exc:  # network, HTTP, or a changed format
            if hit and _now() - hit[0] < MAX_STALE_SECONDS:
                logger.warning("%s unavailable (%s); serving the cached copy", source, type(exc).__name__)
                return hit[1]
            logger.warning("%s unavailable (%s)", source, type(exc).__name__)
            return None
        with _lock:
            _cache[source] = (_now(), value)
        return value


def clear_cache():
    with _lock:
        _cache.clear()


def _get(url):
    response = requests.get(url, headers=HEADERS, timeout=10)
    response.raise_for_status()
    return response


# --- headlines -------------------------------------------------------------

def _iso(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _unescape(text):
    """Feed text without HTML entities: some feeds double-encode them, so "isn't" arrives as "isn&#8217;t"."""
    return html.unescape(html.unescape(text or "")).strip()


def _clean_summary(text, limit=220):
    text = _unescape(re.sub(r"<[^>]+>", "", text or "")).replace("\xa0", " ").replace("\\+", "").strip()
    text = re.sub(r"\s+", " ", text)
    return text if len(text) <= limit else text[: limit - 1].rsplit(" ", 1)[0] + "…"


def parse_nhl_stories(data):
    out = []
    for item in data.get("items", []):
        slug, headline = item.get("slug"), item.get("headline") or item.get("title")
        if not slug or not headline or not item.get("contentDate"):
            continue
        ids = [int(t["slug"].split("-", 1)[1]) for t in item.get("tags", [])
               if str(t.get("slug", "")).startswith("teamid-") and t["slug"].split("-", 1)[1].isdigit()]
        out.append({
            "title": _unescape(headline), "url": f"https://www.nhl.com/news/{slug}", "source": "NHL.com",
            "published": item["contentDate"], "summary": _clean_summary(item.get("summary")),
            "teams": sorted({TEAM_BY_ID[i] for i in ids if i in TEAM_BY_ID}) or teams_mentioned(headline),
        })
    return out


def parse_rss(text, source, link_must_contain=None):
    out = []
    for item in ET.fromstring(text).iter("item"):
        title, link, published = _unescape(item.findtext("title")), (item.findtext("link") or "").strip(), item.findtext("pubDate")
        if not title or not link.startswith("https://") or not published:
            continue
        if link_must_contain and link_must_contain not in link:
            continue  # Sportsnet's feed mixes in collection and video pages
        try:
            when = email.utils.parsedate_to_datetime(published)
        except (TypeError, ValueError):
            continue
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        summary = _clean_summary(item.findtext("description"))
        out.append({"title": title, "url": link, "source": source, "published": _iso(when), "summary": summary,
                    "teams": teams_mentioned(title)})
    return out


ESPN_SKIP_TYPES = {"Media"}  # video clips


def parse_espn_news(data):
    out = []
    for article in data.get("articles", []):
        if article.get("premium") or article.get("type") in ESPN_SKIP_TYPES:
            continue  # ESPN+ paywalled stories and videos
        url = ((article.get("links") or {}).get("web") or {}).get("href") or ""
        title, published = _unescape(article.get("headline")), article.get("published")
        if not title or not url or not published:
            continue
        teams = sorted({t for c in article.get("categories", []) if c.get("type") == "team"
                        for t in [team_from_name(c.get("description"))] if t})
        out.append({"title": title, "url": url.replace("http://", "https://", 1), "source": "ESPN",
                    "published": published, "summary": _clean_summary(article.get("description")),
                    "teams": teams or teams_mentioned(title)})
    return out


def _nhl_headlines():
    return parse_nhl_stories(_get(NHL_STORIES_URL).json())


def _espn_headlines():
    return parse_espn_news(_get(ESPN_NEWS_URL).json())


def _sportsnet_headlines():
    return parse_rss(_get(SPORTSNET_RSS_URL).text, "Sportsnet", link_must_contain="/nhl/article/")


SOURCES = {"NHL.com": _nhl_headlines, "ESPN": _espn_headlines, "Sportsnet": _sportsnet_headlines}


SAME_STORY = 0.6  # word overlap (Jaccard) above which two headlines are one story


_FILLER = {"a", "an", "the", "of", "to", "in", "on", "at", "for", "and", "vs", "with", "as", "by"}


def _words(title):
    """Content words only: filler and scores ("5-3") make one story look like two."""
    words = re.sub(r"[^a-z0-9 ]", "", _plain(title).lower().replace("-", " ")).split()
    return {w for w in words if w not in _FILLER and not w.isdigit()}


def _safe_link(item):
    """Only https links reach the page (no javascript:, data:, or plain http)."""
    return str(item.get("url", "")).startswith("https://")


def merge_headlines(lists, now=None):
    """
    Newest first, last week only, and one copy of a story several outlets
    ran: game recaps are near-identical headlines ("Kraken overcome
    Ovechkin's first goal of season, edge Capitals" / "...to beat
    Capitals"), so headlines whose words overlap enough count as one.
    """
    now = now or datetime.now(timezone.utc)
    kept, out = [], []
    items = sorted((i for items in lists for i in items or [] if _safe_link(i)), key=lambda i: i["published"], reverse=True)
    for item in items:
        published = datetime.fromisoformat(item["published"].replace("Z", "+00:00"))
        if now - published > MAX_HEADLINE_AGE:
            continue
        words = _words(item["title"])
        if any(len(words & k) / len(words | k) >= SAME_STORY for k in kept if words | k):
            continue
        kept.append(words)
        out.append(item)
    return out[:MAX_HEADLINES]


def headlines(team=None, limit=20):
    with ThreadPoolExecutor(max_workers=len(SOURCES)) as pool:
        futures = {name: pool.submit(_cached, f"headlines:{name}", NEWS_TTL, fetch) for name, fetch in SOURCES.items()}
        results = {name: f.result() for name, f in futures.items()}
    items = merge_headlines(results.values())
    if team:
        items = [i for i in items if team in i["teams"]]
    return {"headlines": items[:limit], "sources": sorted(n for n, r in results.items() if r is not None)}


# --- injuries and transactions --------------------------------------------

def _note(text):
    """ESPN's short comment, unless it's an internal code like "ir-nr"."""
    text = (text or "").strip()
    return text if len(text) >= 15 and " " in text else None


def parse_injuries(data):
    """{team: [injury]}, worst status first."""
    order = {"injured reserve": 0, "out": 1, "day-to-day": 2}
    out = {}
    for team in data.get("injuries", []):
        abbrev = team_from_name(team.get("displayName"))
        if not abbrev:
            continue
        rows = []
        for injury in team.get("injuries", []):
            athlete, details = injury.get("athlete") or {}, injury.get("details") or {}
            rows.append({
                "player": athlete.get("displayName"),
                "position": (athlete.get("position") or {}).get("abbreviation"),
                "status": injury.get("status"),
                "injury": details.get("type"),
                "expected_return": details.get("returnDate"),
                "note": _note(injury.get("shortComment")),
                "updated": injury.get("date"),
            })
        rows.sort(key=lambda r: (order.get((r["status"] or "").lower(), 3), r["player"] or ""))
        out[abbrev] = rows
    return out


def parse_transactions(data):
    out = []
    for tx in data.get("transactions", []):
        abbrev = team_from_name((tx.get("team") or {}).get("displayName"))
        if abbrev and tx.get("description"):
            out.append({"date": (tx.get("date") or "")[:10], "team": abbrev, "description": tx["description"]})
    return out


def injuries(team=None):
    by_team = _cached("injuries", INJURIES_TTL, lambda: parse_injuries(_get(ESPN_INJURIES_URL).json()))
    if by_team is None:
        return None
    return {"source": "ESPN", "teams": {team: by_team.get(team, [])} if team else by_team}


def transactions(team=None, limit=25):
    rows = _cached("transactions", TRANSACTIONS_TTL, lambda: parse_transactions(_get(ESPN_TRANSACTIONS_URL).json()))
    if rows is None:
        return None
    if team:
        rows = [r for r in rows if r["team"] == team]
    return {"source": "ESPN", "transactions": rows[:limit]}
