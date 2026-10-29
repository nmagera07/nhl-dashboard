"""
Value of the night: the one bet on a day's slate PuckPulse likes best,
for the card at the top of the Bets tab.

It's picked from the morning lines (the sportsbook snapshot logged with
the 2 AM predictions), so it's fixed before any game starts and can be
graded honestly, win or lose and against the closing line, without
storing anything: any past night's pick is rebuilt the same way.

- The pick: among moneyline and puck line sides with a price, the highest
  expected return of those flagged as value (bets.py). On a night with
  none, the closest one: the highest expected return among the sides the
  model leans toward (edge > 0), marked value=False so the card says it's
  below the value bar. Totals are never picked (their model is beta).
- Grading: 1 unit at the pick's price, from the final score; CLV is the
  expected return of that price by the books' closing odds with their
  margin removed, only when the line didn't move.
"""

from datetime import date

import bets

MARKETS = ("moneyline", "puck_line")


def season_start(day: date) -> date:
    return date(day.year if day.month >= 9 else day.year - 1, 9, 1)


def _line(board, market, side):
    if market != "puck_line":
        return None
    spread = board["puck_line"]["home_spread"]
    return spread if side == "home" else -spread


def pick(boards: dict) -> dict | None:
    """boards: {game_id: bets.game_board}. The night's pick, or None without prices."""
    sides = []
    for game_id, board in boards.items():
        for market in MARKETS:
            for side, s in (board.get(market) or {}).items():
                if isinstance(s, dict) and s.get("price") is not None and s.get("edge") is not None:
                    sides.append((game_id, board, market, side, s))
    value = [x for x in sides if x[4]["value"]]
    leaning = [x for x in sides if x[4]["edge"] > 0]
    pool = value or leaning
    if not pool:
        return None
    game_id, board, market, side, s = max(pool, key=lambda x: x[4]["ev"])
    return {
        "game_id": int(game_id), "away": board["away"], "home": board["home"], "market": market, "side": side,
        "line": _line(board, market, side), "price": s["price"], "book": s.get("book"),
        "ev": s["ev"], "edge": s["edge"], "ours": s["ours"], "model": s["model"], "market_prob": s["market"],
        "value": bool(s["value"]),
    }


def grade(p: dict, final: dict, close_board: dict | None) -> dict | None:
    """final: {"home_score", "away_score"} once graded. {outcome, units, clv, close_price}, or None."""
    if final.get("home_score") is None or final.get("away_score") is None:
        return None
    margin = final["home_score"] - final["away_score"]
    if p["side"] == "away":
        margin = -margin
    margin += p["line"] or 0
    outcome = "win" if margin > 0 else "loss" if margin < 0 else "push"
    units = bets.decimal_odds(p["price"]) - 1 if outcome == "win" else -1 if outcome == "loss" else 0
    close = (close_board or {}).get(p["market"], {}).get(p["side"]) if close_board else None
    same_line = close is not None and _line(close_board, p["market"], p["side"]) == p["line"]
    clv = (round(close["market"] * bets.decimal_odds(p["price"]) - 1, 4)
           if same_line and close.get("market") is not None else None)
    return {"outcome": outcome, "units": round(units, 4), "clv": clv,
            "close_price": close.get("price") if same_line else None}


def _boards(predictions, markets, captured):
    """{game_date: {game_id: board}} from predictions and one snapshot's market rows."""
    out = {}
    for p in predictions:
        market = markets.get((p["game_id"], captured))
        if not market:
            continue
        pred = {"home": p["home_abbrev"], "away": p["away_abbrev"], "home_win_prob": p["home_win_prob"],
                "home_goals": p["home_goals"], "away_goals": p["away_goals"]}
        out.setdefault(p["game_date"], {})[str(p["game_id"])] = bets.game_board(pred, market)
    return out


def record(nights: list[dict]) -> dict:
    graded = [n for n in nights if n.get("result")]

    def count(outcome):
        return sum(1 for n in graded if n["result"]["outcome"] == outcome)
    with_clv = [n["result"]["clv"] for n in graded if n["result"]["clv"] is not None]
    return {
        "nights": len(graded), "wins": count("win"), "losses": count("loss"), "pushes": count("push"),
        "units": round(sum(n["result"]["units"] for n in graded), 2),
        "value_nights": sum(1 for n in graded if n["pick"]["value"]),
        "beat_close": sum(1 for c in with_clv if c > 0), "clv_count": len(with_clv),
        "clv": round(sum(with_clv) / len(with_clv), 4) if with_clv else None,
    }


def value_of_the_night(cur, day: date) -> dict:
    """{"date", "available", "pick", "result", "record"}: the day's pick and the season's record before it."""
    cur.execute(
        """
        SELECT game_id, game_date, home_abbrev, away_abbrev, home_win_prob, home_goals, away_goals,
               home_score, away_score
        FROM game_predictions WHERE game_date BETWEEN %s AND %s
        """,
        (season_start(day), day),
    )
    predictions = cur.fetchall()
    cur.execute(
        """
        SELECT * FROM market_odds
        WHERE source = 'sportsbooks' AND game_date BETWEEN %s AND %s AND captured IN ('morning', 'close')
        """,
        (season_start(day), day),
    )
    markets = {(r["game_id"], r["captured"]): dict(r) for r in cur.fetchall()}
    mornings, closes = _boards(predictions, markets, "morning"), _boards(predictions, markets, "close")
    finals = {p["game_id"]: p for p in predictions}

    def night(d):
        p = pick(mornings.get(d, {}))
        if not p:
            return None
        close = closes.get(d, {}).get(str(p["game_id"]))
        return {"date": d.isoformat(), "pick": p, "result": grade(p, finals[p["game_id"]], close)}

    past = [n for n in (night(d) for d in sorted(mornings) if d < day) if n]
    today = night(day)
    return {
        "date": day.isoformat(), "available": today is not None,
        "pick": today and today["pick"], "result": today and today["result"],
        "record": record(past), "last": past[-1] if past else None,
    }
