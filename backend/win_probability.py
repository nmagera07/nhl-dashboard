"""
In-game win probability: each team's chance to win from any moment of a
game, for the game page's chart.

It starts from the pregame expectation (each team's expected regulation
goals, the goal model's inputs, tuned so the chart starts exactly at the
pregame win probability) and plays out the time left:

  1. The rest of regulation, in two windows. First, goals at each team's
     pregame rate scaled to the time left, nudged for score effects (the
     trailing team presses, the leader sits back) and any power play.
  2. Then the last PULL_SECONDS: a team down one or two pulls its goalie,
     so it scores at PULL_GOALS_PER_HOUR and the leader into the empty net
     at EMPTY_NET_GOALS_PER_HOUR (an empty-netter all but ends it).
  3. A tie after regulation: 3-on-3 overtime (sudden death, five minutes,
     OT_GOAL_RATE), then a shootout; in the playoffs, sudden death until
     someone scores.

Goals in each window are Poisson, independent for the two teams. The
constants are fit on 2023-26 play-by-play by backtest_win_probability.py,
which also checks the result is calibrated at every point of a game.
"""

import math

REGULATION_SECONDS = 3600
OT_SECONDS = 300

# Fit by backtest_win_probability.py --fit (2023-24 to 2025-26). Trailing teams
# outshoot leaders, but goals don't follow: any score effect made it worse.
SCORE_EFFECT = 0.0             # trailing team's rate x (1 + this); the leader's x (1 - this)
PULL_SECONDS = 90              # when a team down one or two pulls its goalie
PULL_GOALS_PER_HOUR = 10.0     # the trailing team's scoring at 6-on-5
EMPTY_NET_GOALS_PER_HOUR = 20.0  # the leader's, into the empty net
PP_GOALS_PER_HOUR = 6.3        # a team on a 5-on-4
SH_GOALS_PER_HOUR = 0.6        # the team killing it
# 2024-25: 72% of regular-season overtimes ended with a goal; home won 54% of OT and 53% of shootout decisions.
OT_GOAL_RATE = -math.log(1 - 0.716) / OT_SECONDS
OT_HOME_EDGE = 0.025
SHOOTOUT_HOME = 0.532
MAX_WINDOW_GOALS = 12


def _poisson(lam, top=MAX_WINDOW_GOALS):
    lam = max(lam, 0.0)
    probs = [math.exp(-lam)]
    for k in range(1, top + 1):
        probs.append(probs[-1] * lam / k)
    return probs


def _overtime_share(home_mu, away_mu):
    """The home team's chance to score first at 3-on-3 (or in a playoff overtime)."""
    return min(max(home_mu / (home_mu + away_mu) + OT_HOME_EDGE, 0.05), 0.95)


def _tied_after_regulation(home_mu, away_mu, playoff, ot_seconds=OT_SECONDS):
    """P(home wins) from a tie at the end of regulation (or at a point in overtime)."""
    share = _overtime_share(home_mu, away_mu)
    if playoff:
        return share
    goal = 1 - math.exp(-OT_GOAL_RATE * ot_seconds)
    return goal * share + (1 - goal) * SHOOTOUT_HOME


def _window(lead, home_rate, away_rate):
    """{lead change: probability} for one window of goals at these expected counts."""
    out = {}
    for h, ph in enumerate(_poisson(home_rate)):
        for a, pa in enumerate(_poisson(away_rate)):
            out[h - a] = out.get(h - a, 0.0) + ph * pa
    return {lead + d: p for d, p in out.items()}


