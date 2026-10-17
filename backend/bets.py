"""
The Bets tab: each game's lines next to PuckPulse's fair odds.

For every game: the moneyline, puck line, and total, each side with
  - model: PuckPulse's own chance (the win model; the goal model for the
    puck line and total, at the books' line),
  - market: the books' chance with their margin removed,
  - ours: the fair chance we stand behind, MODEL_WEIGHT of the model and
    the rest the market. The books are sharp and our edge on them isn't
    proven yet, so the model only nudges the market; raise the weight as
    the closing-line report card earns it,
  - fair: ours as American odds (what the price "should" be),
  - price: the price to bet at (the best book's for the moneyline, the
    median for the puck line and total),
  - edge: ours minus the market's, and ev: the expected return per $1 at
    that price (ours x decimal odds - 1),
  - value: the model leans this way (edge > 0) and ev is at least
    VALUE_EV. With the blend that takes both some disagreement and a good
    price, so line shopping (one book paying more) counts.
Totals never get a value flag: in the backtest our totals didn't beat
always guessing the average, so they're shown as experimental.
"""

import goal_model
from market_odds import american_to_prob, prob_to_american

MODEL_WEIGHT = 0.3
VALUE_EV = 0.02


def decimal_odds(price):
    """+150 -> 2.5, -200 -> 1.5 (the payout per $1 staked, stake included)."""
    return 1 + (price / 100 if price > 0 else 100 / -price)


def _side(model, market, price, flag=True, book=None):
    ours = model if market is None else MODEL_WEIGHT * model + (1 - MODEL_WEIGHT) * market
    side = {"model": round(model, 4), "ours": round(ours, 4), "fair": prob_to_american(min(max(ours, 0.01), 0.99))}
    if market is not None:
        side["market"] = round(market, 4)
        side["edge"] = round(ours - market, 4)
    if price is not None:
        side["price"] = int(price)
        side["ev"] = round(ours * decimal_odds(price) - 1, 4)
        if book:
            side["book"] = book
    side["value"] = bool(flag and side.get("edge", 0) > 0 and side.get("ev", -1) >= VALUE_EV)
    return side


def _num(value):
    return float(value) if value is not None else None


def game_board(pred, market=None, b2b=(False, False)):
    """
    pred: {"home", "away", "home_win_prob", "home_goals", "away_goals"};
    market: a market_odds sportsbooks row as a dict, or None.
    """
    m = market or {}
    p = float(pred["home_win_prob"])
    board = {"home": pred["home"], "away": pred["away"], "b2b": {"home": bool(b2b[0]), "away": bool(b2b[1])},
             "snapshot": m.get("captured"), "as_of": m.get("captured_at"), "books": m.get("books")}
    home_market = _num(m.get("home_prob"))
    board["moneyline"] = {
        "home": _side(p, home_market, m.get("best_home_line") or m.get("home_line"), book=m.get("best_home_book")),
        "away": _side(1 - p, None if home_market is None else 1 - home_market,
                      m.get("best_away_line") or m.get("away_line"), book=m.get("best_away_book")),
    }
    if pred.get("home_goals") is None:
        return board
    scores = goal_model.final_scores(float(pred["home_goals"]), float(pred["away_goals"]))
    spread = _num(m.get("home_spread"))
    if spread is None:  # no line posted: the favorite gives 1.5
        spread = -1.5 if p >= 0.5 else 1.5
    cover = goal_model.home_covers(scores, spread)
    cover_market = _num(m.get("home_cover_prob"))
    board["puck_line"] = {
        "home_spread": spread,
        "home": _side(cover, cover_market, m.get("home_spread_line")),
        "away": _side(1 - cover, None if cover_market is None else 1 - cover_market, m.get("away_spread_line")),
    }
    line = _num(m.get("total")) or 6.5
    over = goal_model.over(scores, line)
    under = 1 - over - sum(q for (h, a), q in scores.items() if h + a == line)  # a whole-number line can push
    over_market = _num(m.get("over_prob"))
    board["total"] = {
        "line": line, "experimental": True,
        "over": _side(over, over_market, m.get("over_line"), flag=False),
        "under": _side(under, None if over_market is None else 1 - over_market, m.get("under_line"), flag=False),
    }
    return board
