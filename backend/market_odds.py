"""
Market odds for each game, logged next to our own prediction so both can
be graded on the same games, from two sources:

  - sportsbooks: the consensus of US books (DraftKings, FanDuel, BetMGM...)
    from The Odds API (the-odds-api.com, free tier: one call covers every
    game; needs ODDS_API_KEY). Each book's moneyline has its margin removed
    (the two implied probabilities normalized to 1), then the median across
    books. Shown to users in the game preview's "Market view".
  - kalshi: the prediction market (below). Logged and graded only; not
    shown until its terms for displaying prices are confirmed.

Source: Kalshi's public market data (no account needed to read). Each NHL
game is an event (KXNHLGAME-26OCT14DALCOL: date, away, home) with one market
per team ("Colorado wins"), priced in dollars. The implied probability is
the midpoint of each side's bid and ask, normalized so the two add to 1.

Timing: the daily job logs a "morning" snapshot right after our 2 AM
predictions, so both see the same information. (The tougher benchmark is
the closing line at puck drop; that would be a second snapshot.)

Usage:
    python market_odds.py              # log today's games (the daily job)
    python market_odds.py --report     # our predictions vs. the market, graded
"""

import argparse
import os
import re
import statistics
import time
import unicodedata
from datetime import date, datetime
from zoneinfo import ZoneInfo

import psycopg2
import requests
from dotenv import load_dotenv

from daily_digest import today_eastern
from logging_config import setup_logging

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
logger = setup_logging("market_odds")

KALSHI_MARKETS_URL = "https://api.elections.kalshi.com/trade-api/v2/markets?event_ticker={event}"
NHL_SCORE_URL = "https://api-web.nhle.com/v1/score/{date}"
NOT_STARTED = {"FUT", "PRE"}
HEADERS = {"User-Agent": "nhl-dashboard (personal project)"}
SOURCE = "kalshi"
ODDS_API_URL = "https://api.the-odds-api.com/v4/sports/icehockey_nhl/odds"
ODDS_API_KEY = os.getenv("ODDS_API_KEY")
SPORTSBOOKS = "sportsbooks"
EASTERN = ZoneInfo("America/New_York")
# Kalshi's team codes differ from the NHL's for four teams.
KALSHI_CODES = {"LAK": "LA", "NJD": "NJ", "SJS": "SJ", "TBL": "TB"}
MONTHS = ("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC")

TABLE_SQL = """
CREATE TABLE IF NOT EXISTS market_odds (
    game_id                 BIGINT NOT NULL,
    source                  VARCHAR(16) NOT NULL,
    captured                VARCHAR(10) NOT NULL,     -- 'morning' (with our 2 AM prediction)
    game_date               DATE NOT NULL,
    home_abbrev             VARCHAR(3) NOT NULL,
    away_abbrev             VARCHAR(3) NOT NULL,
    home_prob               NUMERIC(5,4) NOT NULL,    -- implied, mid prices normalized
    home_bid                NUMERIC(5,4),
    home_ask                NUMERIC(5,4),
    away_bid                NUMERIC(5,4),
    away_ask                NUMERIC(5,4),
    volume                  NUMERIC(14,2),            -- contracts traded, both sides
    captured_at             TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (game_id, source, captured)
)
"""
# Sportsbook consensus: the median line and how many books it's from.
COLUMNS_SQL = """
ALTER TABLE market_odds ADD COLUMN IF NOT EXISTS home_line INTEGER;
ALTER TABLE market_odds ADD COLUMN IF NOT EXISTS away_line INTEGER;
ALTER TABLE market_odds ADD COLUMN IF NOT EXISTS books SMALLINT;
"""


def american_to_prob(price):
    """-150 -> 0.6, +130 -> 0.4348 (the book's implied probability, margin included)."""
    price = float(price)
    return -price / (-price + 100) if price < 0 else 100 / (price + 100)


def _norm(name):
    """'St Louis Blues' and 'St. Louis Blues', 'Montréal' and 'Montreal' compare equal."""
    plain = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z]", "", plain.lower())