def home_win_prob(home_mu, away_mu, lead, seconds_left, *, in_overtime=False, playoff=False,
                  pp_home_seconds=0, pp_away_seconds=0):
    """
    P(home wins) with the home team `lead` goals up (negative if behind)
    and `seconds_left` in regulation (or in overtime, with in_overtime).
    home_mu / away_mu: each team's expected goals over a full regulation
    game. pp_*_seconds: power-play time left for that team right now.
    """
    if in_overtime:
        if lead != 0:
            return 1.0 if lead > 0 else 0.0
        return _tied_after_regulation(home_mu, away_mu, playoff, seconds_left)
    if seconds_left <= 0:
        return 1.0 if lead > 0 else 0.0 if lead < 0 else _tied_after_regulation(home_mu, away_mu, playoff)

    tie = _tied_after_regulation(home_mu, away_mu, playoff)
    pull = min(seconds_left, PULL_SECONDS)
    main = seconds_left - pull
    per_sec_h, per_sec_a = home_mu / REGULATION_SECONDS, away_mu / REGULATION_SECONDS

    # Window 1: the time before a goalie would be pulled.
    if main > 0:
        push = SCORE_EFFECT * (1 if lead < 0 else -1 if lead > 0 else 0)
        rate_h = per_sec_h * (1 + push) * main
        rate_a = per_sec_a * (1 - push) * main
        pp_h, pp_a = min(pp_home_seconds, main), min(pp_away_seconds, main)
        rate_h += (PP_GOALS_PER_HOUR / 3600 - per_sec_h) * pp_h + (SH_GOALS_PER_HOUR / 3600 - per_sec_h) * pp_a
        rate_a += (PP_GOALS_PER_HOUR / 3600 - per_sec_a) * pp_a + (SH_GOALS_PER_HOUR / 3600 - per_sec_a) * pp_h
        leads = _window(lead, max(rate_h, 0.0), max(rate_a, 0.0))
    else:
        leads = {lead: 1.0}

    # Window 2: the last `pull` seconds, with the goalie pulled when it's a one- or two-goal game.
    win = 0.0
    for current, p in leads.items():
        if p < 1e-12:
            continue
        if 1 <= abs(current) <= 2:
            trailer, leader = PULL_GOALS_PER_HOUR / 3600 * pull, EMPTY_NET_GOALS_PER_HOUR / 3600 * pull
            rate_h, rate_a = (leader, trailer) if current > 0 else (trailer, leader)
        else:
            rate_h, rate_a = per_sec_h * pull, per_sec_a * pull
        for final, q in _window(current, rate_h, rate_a).items():
            win += p * q * (1.0 if final > 0 else tie if final == 0 else 0.0)
    return min(max(win, 0.0), 1.0)


def anchor(home_mu, away_mu, pregame_prob, playoff=False):
    """
    Each team's expected goals, shifted (total kept) so the model at puck
    drop gives exactly the pregame win probability.
    """
    lo, hi = -2.0, 2.0
    for _ in range(40):
        mid = (lo + hi) / 2
        p = home_win_prob(home_mu * math.exp(mid), away_mu * math.exp(-mid), 0, REGULATION_SECONDS, playoff=playoff)
        lo, hi = (mid, hi) if p < pregame_prob else (lo, mid)
    shift = (lo + hi) / 2
    return home_mu * math.exp(shift), away_mu * math.exp(-shift)


# --- replaying a game ----------------------------------------------------------

PP_PENALTIES = {"MIN": 1, "BEN": 1, "MAJ": 0}  # typeCode -> 1 if a power-play goal ends it
SAMPLE_SECONDS = 30


def _clock(text):
    minutes, seconds = (text or "0:00").split(":")
    return int(minutes) * 60 + int(seconds)


def _elapsed(period, playoff):
    """Game seconds at the start of a period: 20-minute periods, then a 5-minute regular-season overtime."""
    number = period.get("number", 1)
    if number <= 3 or playoff:
        return (number - 1) * 1200
    return REGULATION_SECONDS + (number - 4) * OT_SECONDS


