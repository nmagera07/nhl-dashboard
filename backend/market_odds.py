"""
Market odds for each game, logged next to our own prediction so both can
be graded on the same games, from two sources:

  - sportsbooks: the consensus of US books (DraftKings, FanDuel, BetMGM...)
    from The Odds API (the-odds-api.com; needs ODDS_API_KEY). One call
    covers every game's moneyline, puck line, and total (3 of the free
    tier's 500 credits a month). Each book's two prices have its margin
    removed (the implied probabilities normalized to 1), then the median
    across books; for the puck line and total, at the line most books
    offer. Also the best moneyline price on each side, for line shopping.
    Shown to users in the game preview's "Market view".
  - kalshi: the prediction market (below). Logged and graded only; not
    shown until its terms for displaying prices are confirmed.

Source: Kalshi's public market data (no account needed to read). Each NHL
game is an event (KXNHLGAME-26OCT14DALCOL: date, away, home) with one market
per team ("Colorado wins"), priced in dollars. The implied probability is
the midpoint of each side's bid and ask, normalized so the two add to 1.

Timing, two snapshots per game:
  - "morning": the daily job, right after our 2 AM predictions, so both
    see the same information.
  - "close": the notifier function checks every 5 minutes; once a game is
    within 15 minutes of puck drop, one call snapshots every game starting
    in the next 75 minutes (a few calls a day, not one per game). The
    closing line has the most information in it (confirmed goalies, late
    injuries), so it's the hardest benchmark: beating it is the real test.

Usage:
    python market_odds.py              # log today's games (the daily job)
    python market_odds.py --close      # closing snapshot if one is due (the function)
    python market_odds.py --report     # our predictions vs. the market, graded
"""

import argparse
import os
import re
import statistics
import time
import unicodedata
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import psycopg2
import requests
from dotenv import load_dotenv

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
CLOSE_LEAD = timedelta(minutes=15)   # a game this close to puck drop triggers the closing snapshot
CLOSE_COVER = timedelta(minutes=75)  # which covers every game starting this soon
CREDIT_FLOOR = 30                    # leave the last Odds API credits for the morning snapshots
MONTHS = ("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC")

TABLE_SQL = """
CREATE TABLE IF NOT EXISTS market_odds (
    game_id                 BIGINT NOT NULL,
    source                  VARCHAR(16) NOT NULL,
    captured                VARCHAR(10) NOT NULL,     -- 'morning' (with our 2 AM prediction) or 'close' (near puck drop)
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
# Sportsbook consensus: the median line and how many books it's from;
# the puck line (home_spread -1.5 = home favored by 1.5) and total, each
# with its median prices and no-margin probability; the best moneylines.
COLUMNS_SQL = """
ALTER TABLE market_odds ADD COLUMN IF NOT EXISTS home_line INTEGER;
ALTER TABLE market_odds ADD COLUMN IF NOT EXISTS away_line INTEGER;
ALTER TABLE market_odds ADD COLUMN IF NOT EXISTS books SMALLINT;
ALTER TABLE market_odds ADD COLUMN IF NOT EXISTS best_home_line INTEGER;
ALTER TABLE market_odds ADD COLUMN IF NOT EXISTS best_away_line INTEGER;
ALTER TABLE market_odds ADD COLUMN IF NOT EXISTS home_spread NUMERIC(3,1);
ALTER TABLE market_odds ADD COLUMN IF NOT EXISTS home_spread_line INTEGER;
ALTER TABLE market_odds ADD COLUMN IF NOT EXISTS away_spread_line INTEGER;
ALTER TABLE market_odds ADD COLUMN IF NOT EXISTS home_cover_prob NUMERIC(5,4);
ALTER TABLE market_odds ADD COLUMN IF NOT EXISTS total NUMERIC(3,1);
ALTER TABLE market_odds ADD COLUMN IF NOT EXISTS over_line INTEGER;
ALTER TABLE market_odds ADD COLUMN IF NOT EXISTS under_line INTEGER;
ALTER TABLE market_odds ADD COLUMN IF NOT EXISTS over_prob NUMERIC(5,4);
"""
ODDS_COLUMNS = ("home_prob", "home_line", "away_line", "books", "best_home_line", "best_away_line",
                "home_spread", "home_spread_line", "away_spread_line", "home_cover_prob",
                "total", "over_line", "under_line", "over_prob")


def american_to_prob(price):
    """-150 -> 0.6, +130 -> 0.4348 (the book's implied probability, margin included)."""
    price = float(price)
    return -price / (-price + 100) if price < 0 else 100 / (price + 100)


def prob_to_american(prob):
    """0.6 -> -150, 0.4348 -> +130."""
    return round(-100 * prob / (1 - prob)) if prob >= 0.5 else round(100 * (1 - prob) / prob)


def median_price(prices):
    """The median of American prices, taken as probabilities: a plain median
    of -105 and +100 would be -2.5."""
    return prob_to_american(statistics.median(american_to_prob(p) for p in prices))


def best_price(prices):
    """The price that pays the most: +150 over +140, -105 over -120."""
    return min(prices, key=american_to_prob)


def today_eastern(now=None):
    return (now or datetime.now(EASTERN)).astimezone(EASTERN).date()


def _norm(name):
    """'St Louis Blues' and 'St. Louis Blues', 'Montréal' and 'Montreal' compare equal."""
    plain = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z]", "", plain.lower())


