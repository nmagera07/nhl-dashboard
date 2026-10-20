"""
PuckPulse expected goals (xG): the chance an unblocked shot becomes a goal,
from the NHL's own play-by-play. Our replacement for MoneyPuck's xG, and the
first step toward our own WAR (which needs shot quality for every shift).

What counts: unblocked shot attempts (shots on goal, misses, goals), the
standard "Fenwick" set; a blocked shot's coordinates are where it was
blocked, not where it was taken. Shootouts and penalty shots are left out.

Features for each shot:
  - distance and angle to the net being attacked (x = +/-89 ft)
  - shot type (wrist, slap, snap, backhand, tip-in, deflected, wrap-around)
  - rebound: the same team had a shot attempt within 3 seconds before
  - rush: the play was in the other two zones within 4 seconds before
  - seconds since the last event, and how far the puck moved since
  - strength: even, power play, shorthanded, or shooting at an empty net
  - score state from the shooter's side (leading, tied, trailing)

The model is a logistic regression, trained offline by train_xg.py (numpy)
and saved as plain coefficients in xg_model.json, so scoring a shot here is
plain Python. Grade it against MoneyPuck's shot-level xG with
train_xg.py --compare.
"""

import json
import math
import os

NET_X = 89.0
REBOUND_SECONDS = 3
RUSH_SECONDS = 4
SHOT_EVENTS = {"shot-on-goal", "missed-shot", "goal"}
ATTEMPT_EVENTS = SHOT_EVENTS | {"blocked-shot"}
SHOT_TYPES = ("wrist", "snap", "slap", "backhand", "tip-in", "deflected", "wrap-around")
MODEL_PATH = os.path.join(os.path.dirname(__file__), "xg_model.json")


def _clock(text):
    minutes, seconds = (text or "0:0").split(":")
    return int(minutes) * 60 + int(seconds)


def strength(situation_code, shooter_is_home):
    """'EN' (opponent's net empty), 'PP', 'SH' or 'EV' from the NHL's
    situationCode: away goalie, away skaters, home skaters, home goalie."""
    code = str(situation_code or "1551").zfill(4)
    away_goalie, away_skaters, home_skaters, home_goalie = (int(c) for c in code)
    own, opp = (home_skaters, away_skaters) if shooter_is_home else (away_skaters, home_skaters)
    opp_goalie = away_goalie if shooter_is_home else home_goalie
    if not opp_goalie:
        return "EN"
    if own > opp:
        return "PP"
    if own < opp:
        return "SH"
    return "EV"


def shots_from_game(pbp):
    """
    [{features..., "goal": 0/1, ids...}] for every unblocked shot in one
    game's play-by-play (api-web.nhle.com/v1/gamecenter/{id}/play-by-play).
    """
    home_id = pbp["homeTeam"]["id"]
    shots = []
    score = {True: 0, False: 0}  # is_home -> goals
    prev = None
    for play in pbp.get("plays", []):
        period = (play.get("periodDescriptor") or {})
        if period.get("periodType") == "SO":
            break
        kind = play.get("typeDescKey")
        d = play.get("details") or {}
        t = _clock(play.get("timeInPeriod"))
        number = period.get("number", 1)
        team = d.get("eventOwnerTeamId")
        is_home = team == home_id
        if kind in SHOT_EVENTS and d.get("xCoord") is not None and d.get("yCoord") is not None:
            # Which net is this team attacking? homeTeamDefendingSide is per play.
            home_defends_left = play.get("homeTeamDefendingSide") == "left"
            attacks_right = home_defends_left if is_home else not home_defends_left
            net_x = NET_X if attacks_right else -NET_X
            x, y = float(d["xCoord"]), float(d["yCoord"])
            # Signed: positive in front of the goal line, negative behind the
            # net (where a "close" shot almost never goes in). The angle then
            # runs 0 (straight on) to 180 (directly behind the net).
            dx = (net_x - x) if attacks_right else (x - net_x)
            distance = math.hypot(dx, y)
            angle = math.degrees(math.atan2(abs(y), dx)) if dx or y else 0.0
            same_period_prev = prev if prev and prev["period"] == number else None
            prev_kind = same_period_prev["kind"] if same_period_prev else None
            prev_same_team = bool(same_period_prev and same_period_prev["team"] == team)
            since = (t - same_period_prev["t"]) if same_period_prev else 99
            moved = (math.hypot(x - same_period_prev["x"], y - same_period_prev["y"])
                     if same_period_prev and same_period_prev["x"] is not None else 0.0)
            rebound = bool(same_period_prev and same_period_prev["kind"] in ATTEMPT_EVENTS
                           and same_period_prev["team"] == team and since <= REBOUND_SECONDS)
            # zoneCode is from the event owner's side: our "O" is their "D".
            rush = bool(same_period_prev and since <= RUSH_SECONDS and (
                (same_period_prev["team"] == team and same_period_prev["zone"] in ("N", "D"))
                or (same_period_prev["team"] != team and same_period_prev["zone"] in ("N", "O"))))
            lead = score[is_home] - score[not is_home]
            # Rebounds: how far the angle swung from the first shot (the goalie
            # has to move across), measured to the same net.
            angle_change = 0.0
            if rebound and same_period_prev["x"] is not None:
                px, py = float(same_period_prev["x"]), float(same_period_prev["y"])
                pdx = (net_x - px) if attacks_right else (px - net_x)
                prev_angle = math.degrees(math.atan2(py, pdx)) if pdx or py else 0.0
                angle_change = abs(math.degrees(math.atan2(y, dx)) - prev_angle) if dx or y else 0.0
            shots.append({
                "game_id": pbp.get("id"), "period": number, "time": t,
                "shooter": d.get("shootingPlayerId") or d.get("scoringPlayerId"), "team_is_home": is_home,
                "goalie": d.get("goalieInNetId"),  # None into an empty net
                "distance": distance, "angle": angle,
                "shot_type": d.get("shotType") or "wrist",
                "rebound": rebound, "rush": rush,
                "since_last": min(since, 99), "moved": moved, "angle_change": min(angle_change, 180.0),
                "prev_kind": prev_kind, "prev_same_team": prev_same_team,
                "strength": strength(play.get("situationCode"), is_home),
                "lead": max(-3, min(3, lead)),
                "goal": 1 if kind == "goal" else 0,
            })
        if kind == "goal":
            score[is_home] += 1
        if kind not in ("stoppage", "period-start", "period-end", "game-end", "delayed-penalty"):
            prev = {"kind": kind, "team": team, "t": t, "period": number, "zone": d.get("zoneCode"),
                    "x": d.get("xCoord"), "y": d.get("yCoord")}
    return shots


