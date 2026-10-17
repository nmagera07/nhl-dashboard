"""
The goal model: from each team's expected goals in a game to the chance of
every final score, and from there the moneyline, puck line, and total.

How a game is scored, step by step:
  1. Regulation goals, not counting empty-netters, from each team's
     expected goals (team offense and defense). Real scores are a little
     less random than Poisson (variance about 0.9 of the mean once team
     strength is known) and the two teams' goals rise and fall slightly
     together (open games are open at both ends). Both make margins
     tighter, which matters for the puck line, so each team's goals are
     Conway-Maxwell-Poisson (a Poisson with a dispersion knob) plus a small
     shared Poisson part.
  2. Empty-netters: late, the trailing team pulls its goalie, and the
     leader often scores into the empty net (0.56 a game when up one).
     That turns a lot of one-goal wins into two-goal wins, which is what
     the puck line (-1.5) is about, so it's modeled from how often it
     actually happens, by the size of the lead.
  3. A tie after regulation goes to overtime/shootout: the winner gets one
     goal (the NHL's and the sportsbooks' final score).

Plain Python (no numpy) so the API and the daily job can use it.
"""

import math

MAX_GOALS = 12  # per team in regulation; more is vanishingly rare
# Fit on 2023-26 (5,248 games' play-by-play) by `backtest_goal_model.py --fit`.
# Empty-net goals the leader adds, per game, by its lead in non-empty-net
# goals (0 = tied, where one decides it in regulation; 3 is "3 or more").
EN_GOALS = (0.049, 0.56, 0.687, 0.172)
OT_HOME = 0.525  # home share of overtime/shootout wins (and of tie-breaking empty-netters)
DISPERSION = 1.145   # Conway-Maxwell-Poisson nu: 1 is Poisson, above 1 is less random
SHARED_GOALS = 0.154  # expected goals of the shared part (the two teams' covariance)
# Hockey ties more than independent scoring predicts (score effects: the
# leader sits back, the trailer pushes, late 6-on-5 goals): the regulation
# score's chance is weighted by its margin (tied, by one; wider is 1), fit
# so tied and one-goal regulation games happen as often as they really do.
MARGIN_WEIGHTS = (1.367, 1.09)
# Expected non-EN regulation goals: exp(home or away + offense * log(team's
# offense / league) + defense * log(opponent's defense / league) + own
# back-to-back + opponent's back-to-back). Ratings are goals per game, half
# goals and half xG, shrunk toward last season with 40 pseudo-games.
TEAM_COEFFICIENTS = {"home": 1.0653, "away": 1.0034, "offense": 0.8019, "defense": 0.9336,
                     "own_b2b": -0.0602, "opp_b2b": 0.0252}
# Team ratings predict the margin well but pace (the total) only weakly:
# out of sample, the real total moves 0.43 goals per goal the ratings
# predict, so the total is pulled that far toward the league's.
LEAGUE_TOTAL = 5.59
TOTAL_SHRINK = 0.432


def poisson(lam, top=MAX_GOALS):
    """P(0..top goals) for a Poisson mean."""
    probs = [math.exp(-lam)]
    for k in range(1, top + 1):
        probs.append(probs[-1] * lam / k)
    return probs


def com_poisson(mean, nu=DISPERSION, top=MAX_GOALS):
    """
    P(0..top goals) with the given mean: P(k) ~ rate^k / (k!)^nu, with the
    rate found by bisection so the mean comes out right. nu = 1 is Poisson.
    """
    if nu == 1:
        return poisson(mean, top)
    log_fact = [math.lgamma(k + 1) for k in range(top + 1)]

    def probs(log_rate):
        weights = [math.exp(k * log_rate - nu * log_fact[k]) for k in range(top + 1)]
        total = sum(weights)
        return [w / total for w in weights]

    low, high = -10.0, 10.0
    for _ in range(50):
        mid = (low + high) / 2
        if sum(k * p for k, p in enumerate(probs(mid))) < mean:
            low = mid
        else:
            high = mid
    return probs((low + high) / 2)


def adjusted_goals(home_goals, away_goals, league_total, total_shrink=TOTAL_SHRINK, margin_scale=1.0):
    """Each team's expected regulation goals with the total pulled toward the league's."""
    total = league_total + total_shrink * (home_goals + away_goals - league_total)
    margin = margin_scale * (home_goals - away_goals)
    return max((total + margin) / 2, 0.05), max((total - margin) / 2, 0.05)