def _offers(event, market_key, first, second):
    """Each book's (point, first's no-margin probability, first's price, second's price) in one two-way market."""
    offers = []
    for book in event.get("bookmakers", []):
        market = next((m for m in book.get("markets", []) if m.get("key") == market_key), None)
        outcomes = {_norm(o["name"]): o for o in (market or {}).get("outcomes", [])}
        a, b = outcomes.get(_norm(first)), outcomes.get(_norm(second))
        if not a or not b:
            continue
        pa, pb = american_to_prob(a["price"]), american_to_prob(b["price"])
        offers.append((a.get("point"), pa / (pa + pb), a["price"], b["price"]))
    return offers


def _main_line(offers):
    """(point, offers at it): the point most books list, since a few post a different one."""
    point = Counter(o[0] for o in offers).most_common(1)[0][0]
    return point, [o for o in offers if o[0] == point]


def sportsbook_consensus(event, home_name, away_name):
    """
    For one Odds API event: from the moneylines, {"home_prob", "home_line",
    "away_line", "books", "best_home_line", "best_away_line"}; plus the
    puck line ("home_spread", "home_spread_line", "away_spread_line",
    "home_cover_prob") and total ("total", "over_line", "under_line",
    "over_prob"), None where no book posts them. Probabilities have each
    book's margin removed, then the median across books. None without a
    moneyline.
    """
    moneylines = _offers(event, "h2h", home_name, away_name)
    if not moneylines:
        return None
    odds = dict.fromkeys(ODDS_COLUMNS)
    odds.update(
        home_prob=round(statistics.median(o[1] for o in moneylines), 4),
        home_line=median_price([o[2] for o in moneylines]),
        away_line=median_price([o[3] for o in moneylines]),
        books=len(moneylines),
        best_home_line=best_price([o[2] for o in moneylines]),
        best_away_line=best_price([o[3] for o in moneylines]),
    )
    spreads = [o for o in _offers(event, "spreads", home_name, away_name) if o[0] is not None]
    if spreads:
        point, at = _main_line(spreads)
        odds.update(home_spread=point, home_cover_prob=round(statistics.median(o[1] for o in at), 4),
                    home_spread_line=median_price([o[2] for o in at]), away_spread_line=median_price([o[3] for o in at]))
    totals = [o for o in _offers(event, "totals", "Over", "Under") if o[0] is not None]
    if totals:
        point, at = _main_line(totals)
        odds.update(total=point, over_prob=round(statistics.median(o[1] for o in at), 4),
                    over_line=median_price([o[2] for o in at]), under_line=median_price([o[3] for o in at]))
    return odds