DISTANCE_KNOTS = (5, 10, 15, 20, 30, 40, 55, 70)
ANGLE_KNOTS = (20, 35, 50, 70, 90)
TURNOVERS = ("giveaway", "takeaway")


def _hinges(value, knots, scale):
    return [max(0.0, value - k) / scale for k in knots]


def feature_vector(shot):
    """The model's inputs, in FEATURE_NAMES order (intercept first)."""
    distance = shot["distance"]
    angle = shot["angle"]
    s = shot["strength"]
    t = shot["shot_type"]
    lead = shot["lead"]
    empty = s == "EN"
    since = max(shot["since_last"], 1)
    prev = shot.get("prev_kind")
    same = shot.get("prev_same_team")
    return [
        1.0,
        # Distance and angle as flexible curves (piecewise linear), for shots on a goalie.
        *([0.0] * (2 + len(DISTANCE_KNOTS)) if empty else
          [distance / 10, math.log1p(distance), *_hinges(distance, DISTANCE_KNOTS, 10)]),
        *([0.0] * (1 + len(ANGLE_KNOTS)) if empty else [angle / 10, *_hinges(angle, ANGLE_KNOTS, 10)]),
        1.0 if angle > 90 else 0.0,
        *(1.0 if t == kind else 0.0 for kind in SHOT_TYPES[1:]),  # wrist is the baseline
        1.0 if t in ("tip-in", "deflected") and distance < 15 else 0.0,
        1.0 if shot["rebound"] else 0.0,
        shot.get("angle_change", 0.0) / 10,
        1.0 if shot["rush"] else 0.0,
        math.log1p(shot["since_last"]),
        min(shot["moved"] / since, 50) / 10,
        1.0 if prev == "faceoff" else 0.0,
        1.0 if prev in TURNOVERS else 0.0,
        1.0 if prev == "hit" else 0.0,
        1.0 if prev in ATTEMPT_EVENTS and not same else 0.0,
        1.0 if s == "PP" else 0.0, 1.0 if s == "SH" else 0.0,
        # Empty net: its own intercept and distance slope.
        1.0 if empty else 0.0, math.log1p(distance) if empty else 0.0,
        1.0 if lead > 0 else 0.0, 1.0 if lead < 0 else 0.0,
        1.0 if shot["team_is_home"] else 0.0,
    ]


FEATURE_NAMES = (
    ["intercept", "distance_per_10ft", "log_distance"] + [f"distance_past_{k}ft" for k in DISTANCE_KNOTS]
    + ["angle_per_10deg"] + [f"angle_past_{k}deg" for k in ANGLE_KNOTS] + ["behind_net"]
    + [f"type_{kind}" for kind in SHOT_TYPES[1:]]
    + ["tip_or_deflection_in_close", "rebound", "rebound_angle_change_per_10deg", "rush", "log_seconds_since_last",
       "puck_speed_ft_per_s_per_10", "after_faceoff", "after_turnover", "after_hit", "after_opponent_shot",
       "power_play", "shorthanded", "empty_net", "empty_net_log_distance", "leading", "trailing", "home"]
)


def load_model(path=MODEL_PATH):
    with open(path) as f:
        return json.load(f)


def predict(shot, model):
    """xG for one shot (0-1) from saved coefficients."""
    z = sum(c * v for c, v in zip(model["coefficients"], feature_vector(shot)))
    return 1 / (1 + math.exp(-z)) if z > -700 else 0.0
