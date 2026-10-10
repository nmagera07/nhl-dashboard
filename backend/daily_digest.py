"""
The morning digest: last night's results and standouts, the biggest
playoff-odds moves, and tonight's games with the model's win
probabilities -- gathered here as facts, written up by NHL Intelligence
(the only service holding AI keys), and stored for the Scores page.

Runs in the daily job right after the playoff-odds simulation (it reads
today's odds and the model's ratings). One AI call a day, shared by every
visitor. If the AI is unavailable, the facts are stored anyway and the page
shows them as a plain list.
"""

import json
import logging
import os
from collections import defaultdict
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import psycopg2
import requests
from dotenv import load_dotenv

import nhl_games
import simulate_playoff_odds as sim
from logging_config import setup_logging

load_dotenv()
logger = setup_logging("daily_digest")

DATABASE_URL = os.getenv("DATABASE_URL")
INTELLIGENCE_URL = (os.getenv("INTELLIGENCE_URL") or "").rstrip("/")
DIGEST_TOKEN = os.getenv("DIGEST_TOKEN", "")
EASTERN = ZoneInfo("America/New_York")
FINAL_STATES = {"FINAL", "OFF"}
MIN_ODDS_MOVE = 2.0  # percentage points; smaller daily moves are noise


def today_eastern(now: datetime | None = None) -> date:
    return (now or datetime.now(EASTERN)).astimezone(EASTERN).date()


def _name(team: dict) -> str:
    return (team.get("name") or {}).get("default") or team.get("abbrev")


def results(games: list[dict]) -> list[dict]:
    """Final scores, with OT/SO when it went past regulation."""
    out = []
    for g in games:
        if g.get("gameState") not in FINAL_STATES:
            continue
        ended = (g.get("gameOutcome") or {}).get("lastPeriodType")
        out.append({
            "away": g["awayTeam"]["abbrev"], "away_score": g["awayTeam"].get("score"),
            "home": g["homeTeam"]["abbrev"], "home_score": g["homeTeam"].get("score"),
            **({"ended": ended} if ended in ("OT", "SO") else {}),
        })
    return out


def standouts(games: list[dict], limit: int = 5) -> list[dict]:
    """Multi-goal and 3+ point nights, from the scoring summaries (shootout goals don't count)."""
    tally = defaultdict(lambda: {"goals": 0, "assists": 0})
    for g in games:
        if g.get("gameState") not in FINAL_STATES:
            continue
        for goal in g.get("goals", []):
            if (goal.get("periodDescriptor") or {}).get("periodType") == "SO":
                continue
            scorer = ((goal.get("name") or {}).get("default"), goal.get("teamAbbrev"))
            tally[scorer]["goals"] += 1
            for a in goal.get("assists", []):
                tally[((a.get("name") or {}).get("default"), goal.get("teamAbbrev"))]["assists"] += 1
    rows = [
        {"player": name, "team": team, "goals": t["goals"], "assists": t["assists"], "points": t["goals"] + t["assists"]}
        for (name, team), t in tally.items()
        if name and (t["goals"] >= 2 or t["goals"] + t["assists"] >= 3)
    ]
    rows.sort(key=lambda r: (-r["goals"] * 2 - r["assists"], r["player"]))
    return rows[:limit]


def odds_movers(history: list[tuple], limit: int = 3) -> dict:
    """
    Biggest playoff-odds changes between the two latest simulations.
    history: (as_of_date, team, playoff_pct) rows for the season.
    """
    dates = sorted({d for d, _, _ in history})
    if len(dates) < 2:
        return {}
    before = {t: float(p) for d, t, p in history if d == dates[-2]}
    after = {t: float(p) for d, t, p in history if d == dates[-1]}
    moves = [
        {"team": t, "from_pct": round(before[t] * 100, 1), "to_pct": round(after[t] * 100, 1),
         "change": round((after[t] - before[t]) * 100, 1)}
        for t in after if t in before and abs(after[t] - before[t]) * 100 >= MIN_ODDS_MOVE
    ]
    up = sorted((m for m in moves if m["change"] > 0), key=lambda m: -m["change"])[:limit]
    down = sorted((m for m in moves if m["change"] < 0), key=lambda m: m["change"])[:limit]
    return {k: v for k, v in (("rising", up), ("falling", down)) if v}


def tonight(games: list[dict], ratings: dict, model: dict) -> list[dict]:
    """Tonight's games with the model's home-win probability (same game model as the odds)."""
    out = []
    for g in games:
        if g.get("gameState") in FINAL_STATES:
            continue
        home, away = g["homeTeam"]["abbrev"], g["awayTeam"]["abbrev"]
        start = datetime.fromisoformat(g["startTimeUTC"].replace("Z", "+00:00")).astimezone(EASTERN)
        row = {"away": away, "home": home, "time": start.strftime("%-I:%M %p ET")}
        if home in ratings and away in ratings:
            x = (ratings[home] - ratings[away] + model["home_edge"]) / model["scale"]
            row["model_home_win_pct"] = round(100 / (1 + 2.718281828459045 ** -x))
        out.append(row)
    return out


def game_of_the_night(games_tonight: list[dict]) -> dict | None:
    """The closest matchup by the model's odds (nearest to 50/50)."""
    rated = [g for g in games_tonight if "model_home_win_pct" in g]
    return min(rated, key=lambda g: abs(g["model_home_win_pct"] - 50)) if rated else None


