"""
The morning post draft: finds last night's best stories (code), and asks
NHL Intelligence's drafting agent (POST /posts/draft) to pick one and write
an X post and a Reddit title for the creator to approve in the post kit.
Nothing is posted automatically.

Stories, each tied to a page and card the site already has:
- Swing of the Night: /s/{date}, its card.
- The biggest upset against the model's pregame odds (winner under 40%):
  /g/{game_id}, the game's card (final score and win probability curve).
- The biggest playoff-odds moves (5+ points since the day before): /t/{team}.

Runs on the notifier function in the morning, after Swing of the Night is
saved and before the creator's reminder.
"""

import json
import logging
import os
from datetime import datetime, timedelta

import psycopg2
import psycopg2.extras
import requests
from dotenv import load_dotenv

from logging_config import setup_logging

load_dotenv()
logger = setup_logging("post_drafts")

DATABASE_URL = os.getenv("DATABASE_URL")
INTELLIGENCE_URL = (os.getenv("INTELLIGENCE_URL") or "").rstrip("/")
DIGEST_TOKEN = os.getenv("DIGEST_TOKEN", "")  # the scheduled jobs' token for NHL Intelligence
API_URL = "https://nhl-dashboard-api.bravecoast-a5240643.westus2.azurecontainerapps.io"
SITE = "https://puckpulse.io"
UPSET_BELOW = 0.40  # the winner's pregame chance
MOVE_AT_LEAST = 0.05  # playoff odds, as a fraction
MAX_MOVERS = 2

TABLE_SQL = """
CREATE TABLE IF NOT EXISTS post_drafts (
    day           DATE PRIMARY KEY,      -- the night the story is about
    story         VARCHAR(40) NOT NULL,  -- the candidate the agent picked, e.g. upset-2026020197
    link          TEXT NOT NULL,
    image         TEXT,
    x_text        TEXT NOT NULL,
    reddit_title  TEXT NOT NULL,
    model         VARCHAR(80),
    candidates    JSONB NOT NULL,        -- every story it chose from, for review
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
GRANT SELECT ON post_drafts TO nhl_api_readonly;
CREATE TABLE IF NOT EXISTS post_actions (
    id          SERIAL PRIMARY KEY,
    day         DATE NOT NULL,
    action      VARCHAR(20) NOT NULL,  -- posted_x, copied_x, posted_reddit, copied_reddit
    text        TEXT NOT NULL,         -- the X text as edited, or the Reddit title
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS post_actions_day ON post_actions (day);
GRANT INSERT ON post_actions TO nhl_api_readonly;
GRANT USAGE ON SEQUENCE post_actions_id_seq TO nhl_api_readonly
"""
HISTORY_DAYS = 14


def pct(p) -> int:
    return round(float(p) * 100)


def _final(away, away_score, home, home_score, ended) -> dict:
    """The result as the drafts should say it: "FLA won 3-2 (OT)", winner's score first."""
    winner, loser = (away, home) if away_score > home_score else (home, away)
    high, low = max(away_score, home_score), min(away_score, home_score)
    extra = f" ({ended})" if ended in ("OT", "SO") else ""
    return {"winner": winner, "loser": loser, "score": f"{high}-{low}{extra}"}


def swing_story(cur, day) -> dict | None:
    cur.execute("SELECT payload FROM swing_of_the_night WHERE day = %s", (day,))
    row = cur.fetchone()
    if not row or not (row["payload"] or {}).get("goal"):
        return None
    s = row["payload"]
    g, game = s["goal"], s["game"]
    return {
        "id": "swing",
        "kind": "Swing of the Night: the goal that moved PuckPulse's live win probability the most",
        "link": f"{SITE}/s/{day.isoformat()}",
        "image": f"{API_URL}/og/swing/{day.isoformat()}.png",
        "facts": {
            "game": f"{game['away']} @ {game['home']}",
            "result": _final(game["away"], game["away_score"], game["home"], game["home_score"], game.get("last_period")),
            "scorer": g.get("scorer"), "team": g["team"], "what_it_did": g["effect"], "when": g["when"],
            "team_win_chance_before_pct": pct(g["before"]), "team_win_chance_after_pct": pct(g["after"]),
            "games_that_night": s.get("games"),
        },
    }