def series(pbp, home_mu, away_mu, playoff=None, at=None):
    """
    The game's win probability curve: {"points": [(game second, P(home))],
    "goals": [{second, team, scorer, before, after}]}, from puck drop to
    the latest event (the final horn for a finished game). With `at`
    (sorted game seconds), only those points, for the backtest.
    """
    playoff = pbp.get("gameType") == 3 if playoff is None else playoff
    home_id, away_id = pbp["homeTeam"]["id"], pbp["awayTeam"]["id"]
    names = {r["playerId"]: f"{r['firstName']['default'][0]}. {r['lastName']['default']}" for r in pbp.get("rosterSpots", [])}
    events = []
    for play in pbp.get("plays", []):
        period = play.get("periodDescriptor") or {}
        if period.get("periodType") == "SO" or play.get("timeInPeriod") is None:
            continue
        events.append((_elapsed(period, playoff) + _clock(play["timeInPeriod"]), period.get("periodType"), play))

    def prob(second, lead, penalties):
        overtime = second >= REGULATION_SECONDS
        if overtime:
            left = (1200 - (second - REGULATION_SECONDS) % 1200) if playoff else max(OT_SECONDS - (second - REGULATION_SECONDS), 0)
        else:
            left = REGULATION_SECONDS - second
        pp = {home_id: 0, away_id: 0}
        for team, end, _ in penalties:
            if end > second:  # a penalty on `team` gives the other one a power play
                other = away_id if team == home_id else home_id
                pp[other] = max(pp[other], end - second)
        return home_win_prob(home_mu, away_mu, lead, left, in_overtime=overtime, playoff=playoff,
                             pp_home_seconds=pp[home_id], pp_away_seconds=pp[away_id])

    points, goals, lead, penalties = [], [], 0, []
    samples = list(at) if at is not None else None
    sample = samples.pop(0) if samples else (None if at is not None else 0)
    last = events[-1][0] if events else 0
    for second, _, play in events + [(last, None, None)]:
        while sample is not None and sample < second:  # the curve between events
            points.append((sample, prob(sample, lead, penalties)))
            if at is None:
                sample += SAMPLE_SECONDS
            else:
                sample = samples.pop(0) if samples else None
        if play is None:
            break
        kind, d = play.get("typeDescKey"), play.get("details") or {}
        if kind == "penalty" and d.get("typeCode") in PP_PENALTIES and d.get("duration"):
            penalties.append((d.get("eventOwnerTeamId"), second + 60 * d["duration"], PP_PENALTIES[d["typeCode"]]))
        elif kind == "goal" and at is not None:  # the backtest only needs the score
            lead += 1 if d.get("eventOwnerTeamId") == home_id else -1
            shorthanded = [p for p in penalties if p[0] != d.get("eventOwnerTeamId") and p[1] > second and p[2]]
            if shorthanded:
                penalties.remove(min(shorthanded, key=lambda p: p[1]))
        elif kind == "goal":
            before = prob(second, lead, penalties)
            scorer_team = d.get("eventOwnerTeamId")
            lead += 1 if scorer_team == home_id else -1
            # A power-play goal ends the shorthanded team's earliest-ending minor.
            shorthanded = [p for p in penalties if p[0] != scorer_team and p[1] > second and p[2]]
            if shorthanded:
                penalties.remove(min(shorthanded, key=lambda p: p[1]))
            after = prob(second, lead, penalties)
            goals.append({"second": second, "team": "home" if scorer_team == home_id else "away",
                          "scorer": names.get(d.get("scoringPlayerId")), "before": round(before, 4), "after": round(after, 4)})
            points.append((second, before))
            points.append((second, after))
    if pbp.get("gameState") in ("OFF", "FINAL") and at is None:
        home_won = pbp["homeTeam"].get("score", 0) > pbp["awayTeam"].get("score", 0)
        points.append((max(last, sample or 0), 1.0 if home_won else 0.0))
    return {"points": [(s, round(p, 4)) for s, p in points], "goals": goals}


def biggest_swing(goals):
    """The goal that moved the home team's chances the most, or None."""
    return max(goals, key=lambda g: abs(g["after"] - g["before"]), default=None)
