"""rapm_stints: 5-on-5 stints from play-by-play and shift charts, and the cache download."""

import rapm_stints as rs
import xg_model as xm

MODEL = {"version": 1, "coefficients": [-2.0] + [0.0] * (len(xm.FEATURE_NAMES) - 1)}  # every shot ~0.119
HOME, AWAY = 1, 2


def _clock(t):
    return f"{t // 60:02d}:{t % 60:02d}"


def _shift(pid, team, start, end, period=1):
    return {"playerId": pid, "teamId": team, "period": period, "startTime": _clock(start), "endTime": _clock(end),
            "typeCode": 517}


def _play(kind, t, team, x=None, zone="O", situation="1551"):
    return {"typeDescKey": kind, "timeInPeriod": _clock(t), "situationCode": situation, "homeTeamDefendingSide": "right",
            "periodDescriptor": {"number": 1, "periodType": "REG"},
            "details": {"eventOwnerTeamId": team, "zoneCode": zone, "xCoord": x, "yCoord": 0}}


ROSTER = ([{"playerId": p, "teamId": HOME, "positionCode": "C"} for p in range(1, 7)]
          + [{"playerId": p, "teamId": AWAY, "positionCode": "C"} for p in range(21, 26)]
          + [{"playerId": 800, "teamId": HOME, "positionCode": "G"}, {"playerId": 900, "teamId": AWAY, "positionCode": "G"}])

# Home 1-5 start; 6 replaces 1 at 0:30. Away 21-25 play on, but 25 sits 1:00-1:10 (4 skaters: not 5-on-5).
SHIFTS = ([_shift(p, HOME, 0, 120) for p in (2, 3, 4, 5)] + [_shift(1, HOME, 0, 30), _shift(6, HOME, 30, 120)]
          + [_shift(p, AWAY, 0, 120) for p in (21, 22, 23, 24)] + [_shift(25, AWAY, 0, 60), _shift(25, AWAY, 70, 120)]
          + [_shift(800, HOME, 0, 1200), _shift(900, AWAY, 0, 1200)]
          + [{**_shift(1, HOME, 10, 10), "typeCode": 505}])  # a goal row in the chart, not a shift

PBP = {"id": 2025020001, "homeTeam": {"id": HOME, "abbrev": "PIT"}, "awayTeam": {"id": AWAY, "abbrev": "WSH"},
       "rosterSpots": ROSTER, "plays": [
           _play("faceoff", 0, HOME, zone="N"),
           _play("shot-on-goal", 10, HOME, -70),
           _play("goal", 30, AWAY, 70),            # at the change: the group that was out gets it
           _play("faceoff", 45, AWAY, zone="O"),   # WSH wins it in their offensive zone: PIT's D-zone
           _play("missed-shot", 50, HOME, -60),
           _play("shot-on-goal", 65, HOME, -60),   # 1551 by the code, but WSH has only 4 out: no stint
       ]}


def test_a_game_splits_at_each_change_and_faceoff():
    stints, unmatched = rs.stints(PBP, SHIFTS, MODEL)
    each = xm.predict(xm.shots_from_game(PBP)[0], MODEL)
    assert [(s["start"], s["end"], s["seconds"]) for s in stints] == [(0, 30, 30), (30, 45, 15), (45, 60, 15), (70, 120, 50)]
    first, second, third, last = stints
    assert first["home"] == [1, 2, 3, 4, 5] and first["away"] == [21, 22, 23, 24, 25]
    assert second["home"] == [2, 3, 4, 5, 6] == third["home"]  # same ten, but the draw starts a new stint
    assert [s["zone"] for s in stints] == ["N", None, "D", None]
    assert (first["home_shots"], first["away_goals"], first["away_xg"]) == (1, 1, round(each, 4))
    assert [s["score"] for s in stints] == [0, -1, -1, -1]  # home minus away at each start
    assert third["home_shots"] == 1 and unmatched == 1


def test_download_caches_finished_games_and_stops_after_the_last(tmp_path, monkeypatch):
    monkeypatch.setattr(rs, "CACHE", str(tmp_path))
    games = {2025020001: "OFF", 2025020002: "FUT"}  # game 3 on doesn't exist
    calls = []

    def get(url):
        calls.append(url)
        game_id = int(url.split("=")[-1] if "shiftcharts" in url else url.split("/")[-2])
        if "shiftcharts" in url:
            return {"data": [{}] * rs.MIN_SHIFTS}
        return {"gameState": games[game_id]} if game_id in games else None

    assert rs.download(20252026, get=get, pause=0) == {"pbp": 1, "shifts": 1}
    assert rs.load("pbp", 20252026, 2025020001) == {"gameState": "OFF"}
    assert rs.load("pbp", 20252026, 2025020002) is None  # not played yet: checked again next run
    assert sum("2025020005" in c for c in calls) == 1 and not any("2025020006" in c for c in calls)

    calls.clear()
    rs.download(20252026, get=get, pause=0)  # a re-run only asks for what's missing
    assert not any("2025020001" in c for c in calls)


def _toi_report(players):
    """A trimmed TH/TV report: a heading per player, his shift rows, then a per-period summary row."""
    html = []
    for number, shifts in players:
        html.append(f'<td align="center" valign="top" class="playerHeading + border" colspan="8">{number} LAST, FIRST</td>')
        for i, (period, start, end) in enumerate(shifts, 1):
            html.append(f'<tr class="oddColor"><td align="center" class="lborder + bborder">{i}</td>'
                        f'<td align="center" class="lborder + bborder">{period}</td>'
                        f'<td align="center" class="lborder + bborder">{start} / 19:00</td>'
                        f'<td align="center" class="lborder + bborder">{end} / 18:00</td>'
                        f'<td align="center" class="lborder + bborder">00:40</td></tr>')
        html.append('<tr><td align="center">1</td><td align="center">12</td><td align="center">00:51</td></tr>')
    return "\n".join(html)


def test_html_reports_stand_in_for_a_missing_shift_chart():
    pbp = {"id": 2026020090, "homeTeam": {"id": HOME}, "awayTeam": {"id": AWAY},
           "rosterSpots": [{"playerId": 87, "teamId": HOME, "sweaterNumber": 87},
                           {"playerId": 8, "teamId": AWAY, "sweaterNumber": 8}]}
    reports = {"TH": _toi_report([(87, [("1", "0:36", "1:16"), ("OT", "2:00", "2:45")]), (99, [("1", "0:00", "0:30")])]),
               "TV": _toi_report([(8, [("2", "10:05", "11:00")])])}
    urls = []

    def get_text(url):
        urls.append(url)
        return reports[url.split("/")[-1][:2]]

    rows = rs.html_shifts(pbp, get_text)
    assert urls[0] == "https://www.nhl.com/scores/htmlreports/20262027/TH020090.HTM"
    assert [(r["playerId"], r["teamId"], r["period"], r["startTime"], r["endTime"]) for r in rows] == [
        (87, HOME, 1, "0:36", "1:16"), (87, HOME, 4, "2:00", "2:45"),  # OT is period 4; #99 isn't on the roster
        (8, AWAY, 2, "10:05", "11:00")]
    assert rs.html_shifts(pbp, lambda url: None) is None
