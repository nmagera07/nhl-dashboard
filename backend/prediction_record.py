"""
Scores the model's logged game predictions (see game_predictions.py) for
the API: how often the favorite won, the Brier score against a coin flip,
and calibration (when the model said 60%, did it happen about 60% of the
time?). Pure functions, so the API doesn't import the daily job's code.
"""

# Calibration buckets, by the favorite's probability.
BUCKETS = [(0.50, 0.55), (0.55, 0.60), (0.60, 0.65), (0.65, 1.01)]


def track_record(rows: list[dict], recent: int = 20) -> dict:
    """
    Score graded predictions. Each row needs home_win_prob and home_won
    (plus whatever the recent list should show).

    - favorite_won: share of games the model's favorite won (50/50 calls skipped)
    - brier: mean squared error of the probabilities; 0.25 is a coin flip,
      lower is better (good hockey models land around 0.23-0.24: single
      games are close to coin flips)
    - calibration: per bucket of the favorite's probability, how often the
      favorite actually won
    """
    graded = [r for r in rows if r.get("home_won") is not None]
    if not graded:
        return {"games": 0, "favorite_won": None, "brier": None, "coin_flip_brier": 0.25,
                "calibration": [], "recent": []}

    picks = []  # (favorite's probability, favorite won)
    for r in graded:
        p = float(r["home_win_prob"])
        if p != 0.5:
            picks.append((max(p, 1 - p), (p > 0.5) == bool(r["home_won"])))
    brier = sum((float(r["home_win_prob"]) - (1.0 if r["home_won"] else 0.0)) ** 2 for r in graded) / len(graded)

    calibration = []
    for lo, hi in BUCKETS:
        inside = [(p, won) for p, won in picks if lo <= p < hi]
        if inside:
            calibration.append({
                "label": f"{round(lo * 100)}%+" if hi > 1 else f"{round(lo * 100)}-{round(hi * 100)}%",
                "games": len(inside),
                "predicted": round(sum(p for p, _ in inside) / len(inside), 4),
                "actual": round(sum(won for _, won in inside) / len(inside), 4),
            })

    newest = sorted(graded, key=lambda r: (str(r.get("game_date")), r.get("game_id", 0)), reverse=True)[:recent]
    return {
        "games": len(graded),
        "favorite_won": round(sum(won for _, won in picks) / len(picks), 4) if picks else None,
        "brier": round(brier, 4),
        "coin_flip_brier": 0.25,
        "calibration": calibration,
        "recent": [_recent_row(r) for r in newest],
    }


def _recent_row(r: dict) -> dict:
    p = float(r["home_win_prob"])
    return {
        "game_id": r.get("game_id"), "game_date": str(r.get("game_date")),
        "home": r.get("home_abbrev"), "away": r.get("away_abbrev"),
        "home_win_prob": p, "home_score": r.get("home_score"), "away_score": r.get("away_score"),
        "ended": r.get("ended"), "favorite_won": None if p == 0.5 else (p > 0.5) == bool(r["home_won"]),
    }