def sportsbook_consensus(event, home_name, away_name):
    """
    {"home_prob", "home_line", "away_line", "books"} for one Odds API event:
    each book's two moneylines turned into probabilities with the margin
    removed, then the median across books (and the median lines, for
    showing). None if no book has both sides.
    """
    probs, home_lines, away_lines = [], [], []
    for book in event.get("bookmakers", []):
        h2h = next((m for m in book.get("markets", []) if m.get("key") == "h2h"), None)
        prices = {_norm(o["name"]): o["price"] for o in (h2h or {}).get("outcomes", [])}
        h, a = prices.get(_norm(home_name)), prices.get(_norm(away_name))
        if h is None or a is None:
            continue
        ph, pa = american_to_prob(h), american_to_prob(a)
        probs.append(ph / (ph + pa))
        home_lines.append(h)
        away_lines.append(a)
    if not probs:
        return None
    return {"home_prob": round(statistics.median(probs), 4), "home_line": round(statistics.median(home_lines)),
            "away_line": round(statistics.median(away_lines)), "books": len(probs)}


def log_sportsbooks(cur, day, games, names, get=None):
    """
    games: [(game_id, home, away)]; names: {abbrev: full team name}. One Odds
    API call covers every upcoming game; only today's (Eastern) are logged.
    """
    if not ODDS_API_KEY and get is None:
        logger.info("No ODDS_API_KEY; skipping sportsbook odds")
        return 0
    cur.execute(TABLE_SQL)
    cur.execute(COLUMNS_SQL)
    try:
        events = (get or _get_odds_api)()
    except requests.RequestException as exc:
        logger.warning(f"The Odds API unavailable ({exc}); skipping sportsbook odds")
        return 0
    by_teams = {}
    for e in events:
        start = datetime.fromisoformat(e["commence_time"].replace("Z", "+00:00")).astimezone(EASTERN).date()
        if start == day:
            by_teams[(_norm(e["home_team"]), _norm(e["away_team"]))] = e
    logged = 0
    for game_id, home, away in games:
        event = by_teams.get((_norm(names.get(home, "")), _norm(names.get(away, ""))))
        odds = event and sportsbook_consensus(event, names[home], names[away])
        if not odds:
            continue
        cur.execute(
            """
            INSERT INTO market_odds (game_id, source, captured, game_date, home_abbrev, away_abbrev, home_prob,
                                     home_line, away_line, books, captured_at)
            VALUES (%s, %s, 'morning', %s, %s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (game_id, source, captured) DO NOTHING
            """,
            (game_id, SPORTSBOOKS, day, home, away, odds["home_prob"], odds["home_line"], odds["away_line"], odds["books"]),
        )
        logged += 1
    return logged


def _get_odds_api():
    response = requests.get(ODDS_API_URL, params={"apiKey": ODDS_API_KEY, "regions": "us", "markets": "h2h",
                                                  "oddsFormat": "american"}, timeout=30)
    response.raise_for_status()
    logger.info(f"The Odds API: {response.headers.get('x-requests-remaining')} requests left this month")
    return response.json()


def kalshi_code(abbrev):
    return KALSHI_CODES.get(abbrev, abbrev)


def event_ticker(day, away, home):
    """KXNHLGAME-26OCT14DALCOL for DAL @ COL on 2026-10-14."""
    return f"KXNHLGAME-{day.year % 100:02d}{MONTHS[day.month - 1]}{day.day:02d}{kalshi_code(away)}{kalshi_code(home)}"


def _price(market, field):
    value = market.get(f"{field}_dollars")
    return float(value) if value not in (None, "") else None


def implied_home_prob(markets, home, away):
    """
    {"home_prob", bids/asks, "volume"} from an event's two markets, or None
    when either side has no two-sided quote (no market yet, or too thin).
    """
    by_team = {m.get("ticker", "").rsplit("-", 1)[-1]: m for m in markets}
    h, a = by_team.get(kalshi_code(home)), by_team.get(kalshi_code(away))
    if not h or not a:
        return None
    quotes = {}
    for side, m in (("home", h), ("away", a)):
        bid, ask = _price(m, "yes_bid"), _price(m, "yes_ask")
        if not bid or not ask or ask < bid:
            return None
        quotes[side] = (bid, ask)
    home_mid = sum(quotes["home"]) / 2
    away_mid = sum(quotes["away"]) / 2
    volume = sum(float(m.get("volume_fp") or 0) for m in (h, a))
    return {"home_prob": round(home_mid / (home_mid + away_mid), 4),
            "home_bid": quotes["home"][0], "home_ask": quotes["home"][1],
            "away_bid": quotes["away"][0], "away_ask": quotes["away"][1], "volume": round(volume, 2)}


def _get(url):
    for attempt in range(4):
        response = requests.get(url, headers=HEADERS, timeout=30)
        if response.status_code != 429:
            response.raise_for_status()
            return response.json()
        time.sleep(5 * (attempt + 1))
    response.raise_for_status()


