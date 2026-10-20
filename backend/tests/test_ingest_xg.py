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
        return self.missing_goalies if "LEFT JOIN team_game_5v5" in self.sql[-1] else self.stored


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

    assert added == 1 and len(cur.inserted) == 2 + 2  # game 2, both teams: xG and 5-on-5 rows (no shift chart here)
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
    assert by_goalie[900] == {"goalie": 900, "team": "WSH", "xg_against": round(2 * each, 3), "goals_against": 1, "shots_against": 2,
                              "hd_shots": 0, "hd_goals": 0, "hd_xg": 0.0}  # each shot ~0.119: under the 0.20 line
    assert (by_goalie[800]["team"], by_goalie[800]["goals_against"], by_goalie[800]["shots_against"]) == ("PIT", 0, 1)


def test_new_games_store_their_goalies():
    cur = FakeCursor()
    ix.store_goalies(cur, 2026020005, 20262027, 2, GOALIE_PBP, MODEL)
    assert sorted((p[1], p[2], p[6]) for p in cur.inserted) == [(800, "PIT", 0), (900, "WSH", 1)]


def _shift(pid, team, period, start, end):
    return {"playerId": pid, "teamId": team, "period": period, "startTime": start, "endTime": end}


ROSTER = [{"playerId": p, "teamId": t, "positionCode": pos} for p, t, pos in
          ((11, 1, "C"), (12, 1, "D"), (21, 2, "C"), (22, 2, "D"), (800, 1, "G"), (900, 2, "G"))]
SHIFTS = [_shift(11, 1, 1, "00:00", "00:30"), _shift(12, 1, 1, "00:20", "01:00"),   # 11 off at 0:30, 12 on at 0:20
          _shift(21, 2, 1, "00:00", "01:00"), _shift(22, 2, 1, "00:50", "01:00"),
          _shift(800, 1, 1, "00:00", "20:00")] * 50  # padded past MIN_SHIFTS; duplicates change nothing


def test_team_5v5_counts_attempts_including_blocks_for_the_shooter():
    blocked = {"typeDescKey": "blocked-shot", "timeInPeriod": "00:30", "situationCode": "1551",
               "periodDescriptor": {"number": 1, "periodType": "REG"},
               "details": {"eventOwnerTeamId": 2, "shootingPlayerId": 11, "blockingPlayerId": 21}}
    pp_goal = {**_goalie_shot("goal", 45, 1, -80, 900), "situationCode": "1541"}  # a power play: not 5-on-5
    pbp = {**GOALIE_PBP, "rosterSpots": ROSTER, "plays": GOALIE_PBP["plays"] + [blocked, pp_goal]}
    pit, wsh = (ix.team_5v5(pbp, MODEL)[t] for t in ("PIT", "WSH"))
    assert (pit["cf"], pit["ff"], pit["sf"], pit["gf"]) == (3, 2, 2, 1)     # the block counts as PIT's attempt
    assert (pit["ca"], pit["fa"], pit["ga"]) == (2, 2, 1) and wsh["cf"] == 2
    each = xm.predict(xm.shots_from_game(GOALIE_PBP)[0], MODEL)
    assert pit["xgf"] == round(2 * each, 3)


def test_player_5v5_credits_whoever_was_on_the_ice():
    pbp = {**GOALIE_PBP, "rosterSpots": ROSTER}
    rows = ix.player_5v5(pbp, SHIFTS, MODEL)
    each = xm.predict(xm.shots_from_game(GOALIE_PBP)[0], MODEL)
    # PIT shoots at 0:05 and 0:20: 11 is on; 12's shift starts at 0:20, so not yet. WSH shoots at 0:40
    # and 0:50: 12 and 21 are on; 22's shift starts at 0:50, so not yet.
    assert rows[11]["onice_xgf"] == round(2 * each, 3) and rows[11]["onice_xga"] == 0
    assert rows[12]["onice_xgf"] == 0 and rows[12]["onice_xga"] == round(2 * each, 3)
    assert rows[21]["onice_xgf"] == round(2 * each, 3) and rows[21]["ixg"] == 0  # shooters here are team-only ids
    assert 22 not in rows and 800 not in rows  # 22 never on for a shot; goalies aren't skaters


def test_without_a_shift_chart_teams_and_own_xg_are_stored_but_not_on_ice_xg():
    pbp = {**GOALIE_PBP, "rosterSpots": ROSTER,
           "plays": [{**p, "details": {**p["details"], "shootingPlayerId": 11}} if p["details"]["eventOwnerTeamId"] == 1 else p
                     for p in GOALIE_PBP["plays"]]}
    cur = FakeCursor()
    assert not ix.store_5v5(cur, 2026020005, 20262027, 2, pbp, SHIFTS[:5], MODEL)
    teams = [p for p in cur.inserted if len(p) == 15]
    players = [p for p in cur.inserted if len(p) == 8]
    assert len(teams) == 2 and all(p[-1] is False for p in teams)
    assert players == [(2026020005, 11, "PIT", 20262027, 2, round(2 * xm.predict(xm.shots_from_game(pbp)[0], MODEL), 3), None, None)]
    cur = FakeCursor()
    assert ix.store_5v5(cur, 2026020005, 20262027, 2, pbp, SHIFTS, MODEL)
    assert len(cur.inserted) == 2 + 3  # two teams, three skaters with on-ice xG


def test_stored_games_without_5v5_rows_get_filled_in():
    cur = FakeCursor(missing_goalies=[2026020005])
    pbp = {**GOALIE_PBP, "rosterSpots": ROSTER}
    get = lambda url: {"data": SHIFTS} if "shiftcharts" in url else pbp  # noqa: E731
    assert ix.fill_5v5(cur, 20262027, get=get, model=MODEL) == 1
    assert len(cur.inserted) == 2 + 2 + 3  # goalies, teams, skaters
    waiting = FakeCursor(missing_goalies=[2026020005])
    assert ix.fill_5v5(waiting, 20262027, get=lambda url: {"data": []} if "shiftcharts" in url else pbp, model=MODEL) == 0
    assert len(waiting.inserted) == 2 + 2  # goalies and teams still stored (no shooters in this fixture)


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