def regulation_scores(home_goals, away_goals, nu=DISPERSION, shared=SHARED_GOALS, weights=MARGIN_WEIGHTS):
    """{(home, away): probability} of regulation goals, not counting empty-netters."""
    shared = min(shared, 0.5 * min(home_goals, away_goals))
    ph, pa = com_poisson(home_goals - shared, nu), com_poisson(away_goals - shared, nu)
    both = poisson(shared, 4)
    out = {}
    for h, p_h in enumerate(ph):
        for a, p_a in enumerate(pa):
            for s, p_s in enumerate(both):
                key = (h + s, a + s)
                out[key] = out.get(key, 0.0) + p_h * p_a * p_s
    for (h, a) in out:
        if abs(h - a) < len(weights):
            out[(h, a)] *= weights[abs(h - a)]
    total = sum(out.values())
    return {score: p / total for score, p in out.items()}


def final_scores(home_goals, away_goals, en_goals=EN_GOALS, ot_home=OT_HOME, nu=DISPERSION, shared=SHARED_GOALS,
                 weights=MARGIN_WEIGHTS):
    """
    {(home, away): probability} of each final score, from each team's
    expected regulation goals not counting empty-netters.
    """
    out = {}

    def add(score, p):
        out[score] = out.get(score, 0.0) + p

    en = [poisson(m, 3) for m in en_goals]
    for (h, a), p in regulation_scores(home_goals, away_goals, nu, shared, weights).items():
        lead = abs(h - a)
        for extra, p_en in enumerate(en[min(lead, 3)]):
            q = p * p_en
            if lead == 0 and extra == 0:  # overtime or a shootout: one goal to the winner
                add((h + 1, a), q * ot_home)
                add((h, a + 1), q * (1 - ot_home))
            elif lead == 0:  # an empty-netter breaks the tie late (rare)
                add((h + extra, a), q * ot_home)
                add((h, a + extra), q * (1 - ot_home))
            else:
                add((h + extra, a) if h > a else (h, a + extra), q)
    total = sum(out.values())  # the truncated tails (12+ goals, 4+ empty-netters) leak a little
    return {score: p / total for score, p in out.items()}


def home_win(scores):
    return sum(p for (h, a), p in scores.items() if h > a)


def home_covers(scores, spread):
    """P(home wins the puck line): home_spread -1.5 means home must win by 2+."""
    return sum(p for (h, a), p in scores.items() if h + spread > a)


def over(scores, total):
    """P(the final total goes over the line), e.g. total 6.5."""
    return sum(p for (h, a), p in scores.items() if h + a > total)


def expected_total(home, away, league, home_b2b=False, away_b2b=False, c=TEAM_COEFFICIENTS):
    """
    The game's expected non-EN regulation goals, both teams, shrunk toward
    the league's. home/away: {"offense", "defense"} goals per game (scored,
    allowed); league: the league's goals per team-game on the same scale.
    """
    def goals(side, team, opponent, own_b2b, opp_b2b):
        return math.exp(c[side] + c["offense"] * math.log(team["offense"] / league)
                        + c["defense"] * math.log(opponent["defense"] / league)
                        + c["own_b2b"] * own_b2b + c["opp_b2b"] * opp_b2b)

    raw = goals("home", home, away, home_b2b, away_b2b) + goals("away", away, home, away_b2b, home_b2b)
    return LEAGUE_TOTAL + TOTAL_SHRINK * (raw - LEAGUE_TOTAL)


def split_for_win_prob(total, home_win_prob, tolerance=1e-4):
    """
    (home goals, away goals) adding up to total whose final scores give the
    home team home_win_prob, so the moneyline, puck line, and total all come
    from one distribution that agrees with the win model.
    """
    low, high = -total + 0.1, total - 0.1
    for _ in range(40):
        margin = (low + high) / 2
        p = home_win(final_scores((total + margin) / 2, (total - margin) / 2))
        if abs(p - home_win_prob) < tolerance:
            break
        low, high = (margin, high) if p < home_win_prob else (low, margin)
    return round((total + margin) / 2, 3), round((total - margin) / 2, 3)


def bet_probabilities(home_goals, away_goals, home_spread=-1.5, total_line=6.5):
    """The no-margin chances for one game's bets, from its expected goals."""
    scores = final_scores(home_goals, away_goals)
    return {"home_win": round(home_win(scores), 4), "home_covers": round(home_covers(scores, home_spread), 4),
            "over": round(over(scores, total_line), 4)}
