"""
The report card: PuckPulse against the sportsbooks on finished games,
for the last 7 days and the season.

  - Picking winners: how often each side's favorite won, and the Brier
    score (the mean squared error of the win chances; lower is better,
    0.25 is a coin flip) for the moneyline, puck line, and total, ours vs.
    the books' (margin removed) on the same games. The books' line is the
    closing one when we have it (the hardest benchmark), else the morning's.
  - Value badges: every side the Bets tab's current rules flag at that
    line (bets.py), graded as a $100 bet at the price shown: the record and
    the profit. Recomputed with today's rules, so it says how they'd have
    done, not what the page showed at the time.
  - Where we disagreed most with the books, and who was right.

Uses the model's own chances for the Brier (its skill), and the Bets
tab's blend for the value badges (what users see).
"""

import goal_model
from bets import decimal_odds, game_board


def brier(pairs):
    return round(sum((p - y) ** 2 for p, y in pairs) / len(pairs), 4) if pairs else None


def _favorite_won(pairs):
    picks = [(p > 0.5) == bool(y) for p, y in pairs if p != 0.5]
    return round(sum(picks) / len(picks), 4) if picks else None


def _bet_result(market, side, game):
    """+1 win, 0 push, -1 loss for one side of a graded game."""
    hs, as_ = game["home_score"], game["away_score"]
    if market == "moneyline":
        won = (hs > as_) if side == "home" else (as_ > hs)
        return 1 if won else -1
    spread = game["home_spread"] if side == "home" else -game["home_spread"]
    margin = (hs - as_) if side == "home" else (as_ - hs)
    return 0 if margin + spread == 0 else (1 if margin + spread > 0 else -1)


def summarize(games):
    """
    games: graded games, each {"away", "home", "game_date", "home_win_prob",
    "home_goals", "away_goals", "home_score", "away_score", "market": a
    market_odds row or None}.
    """
    ml_ours, ml_books, pl_ours, pl_books, tot_ours, tot_books = [], [], [], [], [], []
    disagreements, value = [], []
    for g in games:
        home_won = g["home_score"] > g["away_score"]
        p = float(g["home_win_prob"])
        m = g.get("market") or {}
        books_p = m.get("home_prob")
        if books_p is not None:
            ml_ours.append((p, home_won))
            ml_books.append((float(books_p), home_won))
            disagreements.append({"date": str(g["game_date"]), "away": g["away"], "home": g["home"],
                                  "ours": round(p, 4), "books": round(float(books_p), 4), "home_won": home_won})
        if g.get("home_goals") is not None and m:
            scores = goal_model.final_scores(float(g["home_goals"]), float(g["away_goals"]))
            if m.get("home_spread") is not None and m.get("home_cover_prob") is not None:
                covered = g["home_score"] + float(m["home_spread"]) > g["away_score"]
                pl_ours.append((goal_model.home_covers(scores, float(m["home_spread"])), covered))
                pl_books.append((float(m["home_cover_prob"]), covered))
            if m.get("total") is not None and m.get("over_prob") is not None:
                total = g["home_score"] + g["away_score"]
                if total != float(m["total"]):  # a push isn't graded
                    tot_ours.append((goal_model.over(scores, float(m["total"])), total > float(m["total"])))
                    tot_books.append((float(m["over_prob"]), total > float(m["total"])))
        if m:
            pred = {"home": g["home"], "away": g["away"], "home_win_prob": p,
                    "home_goals": g.get("home_goals"), "away_goals": g.get("away_goals")}
            board = game_board(pred, m)
            for market in ("moneyline", "puck_line"):
                for side in ("home", "away"):
                    s = (board.get(market) or {}).get(side) or {}
                    if not s.get("value"):
                        continue
                    home_spread = (board.get("puck_line") or {}).get("home_spread")
                    result = _bet_result(market, side, {**g, "home_spread": home_spread})
                    team = g["home"] if side == "home" else g["away"]
                    spread = home_spread if side == "home" else -home_spread if home_spread is not None else None
                    label = team if market == "moneyline" else f"{team} {spread:+.1f}"
                    profit = 100 * (decimal_odds(s["price"]) - 1) if result > 0 else (0 if result == 0 else -100)
                    value.append({"date": str(g["game_date"]), "game": f"{g['away']} @ {g['home']}", "bet": label,
                                  "price": s["price"], "book": s.get("book"), "result": result, "profit": round(profit, 2)})
    disagreements.sort(key=lambda d: -abs(d["ours"] - d["books"]))
    wins = sum(v["result"] > 0 for v in value)
    losses = sum(v["result"] < 0 for v in value)
    return {
        "games": len(games),
        "moneyline": {"games": len(ml_ours), "brier_ours": brier(ml_ours), "brier_books": brier(ml_books),
                      "favorite_won_ours": _favorite_won(ml_ours), "favorite_won_books": _favorite_won(ml_books)},
        "puck_line": {"games": len(pl_ours), "brier_ours": brier(pl_ours), "brier_books": brier(pl_books)},
        "total": {"games": len(tot_ours), "brier_ours": brier(tot_ours), "brier_books": brier(tot_books)},
        "value_bets": {"bets": len(value), "wins": wins, "losses": losses, "pushes": len(value) - wins - losses,
                       "profit": round(sum(v["profit"] for v in value), 2), "list": value[-20:][::-1]},
        "disagreements": disagreements[:5],
    }