def upset_story(cur, day) -> dict | None:
    cur.execute(
        """
        SELECT game_id, away_abbrev, home_abbrev, home_win_prob, away_score, home_score, ended, home_won
        FROM game_predictions WHERE game_date = %s AND graded_at IS NOT NULL AND home_won IS NOT NULL
        """,
        (day,),
    )
    best = None
    for g in cur.fetchall():
        chance = float(g["home_win_prob"]) if g["home_won"] else 1 - float(g["home_win_prob"])
        if chance < UPSET_BELOW and (best is None or chance < best[0]):
            best = (chance, g)
    if not best:
        return None
    chance, g = best
    return {
        "id": f"upset-{g['game_id']}",
        "kind": "Upset: the night's least likely winner by PuckPulse's pregame odds",
        "link": f"{SITE}/g/{g['game_id']}",
        "image": f"{API_URL}/og/game/{g['game_id']}.png",
        "facts": {
            "game": f"{g['away_abbrev']} @ {g['home_abbrev']}", "game_id": g["game_id"],
            "result": _final(g["away_abbrev"], g["away_score"], g["home_abbrev"], g["home_score"], g["ended"]),
            "winner_pregame_win_chance_pct": pct(chance),
        },
    }


def mover_stories(cur, day) -> list[dict]:
    """The biggest playoff-odds moves from the morning after `day` versus the morning before."""
    cur.execute(
        """
        SELECT a.team_abbrev, b.playoff_pct AS before, a.playoff_pct AS after
        FROM playoff_odds a
        JOIN playoff_odds b ON b.team_abbrev = a.team_abbrev AND b.season_id = a.season_id AND b.as_of_date = %s
        WHERE a.as_of_date = %s
        ORDER BY ABS(a.playoff_pct - b.playoff_pct) DESC
        LIMIT %s
        """,
        (day, day + timedelta(days=1), MAX_MOVERS),
    )
    out = []
    for r in cur.fetchall():
        before, after = float(r["before"]), float(r["after"])
        if abs(after - before) < MOVE_AT_LEAST:
            continue
        out.append({
            "id": f"odds-{r['team_abbrev']}",
            "kind": "Playoff odds move: one of the night's biggest changes in PuckPulse's playoff odds",
            "link": f"{SITE}/t/{r['team_abbrev']}",
            "image": None,
            "facts": {"team": r["team_abbrev"], "playoff_odds_before_pct": pct(before), "playoff_odds_after_pct": pct(after)},
        })
    return out


def _label(kind: str) -> str:
    return kind.split(":")[0]  # "Swing of the Night", "Upset", "Playoff odds move"


