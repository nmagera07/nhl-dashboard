"""ingest_xg: per-game PuckPulse xG, and the odds step's choice of xG source."""

from datetime import date

import ingest_xg as ix
import simulate_playoff_odds as sim
import xg_model as xm

MODEL = {"version": 1, "coefficients": [-2.0] + [0.0] * (len(xm.FEATURE_NAMES) - 1)}  # every shot ~0.119


def _shot(kind, t, team, x):
    return {"typeDescKey": kind, "timeInPeriod": f"00:{t:02d}", "situationCode": "1551", "homeTeamDefendingSide": "right",
            "periodDescriptor": {"number": 1, "periodType": "REG"},
            "details": {"eventOwnerTeamId": team, "zoneCode": "O", "xCoord": x, "yCoord": 0}}


PBP = {"id": 2026020001, "homeTeam": {"id": 1, "abbrev": "PIT"}, "awayTeam": {"id": 2, "abbrev": "WSH"},
       "plays": [_shot("shot-on-goal", 5, 1, -70), _shot("goal", 20, 1, -80), _shot("missed-shot", 40, 2, 60)]}


def test_game_totals_add_each_teams_shots():
    pit, wsh = ix.game_totals(PBP, MODEL)
    each = xm.predict(xm.shots_from_game(PBP)[0], MODEL)
    assert (pit["team"], pit["is_home"], pit["shots_for"], pit["goals_for"]) == ("PIT", True, 2, 1)
    assert pit["xg_for"] == round(2 * each, 3) and pit["xg_against"] == round(each, 3)
    assert (wsh["shots_for"], wsh["goals_against"]) == (1, 1)


class FakeCursor:
    def __init__(self, stored=(), missing_starters=(), missing_goalies=()):
        self.stored, self.inserted, self.sql = list(stored), [], []
        self.missing_starters, self.updated = [(g,) for g in missing_starters], []
        self.missing_goalies = [(g, 2) for g in missing_goalies]

    def execute(self, sql, params=None):
        self.sql.append(sql)
        if sql.lstrip().startswith("INSERT"):
            self.inserted.append(params)
        if sql.lstrip().startswith("UPDATE"):
            self.updated.append(params)

    def fetchall(self):
        if "starting_goalie_id IS NULL" in self.sql[-1]:
            return self.missing_starters
        return self.missing_goalies if "NOT EXISTS" in self.sql[-1] else self.stored


def test_update_scores_only_new_finished_games_through_yesterday():
    days = {"2026-10-12": [{"id": 2026020001, "gameState": "OFF", "gameType": 2},
                           {"id": 2026020002, "gameState": "OFF", "gameType": 2},
                           {"id": 9, "gameState": "OFF", "gameType": 1}],      # preseason: skipped
            "2026-10-13": [{"id": 2026020003, "gameState": "LIVE", "gameType": 2}]}
    asked = []

    def get(url):
        asked.append(url)
        if "/score/" in url:
            return {"games": days.get(url.rsplit("/", 1)[-1], [])}
        return PBP

    cur = FakeCursor(stored=[(2026020001, date(2026, 10, 12))])
    added = ix.update(cur, 20262027, today=date(2026, 10, 14), get=get, model=MODEL)

    assert added == 1 and len(cur.inserted) == 2  # game 2, both teams
    assert any("GRANT SELECT ON team_game_xg" in s for s in cur.sql)
    assert sum("/play-by-play" in u for u in asked) == 1
    assert asked[0].endswith("/score/2026-10-11")  # one day before the latest stored date


def test_odds_use_puckpulse_xg_only_when_every_game_is_scored():
    standings = {"PIT": {"games_played": 3}, "WSH": {"games_played": 2}}
    complete = [("PIT", 1.5, 3), ("WSH", -0.5, 2)]
    assert sim.puckpulse_xgd(20262027, standings, rows=complete) == {"PIT": (1.5, 3), "WSH": (-0.5, 2)}
    assert sim.puckpulse_xgd(20262027, standings, rows=[("PIT", 1.5, 2), ("WSH", -0.5, 2)]) == {}  # PIT missing a game


def _pbp_with_goalies():
    return {"homeTeam": {"id": 1, "abbrev": "PIT"}, "awayTeam": {"id": 2, "abbrev": "CBJ"}, "plays": [
        {"typeDescKey": "faceoff", "details": {"eventOwnerTeamId": 1}},
        {"typeDescKey": "shot-on-goal", "details": {"eventOwnerTeamId": 1, "goalieInNetId": 900}},  # CBJ's goalie
        {"typeDescKey": "shot-on-goal", "details": {"eventOwnerTeamId": 1, "goalieInNetId": 901}},  # later: ignored
        {"typeDescKey": "missed-shot", "details": {"eventOwnerTeamId": 2, "goalieInNetId": 800}},  # PIT's goalie
    ]}