def log_sportsbooks(cur, day, games, names, get=None, captured="morning"):
    """
    games: [(game_id, home, away)]; names: {abbrev: full team name}. One Odds
    API call covers every upcoming game; only today's (Eastern) are logged.
    A closing snapshot replaces an earlier one for the same game.
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
        on_conflict = "DO NOTHING" if captured == "morning" else (
            "DO UPDATE SET " + ", ".join(f"{c} = EXCLUDED.{c}" for c in (*ODDS_COLUMNS, "captured_at")))
        cur.execute(
            f"""
            INSERT INTO market_odds (game_id, source, captured, game_date, home_abbrev, away_abbrev,
                                     {", ".join(ODDS_COLUMNS)}, captured_at)
            VALUES (%s, %s, %s, %s, %s, %s, {", ".join(["%s"] * len(ODDS_COLUMNS))}, NOW())
            ON CONFLICT (game_id, source, captured) {on_conflict}
            """,
            (game_id, SPORTSBOOKS, captured, day, home, away, *(odds[c] for c in ODDS_COLUMNS)),
        )
        logged += 1
    return logged


def _get_odds_api():
    response = requests.get(ODDS_API_URL, params={"apiKey": ODDS_API_KEY, "regions": "us",
                                                  "markets": "h2h,spreads,totals", "oddsFormat": "american"}, timeout=30)
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


def _credits_left():
    """The Odds API credits left this month (listing the sports is free)."""
    response = requests.get("https://api.the-odds-api.com/v4/sports", params={"apiKey": ODDS_API_KEY}, timeout=15)
    response.raise_for_status()
    return int(response.headers.get("x-requests-remaining", 0))


def _start(game):
    return datetime.fromisoformat(game["startTimeUTC"].replace("Z", "+00:00"))


def closing_due(games, have_close, now):
    """
    games: the NHL score feed's games; have_close: IDs already snapshotted.
    Once a not-started game without a closing snapshot is within CLOSE_LEAD
    of puck drop: every not-started game within CLOSE_COVER (one Odds API
    call covers them all). Otherwise [].
    """
    upcoming = [(g, _start(g)) for g in games if g.get("gameState") in NOT_STARTED and g.get("startTimeUTC")]
    upcoming = [(g, start) for g, start in upcoming if start > now]
    if not any(start - now <= CLOSE_LEAD and g["id"] not in have_close for g, start in upcoming):
        return []
    return [g for g, start in upcoming if start - now <= CLOSE_COVER]


def log_closing(now=None, get=_get, odds_get=None, credits=None):
    """
    The closing snapshot, if one is due. Runs every 5 minutes; most runs
    make one NHL request and stop. A game whose snapshot failed is retried
    on the next run until puck drop.
    """
    now = now or datetime.now(timezone.utc)
    day = today_eastern(now)
    games = get(NHL_SCORE_URL.format(date=day)).get("games", [])
    if not closing_due(games, set(), now):
        return 0
    with psycopg2.connect(DATABASE_URL) as conn, conn.cursor() as cur:
        cur.execute(TABLE_SQL)
        cur.execute(COLUMNS_SQL)
        cur.execute("SELECT DISTINCT game_id FROM market_odds WHERE captured = 'close' AND game_id = ANY(%s)",
                    ([g["id"] for g in games],))
        due = closing_due(games, {row[0] for row in cur.fetchall()}, now)
        if not due:
            return 0
        rows = [(g["id"], g["homeTeam"]["abbrev"], g["awayTeam"]["abbrev"]) for g in due]
        kalshi = log_games(cur, day, rows, captured="close", get=get)
        books = 0
        if ODDS_API_KEY or odds_get:
            try:
                left = (credits or _credits_left)()
            except requests.RequestException as exc:
                left = 0
                logger.warning(f"The Odds API unavailable ({exc})")
            if left >= CREDIT_FLOOR:
                cur.execute("SELECT team_abbrev, team_name FROM teams")
                books = log_sportsbooks(cur, day, rows, dict(cur.fetchall()), get=odds_get, captured="close")
            else:
                logger.warning(f"{left} Odds API credits left; skipping sportsbook closing odds")
    logger.info(f"Closing odds for {len(rows)} games: Kalshi {kalshi}, sportsbooks {books}")
    return len(rows)


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
    """Our predictions vs. each market and snapshot, graded on the same finished games."""
    with psycopg2.connect(DATABASE_URL) as conn, conn.cursor() as cur:
        for source, captured in ((s, c) for s in (SPORTSBOOKS, SOURCE) for c in ("morning", "close")):
            cur.execute(
                """
                SELECT p.game_date, p.away_abbrev, p.home_abbrev, p.home_win_prob, m.home_prob, p.home_won
                FROM game_predictions p
                JOIN market_odds m ON m.game_id = p.game_id AND m.source = %s AND m.captured = %s
                WHERE p.home_won IS NOT NULL
                ORDER BY p.game_date
                """,
                (source, captured),
            )
            rows = cur.fetchall()
            print(f"\nPuckPulse vs {source} ({captured}):",
                  compare([(float(o), float(m), bool(y)) for *_, o, m, y in rows]))
            for day, away, home, o, m, won in sorted(rows, key=lambda r: -abs(float(r[3]) - float(r[4])))[:5]:
                print(f"  {day} {away} @ {home}: ours {float(o):.0%}, {source} {float(m):.0%}, home {'won' if won else 'lost'}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", action="store_true")
    parser.add_argument("--close", action="store_true", help="closing snapshot, if one is due")
    args = parser.parse_args()
    if not DATABASE_URL:
        raise SystemExit("DATABASE_URL is not set")
    if args.report:
        report()
    elif args.close:
        log_closing()
    else:
        log_today()


if __name__ == "__main__":
    main()