def history(cur, day) -> list[dict]:
    """
    The owner's last HISTORY_DAYS of drafted posts, oldest first: the kind
    of story drafted (and the kinds passed over), the draft, and what they
    did with it in the post kit (post_actions): posted as drafted, edited
    (with their text), or skipped. Copying the text counts as posting it.
    Starts at the first day anything was recorded: drafts from before the
    post kit recorded anything would all read as skipped.
    """
    cur.execute("SELECT MIN(day) AS first FROM post_actions")
    first = (cur.fetchall() or [{}])[0].get("first")
    if not first:
        return []
    cur.execute(
        "SELECT day, story, x_text, candidates FROM post_drafts WHERE day >= %s AND day < %s ORDER BY day",
        (max(first, day - timedelta(days=HISTORY_DAYS)), day),
    )
    drafts = cur.fetchall()
    cur.execute(
        """
        SELECT DISTINCT ON (day) day, text FROM post_actions
        WHERE day >= %s AND day < %s AND action IN ('posted_x', 'copied_x')
        ORDER BY day, created_at DESC
        """,
        (day - timedelta(days=HISTORY_DAYS), day),
    )
    posted = {r["day"]: r["text"] for r in cur.fetchall()}
    out = []
    for d in drafts:
        kinds = {c["id"]: _label(c["kind"]) for c in d["candidates"]}
        text = posted.get(d["day"])
        outcome = "skipped" if text is None else "as drafted" if " ".join(text.split()) == " ".join(d["x_text"].split()) else "edited"
        out.append({
            "day": d["day"].isoformat(), "story": kinds.get(d["story"], d["story"]),
            "passed_over": sorted({k for i, k in kinds.items() if i != d["story"]}),
            "draft": d["x_text"], "outcome": outcome, **({"posted": text} if outcome == "edited" else {}),
        })
    return out


def candidates(cur, day) -> list[dict]:
    return [s for s in (swing_story(cur, day), upset_story(cur, day)) if s] + mover_stories(cur, day)


def draft(day, stories: list[dict], post=requests.post, past: list[dict] = ()) -> dict | None:
    """The agent's pick and text ({pick, x_text, reddit_title, model, ...}), or None."""
    if not (INTELLIGENCE_URL and DIGEST_TOKEN):
        logger.warning("INTELLIGENCE_URL/DIGEST_TOKEN not set; no draft")
        return None
    body = {"date": day.isoformat(), "candidates": [{k: s[k] for k in ("id", "kind", "facts")} for s in stories],
            "history": list(past)}
    try:
        response = post(f"{INTELLIGENCE_URL}/posts/draft", json=body, headers={"X-Digest-Token": DIGEST_TOKEN},
                        timeout=120)
        response.raise_for_status()
        result = response.json()
    except (requests.RequestException, ValueError) as exc:
        logger.warning(f"Couldn't get a post drafted ({exc})")
        return None
    if not result.get("pick"):
        logger.info(f"No draft passed the checks ({'; '.join(result.get('problems') or [])})")
        return None
    return result


def save(cur, day, story: dict, result: dict, stories: list[dict]) -> None:
    cur.execute(
        """
        INSERT INTO post_drafts (day, story, link, image, x_text, reddit_title, model, candidates, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
        ON CONFLICT (day) DO UPDATE SET story = EXCLUDED.story, link = EXCLUDED.link, image = EXCLUDED.image,
            x_text = EXCLUDED.x_text, reddit_title = EXCLUDED.reddit_title, model = EXCLUDED.model,
            candidates = EXCLUDED.candidates, created_at = NOW()
        """,
        (day, story["id"], story["link"], story["image"], result["x_text"], result["reddit_title"], result.get("model"),
         json.dumps(stories)),
    )


def run(conn, day, post=requests.post) -> str | None:
    """Draft the post about `day`'s games. Returns the story picked, or None."""
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(TABLE_SQL)
        stories = candidates(cur, day)
        past = history(cur, day)
    conn.commit()
    if not stories:
        logger.info(f"No stories for {day}")
        return None
    result = draft(day, stories, post, past)
    story = next((s for s in stories if result and s["id"] == result["pick"]), None)
    if not story:
        return None
    with conn.cursor() as cur:
        save(cur, day, story, result, stories)
    conn.commit()
    return story["id"]


def main(now=None):
    if not DATABASE_URL:
        raise SystemExit("DATABASE_URL is not set")
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    from zoneinfo import ZoneInfo
    day = (now or datetime.now(ZoneInfo("America/New_York"))).date() - timedelta(days=1)
    with psycopg2.connect(DATABASE_URL) as conn:
        picked = run(conn, day)
    logger.info(f"Post draft for {day}: {picked or 'none'}")


if __name__ == "__main__":
    main()