def test_starters_are_the_goalies_in_net_for_each_teams_first_shot_against():
    import goalie_starts
    assert goalie_starts.starters(_pbp_with_goalies()) == {"CBJ": 900, "PIT": 800}


def test_games_stored_before_starters_were_recorded_get_filled_in():
    cur = FakeCursor(missing_starters=[2026020009])
    assert ix.fill_starters(cur, 20262027, get=lambda url: _pbp_with_goalies()) == 1
    assert sorted(cur.updated) == [(800, 2026020009, "PIT"), (900, 2026020009, "CBJ")]


def _goalie_shot(kind, t, team, x, goalie):
    shot = _shot(kind, t, team, x)
    shot["details"]["goalieInNetId"] = goalie
    return shot


GOALIE_PBP = {"id": 2026020005, "homeTeam": {"id": 1, "abbrev": "PIT"}, "awayTeam": {"id": 2, "abbrev": "WSH"}, "plays": [
    _goalie_shot("shot-on-goal", 5, 1, -70, 900),   # PIT shoots on WSH's goalie
    _goalie_shot("goal", 20, 1, -80, 900),
    _goalie_shot("missed-shot", 40, 2, 60, 800),     # WSH shoots on PIT's goalie
    _goalie_shot("goal", 50, 2, 60, None),           # into an empty net: no goalie charged
]}


def test_goalie_totals_charge_each_goalie_his_shots_against():
    each = xm.predict(xm.shots_from_game(GOALIE_PBP)[0], MODEL)
    by_goalie = {g["goalie"]: g for g in ix.goalie_totals(GOALIE_PBP, MODEL)}
    assert by_goalie[900] == {"goalie": 900, "team": "WSH", "xg_against": round(2 * each, 3), "goals_against": 1, "shots_against": 2}
    assert (by_goalie[800]["team"], by_goalie[800]["goals_against"], by_goalie[800]["shots_against"]) == ("PIT", 0, 1)


def test_new_games_store_their_goalies():
    cur = FakeCursor()
    ix.store_goalies(cur, 2026020005, 20262027, 2, GOALIE_PBP, MODEL)
    assert sorted((p[1], p[2], p[6]) for p in cur.inserted) == [(800, "PIT", 0), (900, "WSH", 1)]


def test_games_stored_before_goalie_xg_get_filled_in():
    cur = FakeCursor(missing_goalies=[2026020005])
    assert ix.fill_goalies(cur, 20262027, get=lambda url: GOALIE_PBP, model=MODEL) == 1
    assert len(cur.inserted) == 2


def test_a_past_season_backfills_from_cached_play_by_play(tmp_path):
    import gzip
    import json
    (tmp_path / "20252026").mkdir()
    for game_id, game_type in ((2025020001, 2), (2025030001, 3)):
        with gzip.open(tmp_path / "20252026" / f"{game_id}.json.gz", "wt") as f:
            json.dump({**GOALIE_PBP, "id": game_id, "gameType": game_type}, f)
    cur = FakeCursor()
    assert ix.backfill_goalies_from_cache(cur, 20252026, str(tmp_path), model=MODEL) == 1  # the playoff game is skipped
    assert {p[0] for p in cur.inserted} == {2025020001} and all(p[3] == 20252026 for p in cur.inserted)


class TestGoalieSeason:
    ROWS = [{"playerId": 900, "goalieFullName": "Logan Thompson", "teamAbbrevs": "WSH", "gamesPlayed": 50, "timeOnIce": 3600 * 48}]

    def _patch(self, monkeypatch, games):
        import player_values as pv
        monkeypatch.setattr(pv, "fetch_nhl_team_goals", lambda year: {"AAA": (0, games), "BBB": (0, games)})
        monkeypatch.setattr(pv, "fetch_nhl_goalies", lambda year: self.ROWS)
        monkeypatch.setattr(pv, "fetch_csv", lambda url, year: "moneypuck")
        monkeypatch.setattr(pv, "season_goalies", lambda text: {"from": text})

    def test_ours_when_every_game_is_stored(self, monkeypatch):
        self._patch(monkeypatch, games=82)
        season = sim.goalie_season(2025, faced={"games": 82, "goalies": {900: (130.0, 120)}})
        assert season == {900: {"name": "Logan Thompson", "team": "WSH", "gp": 50, "games": 48.0, "gsax": 10.0}}

    def test_moneypucks_when_games_are_missing(self, monkeypatch):
        self._patch(monkeypatch, games=82)
        assert sim.goalie_season(2025, faced={"games": 70, "goalies": {900: (130.0, 120)}}) == {"from": "moneypuck"}
        assert sim.goalie_season(2025, faced=None) == {"from": "moneypuck"}
