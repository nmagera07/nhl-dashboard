"""war_v2: goals above average from RAPM and the other parts, then replacement level and wins."""

import pytest

import war_v2

LEAGUE = {"pp_seconds": 3600.0, "pp_xgf": 7.0, "pk_seconds": 3600.0, "pk_xga": 7.0, "pp_net_xg": 6.0, "pim": 40}


def _player(pos="F", gp=82, **kw):
    base = {"name": "X", "pos": pos, "team": "PIT", "gp": gp, "goals": 0, "ixg": 0.0, "pim_taken": 0, "pim_drawn": 0,
            "pp_seconds": 0.0, "pp_xgf": 0.0, "pk_seconds": 0.0, "pk_xga": 0.0}
    return {**base, **kw}


def test_each_part_in_goals():
    inputs = {"league": LEAGUE, "players": {1: _player(goals=30, ixg=24.0, pim_drawn=20, pim_taken=10,
                                                       pp_seconds=7200.0, pp_xgf=19.0, pk_seconds=1800.0, pk_xga=2.5)}}
    ev = {1: {"offense": 0.3, "defense": -0.1, "hours": 20.0}}
    parts = war_v2.goals_above_average(inputs, ev)[1]
    assert parts["ev_offense"] == pytest.approx(6.0) and parts["ev_defense"] == pytest.approx(-2.0)
    assert parts["finishing"] == pytest.approx(6.0)
    assert parts["power_play"] == pytest.approx((19.0 - 14.0) / 5)    # 2 hours at 7 xG/hour expected
    assert parts["penalty_kill"] == pytest.approx((3.5 - 2.5) / 4)    # half an hour: 3.5 expected against
    assert parts["penalties"] == pytest.approx(10 * 6.0 / 40)          # 10 more minutes drawn than taken
    assert parts["total"] == pytest.approx(sum(v for k, v in parts.items() if k != "total"))
    assert war_v2.goals_above_average(inputs, ev, finishing_weight=0.5)[1]["finishing"] == pytest.approx(3.0)


def test_replacement_is_the_fringe_players_rate_per_game():
    players = {1: _player(gp=80, goals=10, ixg=0.0), 2: _player(gp=10, goals=0, ixg=2.0), 3: _player(gp=20, goals=0, ixg=3.0),
               4: _player(pos="D", gp=80)}
    out = war_v2.skater_war({"league": LEAGUE, "players": players}, ev={}, goals_per_win=5.0, finishing_weight=1.0)
    rate = (-2.0 - 3.0) / 30  # the 5-29 GP forwards: -5 goals over 30 games
    assert out[1]["gar"] == pytest.approx(round(10 - rate * 80, 2), abs=0.01)
    assert out[1]["war"] == pytest.approx(out[1]["gar"] / 5.0, abs=0.01)
    assert out[2]["parts"]["finishing"] == -2.0


class FakeDb:
    """Just enough of a psycopg2 connection for war_v2.nightly: the games, the stored extracts, the ratings."""

    def __init__(self, games, prior=()):
        self.games, self.prior, self.stored, self.ratings, self.commits = games, list(prior), {}, [], 0

    def cursor(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def commit(self):
        self.commits += 1

    def execute(self, sql, params=None):
        sql = " ".join(sql.split())
        self.rows = []
        if "FROM team_game_xg" in sql:
            self.rows = [g for g in self.games if g[0] not in self.stored]
        elif sql.startswith("INSERT INTO war_v2_games"):
            self.stored[params[0]] = params
        elif "FROM war_v2_games" in sql:
            self.rows = [(gid, p[4]) for gid, p in self.stored.items()]
        elif "FROM rapm_ratings" in sql:
            self.rows = self.prior
        elif sql.startswith("INSERT INTO rapm_ratings"):
            self.ratings.append(params)

    def fetchall(self):
        return self.rows


def test_the_nightly_step_stores_games_fits_with_last_seasons_prior_and_saves_ratings(monkeypatch):
    from datetime import date

    from tests.test_rapm_stints import PBP, ROSTER, SHIFTS

    pbp = {**PBP, "rosterSpots": [{**r, "firstName": {"default": "P"}, "lastName": {"default": str(r["playerId"])}}
                                  for r in ROSTER]}
    calls = []

    def get(url):
        calls.append(url)
        return pbp if "play-by-play" in url else {"data": []}  # no shift chart: the HTML reports stand in

    monkeypatch.setattr(war_v2.rs, "html_shifts", lambda p, get_text: SHIFTS)
    monkeypatch.setattr(war_v2.rs, "MIN_SHIFTS", 5)  # the fixture's game is two minutes long
    db = FakeDb(games=[(2025020001, date(2026, 10, 20))], prior=[(21, 0.5, 0.1)])
    players = war_v2.nightly(db, 20262027, date(2026, 10, 27), get=get, get_text=None, pause=0)

    assert db.stored[2025020001][3] is True and db.commits == 2  # has stints; games kept before the fit
    assert len(calls) == 2
    rated = {params[1]: params for params in db.ratings}
    assert rated[21][0] == 20262027 and rated[21][2] > 0.3  # pulled toward last season's +0.5, not to 0
    assert players[1]["gp"] == 1 and set(players[1]["parts"]) >= set(war_v2.LABELS)
    db.games.append((2025020001, date(2026, 10, 20)))
    assert war_v2.games_to_fetch(db, 20262027, date(2026, 10, 27)) == []  # stored: not fetched again
