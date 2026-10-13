"""moneypuck_odds: MoneyPuck's playoff odds logged next to ours."""

from datetime import date

import pytest
import requests

import moneypuck_odds as mp

CSV = "\n".join([
    "scenerio,teamCode,madePlayoffs,wonCup,points",
    "ALL,CAR,0.9487,0.102,110.3",
    "WINREG,CAR,0.9579,0.102,111.0",
    "ALL,PIT,0.41,0.011,88.0",
])


def test_keeps_only_the_unconditional_odds():
    assert mp.parse_simulations(CSV) == {
        "CAR": {"playoff_pct": 0.9487, "won_cup_pct": 0.102, "projected_points": 110.3},
        "PIT": {"playoff_pct": 0.41, "won_cup_pct": 0.011, "projected_points": 88.0},
    }


def test_the_update_date_is_the_as_of_date():
    assert mp.parse_updated("2026-10-13 04:28:23.552876-04:00\n") == ("2026-10-13 04:28:23.552876-04:00", date(2026, 10, 13))


def test_head_to_head_agreement_before_the_season_ends_and_brier_after():
    rows = [("2026-10-13", "CAR", 0.9, 0.95), ("2026-10-13", "PIT", 0.6, 0.4)]
    assert mp.head_to_head(rows, {}) == {"days": 1, "mean_abs_diff": 0.125}

    scored = mp.head_to_head(rows, {"CAR": 1.0, "PIT": 0.0})
    assert scored["brier_ours"] == pytest.approx((0.1 ** 2 + 0.6 ** 2) / 2, abs=1e-4)
    assert scored["brier_moneypuck"] == pytest.approx((0.05 ** 2 + 0.4 ** 2) / 2, abs=1e-4)


def test_an_outage_or_partial_file_skips_the_day_without_failing(monkeypatch):
    def down(url):
        raise requests.ConnectionError("down")

    monkeypatch.setattr(mp, "_get", down)
    monkeypatch.setattr(mp.psycopg2, "connect", lambda *_: pytest.fail("should not touch the DB"))
    mp.log_today()

    monkeypatch.setattr(mp, "_get", lambda url: "2026-10-13 04:28:23-04:00" if url == mp.UPDATED_URL else CSV)
    mp.log_today()  # 2 teams, not 32: skipped
