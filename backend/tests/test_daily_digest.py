"""daily_digest: gathering the morning digest's facts (the AI only writes them up)."""

from datetime import date

import daily_digest as dd


def _game(away, away_score, home, home_score, state="OFF", ended="REG", goals=(), start="2026-10-10T23:00:00Z"):
    return {
        "gameState": state, "startTimeUTC": start, "gameOutcome": {"lastPeriodType": ended},
        "awayTeam": {"abbrev": away, "score": away_score, "name": {"default": away.title()}},
        "homeTeam": {"abbrev": home, "score": home_score, "name": {"default": home.title()}},
        "goals": list(goals),
    }


def _goal(name, team, assists=(), period_type="REG"):
    return {"name": {"default": name}, "teamAbbrev": team, "periodDescriptor": {"periodType": period_type},
            "assists": [{"name": {"default": a}} for a in assists]}


def test_results_keep_finals_with_overtime_and_shootouts():
    games = [_game("PIT", 2, "CBJ", 3, ended="SO"), _game("SEA", 6, "DET", 3), _game("BOS", None, "TOR", None, state="FUT")]
    assert dd.results(games) == [
        {"away": "PIT", "away_score": 2, "home": "CBJ", "home_score": 3, "ended": "SO"},
        {"away": "SEA", "away_score": 6, "home": "DET", "home_score": 3},
    ]


def test_standouts_are_multi_goal_or_three_point_nights_without_shootout_goals():
    goals = [
        _goal("F. Gaudreau", "SEA"), _goal("F. Gaudreau", "SEA", assists=["B. Meyers"]),
        _goal("J. Eberle", "SEA", assists=["B. Meyers", "V. Dunn"]), _goal("B. Meyers", "SEA"),
        _goal("K. Johnson", "CBJ", period_type="SO"), _goal("K. Johnson", "CBJ"),  # one real goal, one SO
    ]
    rows = dd.standouts([_game("SEA", 6, "DET", 3, goals=goals)])
    assert [(r["player"], r["goals"], r["assists"]) for r in rows] == [("B. Meyers", 1, 2), ("F. Gaudreau", 2, 0)]


def test_odds_movers_compare_the_two_latest_runs_and_skip_small_moves():
    history = [
        (date(2026, 10, 9), "ANA", 0.590), (date(2026, 10, 10), "ANA", 0.668),
        (date(2026, 10, 9), "WPG", 0.540), (date(2026, 10, 10), "WPG", 0.435),
        (date(2026, 10, 9), "PIT", 0.597), (date(2026, 10, 10), "PIT", 0.587),  # 1 point: noise
    ]
    assert dd.odds_movers(history) == {
        "rising": [{"team": "ANA", "from_pct": 59.0, "to_pct": 66.8, "change": 7.8}],
        "falling": [{"team": "WPG", "from_pct": 54.0, "to_pct": 43.5, "change": -10.5}],
    }
    assert dd.odds_movers(history[:1]) == {}  # only one run so far


def test_tonight_has_eastern_times_and_model_odds_and_picks_the_closest_game():
    model = {"home_edge": 0.264, "scale": 1.47}
    games = [_game("CBJ", None, "STL", None, state="FUT", start="2026-10-10T23:00:00Z"),
             _game("CHI", None, "COL", None, state="FUT", start="2026-10-11T01:00:00Z")]
    rows = dd.tonight(games, {"CBJ": 0.1, "STL": -0.164, "CHI": -0.6, "COL": 0.6}, model)

    assert rows[0] == {"away": "CBJ", "home": "STL", "time": "7:00 PM ET", "model_home_win_pct": 50}
    assert rows[1]["time"] == "9:00 PM ET" and rows[1]["model_home_win_pct"] == 73  # (1.2 + 0.264) / 1.47 -> 73%
    assert dd.game_of_the_night(rows)["home"] == "STL"


def test_today_eastern_rolls_over_at_eastern_midnight():
    from datetime import datetime, timezone

    assert dd.today_eastern(datetime(2026, 10, 10, 6, 0, tzinfo=timezone.utc)) == date(2026, 10, 10)  # 2 AM ET
    assert dd.today_eastern(datetime(2026, 10, 10, 3, 0, tzinfo=timezone.utc)) == date(2026, 10, 9)   # 11 PM ET


def test_write_without_configuration_stores_facts_only(monkeypatch):
    monkeypatch.setattr(dd, "INTELLIGENCE_URL", "")
    assert dd.write({"date": "x"}) == (None, None)


def test_lines_spell_out_names_winner_first():
    finals = [{"away": "PIT", "away_score": 2, "home": "CBJ", "home_score": 3, "ended": "SO"}]
    movers = {"falling": [{"team": "WPG", "from_pct": 54.0, "to_pct": 43.5, "change": -10.5}]}
    featured = {"away": "CBJ", "home": "STL", "time": "7:00 PM ET", "model_home_win_pct": 50}

    dd.add_lines(finals, movers, featured, {"PIT": "Penguins", "CBJ": "Blue Jackets", "WPG": "Jets", "STL": "Blues"})

    assert finals[0]["line"] == "Blue Jackets 3, Penguins 2 (SO)"
    assert movers["falling"][0]["line"] == "Jets: 54% to 44%"
    assert featured["line"] == "Blue Jackets at Blues, 7:00 PM ET; the model gives the Blues 50%"