def log_games(cur, day, games, captured="morning", get=_get):
    """games: [(game_id, home, away)]. Logs each one Kalshi has a two-sided market for."""
    cur.execute(TABLE_SQL)
    cur.execute("GRANT SELECT ON market_odds TO nhl_api_readonly")
    logged = 0
    for game_id, home, away in games:
        try:
            markets = get(KALSHI_MARKETS_URL.format(event=event_ticker(day, away, home))).get("markets", [])
        except requests.RequestException as exc:
            logger.warning(f"{away} @ {home}: Kalshi unavailable ({exc}); skipping")
            continue
        odds = implied_home_prob(markets, home, away)
        if odds is None:
            logger.info(f"{away} @ {home}: no two-sided Kalshi market yet")
            continue
        cur.execute(
            """
            INSERT INTO market_odds (game_id, source, captured, game_date, home_abbrev, away_abbrev, home_prob,
                                     home_bid, home_ask, away_bid, away_ask, volume, captured_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (game_id, source, captured) DO NOTHING
            """,
            (game_id, SOURCE, captured, day, home, away, odds["home_prob"], odds["home_bid"], odds["home_ask"],
             odds["away_bid"], odds["away_ask"], odds["volume"]),
        )
        logged += 1
        time.sleep(0.2)
    return logged


def not_started(day, get=_get):
    """IDs of today's games that haven't started. Once a game is live the
    market prices the score, so a late run (the job's retry) must skip it."""
    return {g["id"] for g in get(NHL_SCORE_URL.format(date=day)).get("games", []) if g.get("gameState") in NOT_STARTED}


def log_today():
    """
    Today's games from the prediction log (written moments earlier by
    game_predictions.py), only those not started yet. A Kalshi outage skips
    the day; it only costs one day of comparison.
    """
    day = today_eastern()
    with psycopg2.connect(DATABASE_URL) as conn, conn.cursor() as cur:
        cur.execute("SELECT game_id, home_abbrev, away_abbrev FROM game_predictions WHERE game_date = %s", (day,))
        pending = not_started(day)
        games = [g for g in cur.fetchall() if g[0] in pending]
        logged = log_games(cur, day, games)
        cur.execute("SELECT team_abbrev, team_name FROM teams")
        books = log_sportsbooks(cur, day, games, dict(cur.fetchall()))
    logger.info(f"Logged Kalshi odds for {logged} and sportsbook odds for {books} of {len(games)} games on {day}")


def brier(pairs):
    return sum((p - y) ** 2 for p, y in pairs) / len(pairs)


def compare(rows):
    """
    rows: [(our home prob, market home prob, home_won)] on graded games.
    Brier for both, and how the disagreements went.
    """
    if not rows:
        return {"games": 0}
    ours = [(o, y) for o, _, y in rows]
    market = [(m, y) for _, m, y in rows]
    picked_differently = [(o, m, y) for o, m, y in rows if (o > 0.5) != (m > 0.5)]
    return {
        "games": len(rows),
        "brier_ours": round(brier(ours), 4),
        "brier_market": round(brier(market), 4),
        "mean_abs_gap": round(sum(abs(o - m) for o, m, _ in rows) / len(rows), 4),
        "picked_different_winner": len(picked_differently),
        "we_were_right_when_we_differed": sum((o > 0.5) == bool(y) for o, _, y in picked_differently),
    }


def report():
    """Our predictions vs. each market, graded on the same finished games."""
    with psycopg2.connect(DATABASE_URL) as conn, conn.cursor() as cur:
        for source in (SPORTSBOOKS, SOURCE):
            cur.execute(
                """
                SELECT p.game_date, p.away_abbrev, p.home_abbrev, p.home_win_prob, m.home_prob, p.home_won
                FROM game_predictions p
                JOIN market_odds m ON m.game_id = p.game_id AND m.source = %s AND m.captured = 'morning'
                WHERE p.home_won IS NOT NULL
                ORDER BY p.game_date
                """,
                (source,),
            )
            rows = cur.fetchall()
            print(f"\nPuckPulse vs {source}:", compare([(float(o), float(m), bool(y)) for *_, o, m, y in rows]))
            for day, away, home, o, m, won in sorted(rows, key=lambda r: -abs(float(r[3]) - float(r[4])))[:5]:
                print(f"  {day} {away} @ {home}: ours {float(o):.0%}, {source} {float(m):.0%}, home {'won' if won else 'lost'}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", action="store_true")
    args = parser.parse_args()
    if not DATABASE_URL:
        raise SystemExit("DATABASE_URL is not set")
    report() if args.report else log_today()


if __name__ == "__main__":
    main()