def add_lines(finals: list[dict], movers: dict, featured: dict | None, names: dict):
    """
    Ready-to-use sentences ("Blue Jackets 3, Penguins 2 (SO)") next to the
    raw fields, so the model rephrases instead of translating abbreviations:
    Groq's model turned CBJ into "Buffalo Sabres" when left to map them.
    """
    name = lambda abbrev: names.get(abbrev, abbrev)  # noqa: E731
    for g in finals:
        (w, ws), (l, ls) = sorted([(g["away"], g["away_score"]), (g["home"], g["home_score"])], key=lambda t: -t[1])
        g["line"] = f"{name(w)} {ws}, {name(l)} {ls}" + (f" ({g['ended']})" if g.get("ended") else "")
    for m in movers.get("rising", []) + movers.get("falling", []):
        m["line"] = f"{name(m['team'])}: {m['from_pct']:.0f}% to {m['to_pct']:.0f}%"
    if featured:
        pct = featured.get("model_home_win_pct")
        featured["line"] = (f"{name(featured['away'])} at {name(featured['home'])}, {featured['time']}"
                            + (f"; the model gives the {name(featured['home'])} {pct}%" if pct is not None else ""))


def build_facts(day: date, cur) -> dict | None:
    last_night = nhl_games.games_on_date(day - timedelta(days=1))
    today = nhl_games.games_on_date(day)

    cur.execute("SELECT payload FROM season_sim_inputs ORDER BY season_id DESC LIMIT 1")
    row = cur.fetchone()
    payload = row[0] if row else None
    ratings = {t: v["rating"] for t, v in (payload or {}).get("teams", {}).items()}
    model = (payload or {}).get("model") or {"home_edge": sim.HOME_EDGE, "scale": sim.SCALE}

    cur.execute(
        "SELECT as_of_date, team_abbrev, playoff_pct FROM playoff_odds "
        "WHERE season_id = (SELECT MAX(season_id) FROM playoff_odds) "
        "AND as_of_date IN (SELECT DISTINCT as_of_date FROM playoff_odds "
        "  WHERE season_id = (SELECT MAX(season_id) FROM playoff_odds) ORDER BY as_of_date DESC LIMIT 2)"
    )
    history = cur.fetchall()

    cur.execute("SELECT ROUND(AVG(games_played)) FROM standings_snapshots "
                "WHERE snapshot_date = (SELECT MAX(snapshot_date) FROM standings_snapshots)")
    avg_gp = (cur.fetchone() or [None])[0]

    games_tonight = tonight(today, ratings, model)
    finals = results(last_night)
    if not finals and not games_tonight:
        return None
    teams = {g[side]["abbrev"]: _name(g[side]) for g in last_night + today for side in ("awayTeam", "homeTeam")}
    add_lines(finals, odds_movers_ := odds_movers(history), game_of_the_night(games_tonight), teams)
    facts = {
        "date": day.strftime("%A, %B %-d"),
        "last_night_date": (day - timedelta(days=1)).strftime("%A, %B %-d"),
        # Without this a model called October "a late-season surge".
        "season_progress": f"teams have played about {int(avg_gp)} of {84 if day.year >= 2026 else 82} games" if avg_gp else None,
        "last_night": finals,
        "standouts": standouts(last_night),
        "playoff_odds_moves": odds_movers_,
        "tonight": games_tonight,
        "game_of_the_night": game_of_the_night(games_tonight),
        "team_names": teams,
        "notes": "Scores are away-home. Win probabilities and playoff odds are the app's model.",
    }
    return {k: v for k, v in facts.items() if v not in (None, [], {})}


def write(facts: dict) -> tuple[str | None, str | None]:
    """Ask NHL Intelligence to write the digest. (None, None) if it can't."""
    if not (INTELLIGENCE_URL and DIGEST_TOKEN):
        logger.warning("INTELLIGENCE_URL/DIGEST_TOKEN not set; storing facts only")
        return None, None
    try:
        # Generous timeout: the service scales to zero and may need to wake up.
        response = requests.post(f"{INTELLIGENCE_URL}/digest/write", json={"facts": facts},
                                 headers={"X-Digest-Token": DIGEST_TOKEN}, timeout=120)
        response.raise_for_status()
        body = response.json()
        return body.get("text"), body.get("model")
    except (requests.RequestException, ValueError) as exc:
        logger.warning(f"Couldn't get the digest written ({exc}); storing facts only")
        return None, None


def save(cur, day: date, facts: dict, text: str | None, model: str | None):
    cur.execute(
        """
        INSERT INTO daily_digest (digest_date, facts, text, model, created_at)
        VALUES (%s, %s, %s, %s, NOW())
        ON CONFLICT (digest_date) DO UPDATE SET
            facts = EXCLUDED.facts, text = EXCLUDED.text, model = EXCLUDED.model, created_at = NOW()
        """,
        (day, json.dumps(facts), text, model),
    )


def main():
    if not DATABASE_URL:
        raise SystemExit("DATABASE_URL is not set")
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    day = today_eastern()
    with psycopg2.connect(DATABASE_URL) as conn, conn.cursor() as cur:
        facts = build_facts(day, cur)
        if facts is None:
            logger.info(f"No games last night or tonight ({day}); no digest")
            return
        text, model = write(facts)
        save(cur, day, facts, text, model)
    logger.info(f"Digest for {day}: {len(facts.get('last_night', []))} results, "
                f"{len(facts.get('tonight', []))} games tonight, written by {model or 'nobody (facts only)'}")


if __name__ == "__main__":
    main()
