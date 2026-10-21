"""
Playoff Odds Simulator (v2.5: goals + PuckPulse xG + roster rating + goalies)

Monte Carlo simulation of the rest of the regular season to estimate each
team's probability of making the playoffs.

How it works:
  1. Rate each team by a blend of goal differential and MoneyPuck expected-
     goals (xG) differential per game, shrunk toward a prior: half of last
     season's xG differential per game, weighted as PRIOR_GAMES_XG
     pseudo-games. Early in the season the prior dominates; by midseason
     this season's results take over. If MoneyPuck is unreachable, it falls
     back to goals only (prior = last season's GD/game, PRIOR_GAMES).
     v2.2 adds roster moves to the prior: the value of skaters who
     arrived minus those who left (player_values.py). v2.3 adds each
     team's goaltending (GSAx), which xG leaves out. v2.4 replaces last
     season's xG and the roster moves with a roster rating: the sum of the
     current players' values (a WAR-style team rating). v2.5 uses our own
     xG (xg_model.py, from NHL play-by-play) for this season, with
     MoneyPuck's as the fallback.
     v1 used raw point %, which after a 4-0 start rated a team as
     near-unbeatable.
  2. Pull the remaining regular-season schedule from the NHL API.
  3. Run N simulated seasons. In each one, draw every team's "true"
     strength around its rating (wider early in the season, when we know
     less), then play each remaining game: a logistic win probability with
     a home-ice edge, plus overtime (OT_PROBABILITY of games; the loser
     still gets a point) and shootouts (which don't count toward ROW).
  4. Pick that season's 16 playoff teams: top 3 per division, then 2
     wild cards per conference, ties broken by points, regulation wins
     (RW), regulation + OT wins (ROW), then wins.
  5. Playoff odds = fraction of simulated seasons a team made the 16.

HOME_EDGE, SCALE, OT_PROBABILITY, and SHOOTOUT_SHARE_OF_OT are fit from
3,936 real games (2023-24 to 2025-26) by calibrate_playoff_model.py.
PRIOR_GAMES and TALENT_SD were chosen by backtesting against past seasons
(backtest_playoff_odds.py).

Usage:
    python simulate_playoff_odds.py                       # live, today
    python simulate_playoff_odds.py --as-of 2026-02-01    # a past date
    python simulate_playoff_odds.py --no-save             # print only

Runs daily from run_daily_ingest.py (after standings). During the
offseason the NHL API returns no remaining games and every team's odds
collapse to its final result.
"""

import argparse
import math
import os
import random
import time
from collections import defaultdict
from datetime import date, timedelta

import psycopg2
import requests
from dotenv import load_dotenv

import lottery
from logging_config import setup_logging
from seasons import current_season_id, previous_season_id  # noqa: F401 (re-exported for the model scripts)

load_dotenv()

# Not required at import: the API imports this module for the scenario
# tools (season_scenarios.py) and only holds its read-only credential.
DATABASE_URL = os.getenv("DATABASE_URL")

logger = setup_logging("simulate_playoff_odds")
STANDINGS_URL = "https://api-web.nhle.com/v1/standings/{date}"
# MoneyPuck team season summaries (free for non-commercial use with credit,
# moneypuck.com/data.htm). "all" situations, regular season.
MONEYPUCK_TEAMS_URL = "https://moneypuck.com/moneypuck/playerData/seasonSummary/{year}/regular/teams.csv"
MONEYPUCK_HEADERS = {"User-Agent": "nhl-dashboard (personal, non-commercial; credits MoneyPuck.com)"}
SCHEDULE_URL = "https://api-web.nhle.com/v1/club-schedule-season/{team}/{season}"

MODEL_VERSION = "v2.6"       # logged with every game prediction (game_predictions.py)

# Game model -- fit by calibrate_playoff_model.py on 5,248 games (2022-23 to
# 2025-26). The second night of a back-to-back is part of the margin (v2.6):
# a tired road team is worth +0.53 goals/game to the home team, a tired home
# team -0.31. Without it, "home ice" (0.24) was partly road fatigue, since
# road teams play the second night about twice as often. Better log loss in
# all 4 seasons held out. Who starts in net added nothing measurable.
HOME_EDGE = 0.160            # goals/game of home-ice advantage
SCALE = 1.457                # logistic steepness, in goals/game
HOME_B2B = -0.306            # home team on the 2nd night of a back-to-back
AWAY_B2B = 0.530             # away team on the 2nd night (helps the home team)
OT_PROBABILITY = 0.223       # share of games reaching overtime
SHOOTOUT_SHARE_OF_OT = 0.319 # share of OT games decided in a shootout

# Team-strength model -- chosen by backtest_playoff_odds.py.
PRIOR_CARRYOVER = 0.5        # how much of last season's strength carries over
PRIOR_GAMES = 45             # weight of the prior, in games (goals-only fallback)
TALENT_SD = 0.35             # spread of true strength (GD/game) with no data

# xG blend (v2.1) -- backtested 2026-10 over 4 seasons with as-of game-by-game
# MoneyPuck xG: 3.7% better Brier overall, 7.6% better on Nov 1, and better
# on held-out seasons under leave-one-season-out (unlike strength of
# schedule). Strength input = half goal differential, half xG differential;
# prior = last season's xG differential per game.
XG_WEIGHT = 0.5
PRIOR_GAMES_XG = 30

# Roster-aware prior (v2.2) -- backtested 2026-10 over 4 seasons: last
# season's prior plus the goals/game each team gained or lost to roster
# moves since (player_values.roster_strength_change). 2.6% better Brier
# overall, 4.9% better on Nov 1, never worse at a checkpoint, better on 3
# of 4 held-out seasons. Weight 1.0 (player values at face value) scored
# best of 0 to 1.5.
ROSTER_WEIGHT = 1.0

# Roster rating (v2.4) -- backtested 2026-10: rating each team as the sum of
# its players (player_values.team_roster_strength: values from the last two
# seasons, weighted by expected games, 12 F / 6 D slots) beat "last
# season's xG + roster moves" in all 4 seasons (1.2% better Brier overall),
# and the best blend put zero weight on last season's team xG: once you
# know the players, the team's own history adds nothing. Weight 1.0
# (values at face value) and PRIOR_GAMES_XG unchanged; 1.25 tied, 1.5 was
# worse. Replaces the v2.2 roster-change term (ROSTER_WEIGHT above).
ROSTER_RATING_WEIGHT = 1.0

# PuckPulse xG (v2.5) -- backtested 2026-10 against MoneyPuck's xG in v2.4,
# each season scored by an xG model trained on the other three: Brier
# 0.1104 -> 0.1093, 16 of 20 checkpoints better, but a team-season
# bootstrap's 95% interval (-0.0032, +0.0010) includes zero. Switched for
# independence, at no measurable cost; MoneyPuck stays the fallback.

# Goaltending in the prior (v2.3) -- backtested 2026-10 like the roster
# prior. xG measures shots, not saves, so the xG prior had no goaltending
# in it at all: each team's current goalies' GSAx per 60 (shrunk hard, see
# player_values.goalie_rates), weighted by starts, is added in full. Adding
# only the *change* in goalies did nothing. 1.9% better Brier than v2.2,
# better than v2.1 in all 4 seasons and than v2.2 in 3 of 4.
GOALIE_WEIGHT = 1.0
GOALIE_LOOKUP_MIN_GP = 10   # last season's goalies worth a landing-page lookup if off the roster feed

DEFAULT_TRIALS = 10000


def nhl_get(url, retries=6):
    """GET with a polite retry: the NHL API rate-limits bursts (HTTP 429)."""
    for attempt in range(retries):
        response = requests.get(url, timeout=20)
        if response.status_code != 429:
            response.raise_for_status()
            return response.json()
        time.sleep(int(response.headers.get("Retry-After", 0)) or 5 * (attempt + 1))
    response.raise_for_status()


def home_margin(home_b2b=False, away_b2b=False, model=None):
    """
    The home team's built-in edge in goals/game: home ice plus the second
    night of a back-to-back for either side. `model` (a sim_inputs()
    "model" dict) supplies the constants it was saved with.
    """
    m = model or {}
    edge = m.get("home_edge", HOME_EDGE)
    return edge + (m.get("home_b2b", HOME_B2B) if home_b2b else 0.0) + (m.get("away_b2b", AWAY_B2B) if away_b2b else 0.0)


def win_probability(home_rating, away_rating, home_b2b=False, away_b2b=False):
    """P(home team wins), ratings in goals/game of strength."""
    x = (home_rating - away_rating + home_margin(home_b2b, away_b2b)) / SCALE
    if x < -700:  # avoid math.exp overflow on absurd inputs
        return 0.0
    return 1 / (1 + math.exp(-x))


def fetch_standings_as_of(as_of_date):
    standings = {}
    for team in nhl_get(STANDINGS_URL.format(date=as_of_date))["standings"]:
        standings[team["teamAbbrev"]["default"]] = {
            "points": team["points"],
            "games_played": team["gamesPlayed"],
            "wins": team["wins"],
            "losses": team.get("losses", 0),
            "ot_losses": team.get("otLosses", 0),
            "regulation_wins": team.get("regulationWins", 0),
            "row": team.get("regulationPlusOtWins", 0),
            "goal_differential": team.get("goalDifferential", 0),
            "division": team["divisionName"],
            "conference": team["conferenceName"],
        }
    return standings


def fetch_season_games(team_abbrevs, season_id):
    """
    Every regular-season game once, as dicts with date, home, away, and the
    final score (None until it's played).
    """
    seen = {}
    for team in team_abbrevs:
        for g in nhl_get(SCHEDULE_URL.format(team=team, season=season_id))["games"]:
            if g["gameType"] != 2:
                continue
            final = g.get("gameState") in ("OFF", "FINAL")
            seen[g["id"]] = {
                "date": g["gameDate"],
                "home": g["homeTeam"]["abbrev"],
                "away": g["awayTeam"]["abbrev"],
                "home_score": g["homeTeam"].get("score") if final else None,
                "away_score": g["awayTeam"].get("score") if final else None,
            }
        time.sleep(0.2)
    return mark_back_to_backs(list(seen.values()))


def mark_back_to_backs(games):
    """Adds home_b2b / away_b2b to each game: that team also plays (or
    played) the day before. Known from the schedule alone, so future
    games get it too."""
    days = defaultdict(set)
    for g in games:
        days[g["home"]].add(g["date"])
        days[g["away"]].add(g["date"])
    for g in games:
        yesterday = str(date.fromisoformat(g["date"]) - timedelta(days=1))
        g["home_b2b"] = yesterday in days[g["home"]]
        g["away_b2b"] = yesterday in days[g["away"]]
    return games


def split_games(games, as_of_date):
    """
    (completed games with scores up to the date, remaining (home, away,
    home_b2b, away_b2b) tuples). Standings for a date include that day's games once they're
    played, so a game on the as-of date is remaining until it has a final
    score -- the daily run happens before that day's games, and treating
    them as done dropped them from the simulation entirely.
    """
    remaining = [(g["home"], g["away"], g.get("home_b2b", False), g.get("away_b2b", False))
                 for g in remaining_games(games, as_of_date)]
    return [g for g in games if _is_played(g, as_of_date)], remaining


def _is_played(game, as_of_date):
    return game["date"] <= str(as_of_date) and game["home_score"] is not None


def remaining_games(games, as_of_date):
    """Games still to be played after the standings date, in date order."""
    as_of = str(as_of_date)
    left = [g for g in games if g["date"] > as_of or (g["date"] == as_of and g["home_score"] is None)]
    return sorted(left, key=lambda g: g["date"])


def fetch_moneypuck_xgd(start_year):
    """
    {team: (xG for - xG against total, games played)} for one season, all
    situations, from MoneyPuck. Raises on any network/parse problem so the
    caller can fall back to the goals-only model.
    """
    import csv
    import io

    response = requests.get(MONEYPUCK_TEAMS_URL.format(year=start_year), headers=MONEYPUCK_HEADERS, timeout=30)
    response.raise_for_status()
    out = {}
    for row in csv.DictReader(io.StringIO(response.text)):
        if row.get("situation") == "all":
            out[row["team"]] = (float(row["xGoalsFor"]) - float(row["xGoalsAgainst"]), int(float(row["games_played"])))
    if len(out) < 30:
        raise ValueError(f"MoneyPuck returned only {len(out)} teams for {start_year}")
    return out


def blend_xg(standings, xgd_totals, weight=XG_WEIGHT):
    """Standings with goal_differential replaced by a goals/xG blend, so
    team_ratings() shrinks the blend exactly like it shrinks raw GD. Teams
    missing from MoneyPuck keep their goal differential."""
    out = {}
    for team, row in standings.items():
        gd = row.get("goal_differential", 0)
        xgd = xgd_totals.get(team, (gd, None))[0]
        out[team] = {**row, "goal_differential": (1 - weight) * gd + weight * xgd}
    return out


def xg_model_inputs(season_id, fetch=fetch_moneypuck_xgd):
    """(this season's xG totals, last season's xG priors), or None if
    MoneyPuck is unavailable."""
    start = season_id // 10000
    try:
        current = fetch(start)
        previous = fetch(start - 1)
    except Exception as exc:  # network, HTTP, or parse -- fall back to goals only
        logger.warning(f"MoneyPuck xG unavailable ({exc}); using the goals-only model")
        return None
    priors = {t: PRIOR_CARRYOVER * xgd / gp for t, (xgd, gp) in previous.items() if gp}
    return current, priors


def puckpulse_xgd(season_id, standings, rows=None):
    """
    {team: (xG for - xG against total, games)} this season from our own xG
    (ingest_xg.py), in fetch_moneypuck_xgd()'s shape, or {} if any team's
    count of scored games doesn't match its games played in the standings
    (a game the nightly step couldn't score): then MoneyPuck stands in.
    """
    if rows is None:
        try:
            with psycopg2.connect(DATABASE_URL) as conn, conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT team_abbrev, SUM(xg_for - xg_against), COUNT(*)
                    FROM team_game_xg WHERE season_id = %s AND game_type = 2 GROUP BY team_abbrev
                    """,
                    (season_id,),
                )
                rows = cur.fetchall()
        except psycopg2.Error as exc:  # table not created yet, DB hiccup
            logger.warning(f"PuckPulse xG unavailable ({exc}); using MoneyPuck's")
            return {}
    totals = {team: (float(xgd), int(games)) for team, xgd, games in rows}
    short = [t for t, s in standings.items() if totals.get(t, (0, 0))[1] != s["games_played"]]
    if short:
        logger.warning(f"PuckPulse xG is missing games for {', '.join(sorted(short))}; using MoneyPuck's today")
        return {}
    return {t: totals[t] for t in standings if t in totals}


def xg_model_ratings(standings, season_id, fetch=fetch_moneypuck_xgd):
    """Ratings from the xG blend, or None if MoneyPuck is unavailable."""
    inputs = xg_model_inputs(season_id, fetch)
    if inputs is None:
        return None
    current, priors = inputs
    return team_ratings(blend_xg(standings, current), priors, prior_games=PRIOR_GAMES_XG)


def rating_parts(standings, xgd_totals, priors, prior_games, xg_weight, roster=None, goalies=None):
    """
    Each team's rating split into what pushed it there, in goals/game:
    this season's goals, this season's xG, last season's prior, the roster,
    and goaltending (the last two already folded into `priors`; `roster`
    and `goalies` say how much). The parts add up to the team_ratings()
    mean exactly. In v2.4 the prior is roster + goalies, so last_season is
    0; it's nonzero in the fallbacks. For the goals-only fallback, pass
    xg_weight=0 (the xG part is then None).
    """
    roster_change = roster or {}
    goalies = goalies or {}
    parts = {}
    for abbrev, s in standings.items():
        gp = s["games_played"]
        gd = s.get("goal_differential", 0)
        xgd = xgd_totals.get(abbrev, (gd, None))[0] if xg_weight else None
        denom = gp + prior_games
        moves = roster_change.get(abbrev, 0.0)
        goaltending = goalies.get(abbrev, 0.0)
        prior = priors.get(abbrev, 0.0) - moves - goaltending
        parts[abbrev] = {
            "games_played": gp,
            "goal_diff": gd,
            "xg_diff": None if xgd is None else round(xgd, 1),
            "goals": round((1 - xg_weight) * gd / denom, 4),
            "xg": None if xgd is None else round(xg_weight * xgd / denom, 4),
            "last_season": round(prior_games * prior / denom, 4),
            # Last season's per-game differential before the carryover haircut.
            "last_season_per_game": round(prior / PRIOR_CARRYOVER, 3),
            "last_season_share": round(prior_games / denom, 3),
            "roster": round(prior_games * moves / denom, 4),
            "roster_per_game": round(moves, 3),
            "goalies": round(prior_games * goaltending / denom, 4),
            "goalies_per_game": round(goaltending, 3),
        }
    return parts


def schedule_strength(ratings, games, as_of_date):
    """
    How the remaining schedule helps or hurts each team, in goals/game like
    the rating: how much weaker than a typical team's opponents its
    opponents are, plus home ice for any extra home games, plus rest (its
    own back-to-backs cost it; its opponents' help it). Positive = an
    easier road ahead. {team: {"games_left", "home_games", "effect"}}.
    """
    opponents = defaultdict(list)
    home_games = defaultdict(int)
    rest = defaultdict(float)  # goals/game the team gains (+) or loses to back-to-backs
    for g in remaining_games(games, as_of_date):
        if g["home"] in ratings and g["away"] in ratings:
            opponents[g["home"]].append(ratings[g["away"]][0])
            opponents[g["away"]].append(ratings[g["home"]][0])
            home_games[g["home"]] += 1
            fatigue = home_margin(g.get("home_b2b"), g.get("away_b2b")) - HOME_EDGE
            rest[g["home"]] += fatigue
            rest[g["away"]] -= fatigue
    avg_opp = {t: sum(o) / len(o) for t, o in opponents.items()}
    if not avg_opp:
        return {t: {"games_left": 0, "home_games": 0, "effect": 0.0} for t in ratings}
    typical = sum(avg_opp.values()) / len(avg_opp)
    out = {}
    for team in ratings:
        n = len(opponents[team])
        if not n:
            out[team] = {"games_left": 0, "home_games": 0, "effect": 0.0}
            continue
        home_tilt = HOME_EDGE * (2 * home_games[team] - n) / n
        out[team] = {
            "games_left": n,
            "home_games": home_games[team],
            "effect": round(typical - avg_opp[team] + home_tilt + rest[team] / n, 4),
        }
    return out


def odds_explanations(ratings, parts, games, as_of_date):
    """
    "Why these odds?" for every team: the rating's parts, the schedule's
    effect, and where each ranks in the league (1 = best rating / easiest
    schedule). Saved with the simulator inputs; served by
    GET /playoff-odds/why.
    """
    schedule = schedule_strength(ratings, games, as_of_date)
    by_rating = sorted(ratings, key=lambda t: -ratings[t][0])
    by_schedule = sorted(schedule, key=lambda t: -schedule[t]["effect"])
    return {
        team: {
            **parts[team],
            "rating": round(ratings[team][0], 4),
            "rating_rank": by_rating.index(team) + 1,
            "schedule": {**schedule[team], "rank": by_schedule.index(team) + 1},
        }
        for team in ratings
        if team in parts
    }


def load_priors(season_id):
    """Last season's final GD/game per team, times PRIOR_CARRYOVER."""
    with psycopg2.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT team_abbrev, goal_differential, games_played FROM season_final_standings WHERE season_id = %s",
                (previous_season_id(season_id),),
            )
            return {abbrev: PRIOR_CARRYOVER * gd / gp for abbrev, gd, gp in cur.fetchall() if gp}


def team_ratings(standings, priors, prior_games=PRIOR_GAMES, talent_sd=TALENT_SD):
    """
    Each team's strength estimate (mean, sd) in goals/game. The mean blends
    this season's GD with the prior as prior_games pseudo-games; the sd
    shrinks as real games accumulate. A team with no prior (e.g. a
    relocated franchise) starts at league average.
    """
    ratings = {}
    for abbrev, s in standings.items():
        gp = s["games_played"]
        prior = priors.get(abbrev, 0.0)
        mean = (s["goal_differential"] + prior_games * prior) / (gp + prior_games)
        sd = talent_sd * math.sqrt(prior_games / (gp + prior_games))
        ratings[abbrev] = (mean, sd)
    return ratings


def adjusted_ratings(teams, completed, priors, prior_games=PRIOR_GAMES, talent_sd=TALENT_SD, iterations=50):
    """
    EXPERIMENTAL -- not used in production. Backtested 2026-10 over 4 seasons
    (backtest_playoff_odds.py --sos): ~0.3% better Brier, within noise, and no
    gain under leave-one-season-out testing. Kept for future experiments.

    Opponent-adjusted (strength-of-schedule) ratings: solve for ratings r so
    each completed game's goal margin ~= r_home - r_away + HOME_EDGE, with
    each team pulled toward its prior as `prior_games` pseudo-games (ridge
    regression, solved by coordinate descent). Against average opponents it
    reduces exactly to team_ratings(); beating good teams now counts more.
    Returns {team: (mean, sd)} like team_ratings().
    """
    games_by_team = {t: [] for t in teams}
    for g in completed:
        margin = g["home_score"] - g["away_score"] - HOME_EDGE
        if g["home"] in games_by_team and g["away"] in games_by_team:
            games_by_team[g["home"]].append((margin, g["away"]))    # r_home = margin + r_away
            games_by_team[g["away"]].append((-margin, g["home"]))   # r_away = -margin + r_home

    rating = {t: priors.get(t, 0.0) for t in teams}
    for _ in range(iterations):
        for t, games in games_by_team.items():
            target = sum(m + rating[opp] for m, opp in games)
            rating[t] = (target + prior_games * priors.get(t, 0.0)) / (len(games) + prior_games)

    return {
        t: (rating[t], talent_sd * math.sqrt(prior_games / (len(games_by_team[t]) + prior_games)))
        for t in teams
    }


def _tiebreak_key(record):
    return (
        -record["points"],
        -record.get("regulation_wins", 0),
        -record.get("row", 0),
        -record["wins"],
    )


def determine_playoff_teams(trial_standings, divisions, conferences):
    """
    trial_standings: {team_abbrev: {'points', 'wins', optional
    'regulation_wins', 'row'}}. Returns the set of 16 playoff teams: top 3
    per division, then the next 2 per conference as wild cards.

    Raises ValueError if any division has zero teams -- there's no team to
    look up that division's conference from, and it means `divisions` was
    built wrong upstream (e.g. a bad divisionName from the standings API).
    """
    playoff_teams = set()
    conference_leftovers = defaultdict(list)

    for division_name, division_teams in divisions.items():
        if not division_teams:
            raise ValueError(f"Division '{division_name}' has no teams -- can't determine its conference")

        ranked = sorted(division_teams, key=lambda a: _tiebreak_key(trial_standings[a]))
        playoff_teams.update(ranked[:3])
        conference = conferences[ranked[0]]
        conference_leftovers[conference].extend(ranked[3:])

    for teams in conference_leftovers.values():
        ranked = sorted(teams, key=lambda a: _tiebreak_key(trial_standings[a]))
        playoff_teams.update(ranked[:2])

    return playoff_teams


def conference_cutlines(trial_standings, divisions, conferences):
    """
    The playoff line for one trial: the points of the second wild card (the
    last team in) in each conference, ranked like determine_playoff_teams().
    """
    leftovers = defaultdict(list)
    for division_teams in divisions.values():
        ranked = sorted(division_teams, key=lambda a: _tiebreak_key(trial_standings[a]))
        leftovers[conferences[ranked[0]]].extend(ranked[3:])
    lines = {}
    for conf, teams in leftovers.items():
        ranked = sorted(teams, key=lambda a: _tiebreak_key(trial_standings[a]))
        if len(ranked) >= 2:
            lines[conf] = trial_standings[ranked[1]]["points"]
    return lines


def _percentile(sorted_values, q):
    """Nearest-rank-ish linear interpolation on an already sorted list."""
    if not sorted_values:
        return None
    pos = (len(sorted_values) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(sorted_values) - 1)
    return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * (pos - lo)


def summarize_cutlines(samples):
    """{conference: [points per trial]} -> {conference: {p25, p50, p75}}, rounded to 0.5."""
    out = {}
    for conf, values in samples.items():
        ordered = sorted(values)
        out[conf] = {f"p{int(q * 100)}": round(_percentile(ordered, q) * 2) / 2 for q in (0.25, 0.5, 0.75)}
    return out


def lottery_order(trial_standings, playoff_teams):
    """The non-playoff teams, worst first (the draft lottery's order; losing a tiebreak picks earlier)."""
    missed = [t for t in trial_standings if t not in playoff_teams]
    return sorted(missed, key=lambda a: _tiebreak_key(trial_standings[a]), reverse=True)


def simulate(standings, schedule, trials, ratings, rng=random, cutline_out=None, lottery_out=None):
    """
    Monte Carlo playoff odds. If `cutline_out` is a dict, it's filled with
    the playoff line per conference ({conference: {p25, p50, p75}} in points)
    from the same trials -- no extra simulation or queries. If
    `lottery_out` is a dict, it's filled with each team's draft lottery
    chances ({team: [chance of pick 1, ..., pick 16]}): in each trial the
    non-playoff teams' order goes through the lottery's exact odds.
    """
    lottery_sums = defaultdict(lambda: [0.0] * len(lottery.COMBINATIONS))
    cutline_samples = defaultdict(list)
    divisions = defaultdict(list)
    conferences = {}
    # Each game's home margin (home ice + back-to-backs) once, not per trial.
    games = [(home, away, home_margin(*b2b)) for home, away, *b2b in schedule]
    for abbrev, s in standings.items():
        divisions[s["division"]].append(abbrev)
        conferences[abbrev] = s["conference"]

    made_playoffs = defaultdict(int)

    for _ in range(trials):
        strength = {abbrev: rng.gauss(mean, sd) for abbrev, (mean, sd) in ratings.items()}
        trial = {
            abbrev: {
                "points": s["points"],
                "wins": s["wins"],
                "regulation_wins": s.get("regulation_wins", 0),
                "row": s.get("row", 0),
            }
            for abbrev, s in standings.items()
        }

        for home, away, margin in games:
            x = (strength[home] - strength[away] + margin) / SCALE
            home_wins = rng.random() < (1 / (1 + math.exp(-x)) if x > -700 else 0.0)
            winner, loser = (home, away) if home_wins else (away, home)
            trial[winner]["points"] += 2
            trial[winner]["wins"] += 1
            if rng.random() < OT_PROBABILITY:
                trial[loser]["points"] += 1          # OT/SO loser point
                if rng.random() >= SHOOTOUT_SHARE_OF_OT:
                    trial[winner]["row"] += 1        # won in overtime
            else:
                trial[winner]["regulation_wins"] += 1
                trial[winner]["row"] += 1

        playoff_teams = determine_playoff_teams(trial, divisions, conferences)
        for team in playoff_teams:
            made_playoffs[team] += 1
        if cutline_out is not None:
            for conf, pts in conference_cutlines(trial, divisions, conferences).items():
                cutline_samples[conf].append(pts)
        if lottery_out is not None:
            order = lottery_order(trial, playoff_teams)
            if len(order) == len(lottery.COMBINATIONS):
                for team, chances in lottery.pick_chances(order).items():
                    sums = lottery_sums[team]
                    for k, p in enumerate(chances):
                        sums[k] += p

    if cutline_out is not None:
        cutline_out.update(summarize_cutlines(cutline_samples))
    if lottery_out is not None:
        lottery_out.update({team: [round(v / trials, 5) for v in lottery_sums[team]] for team in standings})

    return {team: made_playoffs[team] / trials for team in standings}


def sim_inputs(standings, ratings, games, season_id, as_of_date, why=None, players=None, cutline=None):
    """
    Everything the in-browser season simulator needs to play out the rest
    of the season exactly like simulate() does: the game model's constants,
    each team's record and strength rating, and the remaining schedule.
    `why` (odds_explanations()) rides along for GET /playoff-odds/why, and
    `players` (player_values.player_values()) for roster-change scenarios,
    and `cutline` (from simulate()) for GET /playoff-line.
    """
    return {
        "why": why or {},
        "cutline": cutline or {},
        "players": {str(pid): v for pid, v in (players or {}).items()},
        "season_id": season_id,
        "as_of_date": str(as_of_date),
        "model": {
            "version": MODEL_VERSION,
            "home_edge": HOME_EDGE,
            "scale": SCALE,
            "home_b2b": HOME_B2B,
            "away_b2b": AWAY_B2B,
            "ot_probability": OT_PROBABILITY,
            "shootout_share_of_ot": SHOOTOUT_SHARE_OF_OT,
        },
        "teams": {
            abbrev: {
                "points": s["points"],
                "wins": s["wins"],
                "losses": s.get("losses", 0),
                "ot_losses": s.get("ot_losses", 0),
                "regulation_wins": s.get("regulation_wins", 0),
                "row": s.get("row", 0),
                "division": s["division"],
                "conference": s["conference"],
                "rating": round(ratings[abbrev][0], 4),
                "rating_sd": round(ratings[abbrev][1], 4),
            }
            for abbrev, s in standings.items()
        },
        # [date, home, away, home_b2b, away_b2b]; readers unpack the first three.
        "games": [[g["date"], g["home"], g["away"], g.get("home_b2b", False), g.get("away_b2b", False)]
                  for g in remaining_games(games, as_of_date)],
    }


def load_rosters(goalies=False):
    """{player_id: team} for skaters (or goalies) on an NHL roster now (from the players table)."""
    with psycopg2.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT player_id, team_abbrev FROM players WHERE on_roster AND (position_code = 'G') = %s",
                (goalies,),
            )
            return dict(cur.fetchall())


def roster_rating_prior(season_id):
    """
    {team: goals/game its current skaters add vs. a league-average roster},
    times ROSTER_RATING_WEIGHT: the v2.4 prior's skater part. Values come
    from the last two seasons; injured players still under contract count
    (missing_player_teams). Best effort: {} falls back to last season's xG
    (the v2.1 prior).
    """
    import player_values as pv

    start = season_id // 10000
    try:
        last, before_last = pv.season_skaters(start - 1), pv.season_skaters(start - 2)
        values = pv.player_values(last, before_last)
        rosters = load_rosters()
        rosters.update(missing_player_teams(values, last, rosters))
        strength = pv.team_roster_strength(values, last, rosters)
    except Exception as exc:  # network, parse, or DB
        logger.warning(f"Couldn't compute roster ratings ({exc}); prior is last season's xG today")
        return {}
    return {t: round(ROSTER_RATING_WEIGHT * v, 4) for t, v in strength.items()}


PLAYER_LANDING_URL = "https://api-web.nhle.com/v1/player/{player_id}/landing"
MISSING_LOOKUP_MIN = 0.01  # goals/game: smaller departures aren't worth an API call


def goalie_prior(season_id):
    """
    {team: goals/game its current goalies save vs. a league-average
    tandem}, times GOALIE_WEIGHT, for the prior. Best effort: without it
    the prior has no goaltending (the v2.2 model).
    """
    import player_values as pv

    start = season_id // 10000
    try:
        last, before_last = (goalie_season(y, stored_goalie_xg(y * 10000 + y + 1)) for y in (start - 1, start - 2))
        rosters = load_rosters(goalies=True)
        # Same injured-reserve gap as skaters. A flat value makes every goalie
        # with GOALIE_LOOKUP_MIN_GP+ starts last season worth a lookup.
        regulars = {pid: {"name": g["name"], "value": 1.0} for pid, g in last.items() if g["gp"] >= GOALIE_LOOKUP_MIN_GP}
        rosters.update(missing_player_teams(regulars, last, rosters))
        strength = pv.team_goalie_strength(pv.goalie_rates(last, before_last), last, rosters)
    except Exception as exc:  # network, parse, or DB
        logger.warning(f"Couldn't compute goaltending ({exc}); prior has no goalie part today")
        return {}
    return {t: round(GOALIE_WEIGHT * v, 4) for t, v in strength.items()}


def goalie_season(year, faced):
    """
    pv.season_goalies()'s shape for the regular season starting in `year`:
    from our own xG (`faced`, stored_goalie_xg()) when every game is
    stored, else MoneyPuck's. Ours matched MoneyPuck's GSAx at r = 0.88-0.97
    per goalie (2022-23 to 2025-26) and backtested slightly better (Brier
    0.1085 vs 0.1091 over those four seasons).
    """
    import player_values as pv

    season_id = year * 10000 + year + 1
    games = sum(gp for _, gp in pv.fetch_nhl_team_goals(year).values()) / 2
    if faced and faced["games"] >= games - 2:  # a game or two short is noise, not a missing week
        return pv.our_season_goalies(pv.fetch_nhl_goalies(year), faced["goalies"])
    logger.info(f"Goalie xG for {season_id}: {faced['games'] if faced else 0} of {games:.0f} games stored; using MoneyPuck's")
    return pv.season_goalies(pv.fetch_csv(pv.MONEYPUCK_GOALIES_URL, year))


def stored_goalie_xg(season_id):
    """{"games": regular-season games stored, "goalies": {player_id: (xG against, goals against)}}, or None."""
    try:
        with psycopg2.connect(DATABASE_URL) as conn, conn.cursor() as cur:
            cur.execute("SELECT COUNT(DISTINCT game_id) FROM goalie_game_xg WHERE season_id = %s AND game_type = 2", (season_id,))
            games = cur.fetchone()[0]
            cur.execute(
                """
                SELECT goalie_id, SUM(xg_against), SUM(goals_against)
                FROM goalie_game_xg WHERE season_id = %s AND game_type = 2 GROUP BY goalie_id
                """,
                (season_id,),
            )
            rows = cur.fetchall()
    except psycopg2.Error as exc:  # no table yet, or a DB hiccup: MoneyPuck stands in
        logger.warning(f"Couldn't read goalie xG for {season_id} ({type(exc).__name__})")
        return None
    return {"games": games, "goalies": {r[0]: (float(r[1]), int(r[2])) for r in rows}} if rows else None


def missing_player_teams(values, last, rosters, get=nhl_get):
    """
    {player_id: team} for last season's regulars missing from today's
    rosters who still have a team. The NHL's current-roster feed leaves out
    injured reserve, so without this an injured star (Seth Jarvis, Oct
    2026) counted as gone for the season. The player's landing page has
    his team (none if retired or unsigned). Best effort per player.
    """
    found = {}
    for pid, v in values.items():
        played = min(last.get(pid, {}).get("gp", 0) / 82, 1.0)
        if pid in rosters or abs(v["value"] * played) < MISSING_LOOKUP_MIN:
            continue
        try:
            team = get(PLAYER_LANDING_URL.format(player_id=pid)).get("currentTeamAbbrev")
        except Exception as exc:  # one player's page failing shouldn't cost the rest
            logger.warning(f"No landing page for {v['name']} ({exc}); counting him as gone")
            continue
        if team:
            found[pid] = team
    if found:
        logger.info(f"{len(found)} players off the current-roster feed but still signed (injured reserve, etc.)")
    return found


def with_roster_change(priors, change):
    """Priors plus each team's roster change (a team new to the league
    gets its change alone)."""
    return {t: priors.get(t, 0.0) + change.get(t, 0.0) for t in set(priors) | set(change)}


def compute_player_values(season_id):
    """
    Skater values for roster-change scenarios. Best effort: the odds don't
    depend on them, so an NHL stats or roster hiccup only costs the trade
    simulator a day.
    """
    import player_values as pv

    start = season_id // 10000
    try:
        values = pv.player_values(pv.season_skaters(start), pv.season_skaters(start - 1), rosters=load_rosters())
    except Exception as exc:  # network, parse, or DB
        logger.warning(f"Couldn't compute player values ({exc}); roster-change scenarios unavailable today")
        return {}
    logger.info(f"Player values for {len(values)} skaters")
    return values


def save_sim_inputs(payload):
    """
    Store today's simulator inputs (one row per season, latest run wins).
    Best effort: the odds are already saved, and a failure here (e.g. the
    table not created yet) shouldn't fail the daily job.
    """
    import json

    try:
        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO season_sim_inputs (season_id, as_of_date, payload, computed_at)
                    VALUES (%s, %s, %s, NOW())
                    ON CONFLICT (season_id) DO UPDATE SET
                        as_of_date = EXCLUDED.as_of_date,
                        payload = EXCLUDED.payload,
                        computed_at = NOW()
                    """,
                    (payload["season_id"], payload["as_of_date"], json.dumps(payload)),
                )
    except psycopg2.Error as exc:
        logger.warning(f"Couldn't save season simulator inputs ({exc}); odds were saved")


LOTTERY_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS draft_lottery_odds (
    season_id               INTEGER NOT NULL,
    as_of_date              DATE NOT NULL,
    team_abbrev             VARCHAR(3) NOT NULL,
    missed_playoffs_pct     NUMERIC(6,5) NOT NULL,  -- in the lottery at all
    first_pick_pct          NUMERIC(6,5) NOT NULL,
    top_three_pct           NUMERIC(6,5) NOT NULL,
    pick_chances            JSONB NOT NULL,         -- [chance of pick 1, ..., pick 16]
    trials                  INTEGER NOT NULL,
    computed_at             TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (season_id, as_of_date, team_abbrev)
)
"""


def save_lottery(chances, season_id, as_of_date, trials):
    """Each team's simulated draft lottery chances (lottery.py), one row per team per day. Best effort."""
    import json

    try:
        with psycopg2.connect(DATABASE_URL) as conn, conn.cursor() as cur:
            cur.execute(LOTTERY_TABLE_SQL)
            cur.execute("GRANT SELECT ON draft_lottery_odds TO nhl_api_readonly")
            for team, picks in chances.items():
                cur.execute(
                    """
                    INSERT INTO draft_lottery_odds (season_id, as_of_date, team_abbrev, missed_playoffs_pct,
                                                    first_pick_pct, top_three_pct, pick_chances, trials, computed_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
                    ON CONFLICT (season_id, as_of_date, team_abbrev) DO UPDATE SET
                        missed_playoffs_pct = EXCLUDED.missed_playoffs_pct, first_pick_pct = EXCLUDED.first_pick_pct,
                        top_three_pct = EXCLUDED.top_three_pct, pick_chances = EXCLUDED.pick_chances,
                        trials = EXCLUDED.trials, computed_at = NOW()
                    """,
                    (season_id, as_of_date, team, min(sum(picks), 1.0), picks[0], sum(picks[:3]), json.dumps(picks), trials),
                )
    except psycopg2.Error as exc:
        logger.warning(f"Couldn't save draft lottery odds ({exc}); playoff odds were saved")


def save_odds(odds, season_id, as_of_date, trials):
    with psycopg2.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            for team_abbrev, pct in odds.items():
                cur.execute(
                    """
                    INSERT INTO playoff_odds (season_id, as_of_date, team_abbrev, playoff_pct, trials, computed_at)
                    VALUES (%s, %s, %s, %s, %s, NOW())
                    ON CONFLICT (season_id, as_of_date, team_abbrev) DO UPDATE SET
                        playoff_pct = EXCLUDED.playoff_pct,
                        trials = EXCLUDED.trials,
                        computed_at = NOW()
                    """,
                    (season_id, as_of_date, team_abbrev, pct, trials),
                )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int, default=None, help="Defaults to the season --as-of falls in")
    parser.add_argument("--as-of", type=str, default=str(date.today()))
    parser.add_argument("--trials", type=int, default=DEFAULT_TRIALS)
    parser.add_argument("--no-save", action="store_true", help="Print results without writing to the DB")
    args = parser.parse_args()
    if not DATABASE_URL and not args.no_save:
        raise SystemExit("DATABASE_URL is not set")

    if args.season is None:
        args.season = current_season_id(date.fromisoformat(args.as_of))

    standings = fetch_standings_as_of(args.as_of)
    if not standings:
        logger.info(f"No standings for {args.as_of} (offseason?) -- nothing to simulate")
        return
    logger.info(f"Loaded standings for {len(standings)} teams as of {args.as_of}")

    ours = puckpulse_xgd(args.season, standings)
    roster = roster_rating_prior(args.season)
    # MoneyPuck only as a fallback: its xG if ours is missing a game, and
    # last season's xG as the prior if the roster ratings failed.
    xg_inputs = None if ours and roster else xg_model_inputs(args.season)
    if ours or xg_inputs is not None:
        current_xgd = ours or xg_inputs[0]
        last_season_xg = xg_inputs[1] if xg_inputs else {}
        logger.info(f"Using the goals + {'PuckPulse' if ours else 'MoneyPuck'} xG model")
        goalies = goalie_prior(args.season)
        # v2.4: the prior is the roster plus its goalies. Without roster
        # ratings (MoneyPuck or DB hiccup), last season's xG stands in.
        base = {} if roster else last_season_xg
        priors = with_roster_change(with_roster_change(base, roster), goalies)
        ratings = team_ratings(blend_xg(standings, current_xgd), priors, prior_games=PRIOR_GAMES_XG)
        parts = rating_parts(standings, current_xgd, priors, PRIOR_GAMES_XG, XG_WEIGHT, roster, goalies)
        for label, extra in (("Roster ratings", roster), ("Goaltending", goalies)):
            if extra:
                biggest = sorted(extra.items(), key=lambda kv: -abs(kv[1]))[:5]
                logger.info(f"{label} (goals/game): " + ", ".join(f"{t} {v:+.2f}" for t, v in biggest))
    else:
        priors = load_priors(args.season)
        logger.info(f"Goals-only model: {len(priors)} prior ratings from season {previous_season_id(args.season)}")
        ratings = team_ratings(standings, priors)
        parts = rating_parts(standings, {}, priors, PRIOR_GAMES, 0.0)

    games = fetch_season_games(list(standings.keys()), args.season)
    _, schedule = split_games(games, args.as_of)
    logger.info(f"{len(schedule)} remaining games to simulate across {args.trials} trials")

    started = time.time()
    cutline, lottery_chances = {}, {}
    odds = simulate(standings, schedule, args.trials, ratings, cutline_out=cutline, lottery_out=lottery_chances)
    logger.info(f"Playoff line by conference: {cutline}")
    logger.info(f"Simulated in {time.time() - started:.1f}s")

    if not args.no_save:
        save_odds(odds, args.season, args.as_of, args.trials)
        save_lottery(lottery_chances, args.season, args.as_of, args.trials)
        why = odds_explanations(ratings, parts, games, args.as_of)
        players = compute_player_values(args.season)
        save_sim_inputs(sim_inputs(standings, ratings, games, args.season, args.as_of, why=why, players=players, cutline=cutline))

    best = sorted(lottery_chances.items(), key=lambda kv: -kv[1][0])[:5]
    logger.info("Draft lottery, chance at No. 1: " + ", ".join(f"{t} {p[0] * 100:.1f}%" for t, p in best))
    for team, pct in sorted(odds.items(), key=lambda x: -x[1]):
        mean, _ = ratings[team]
        logger.info(f"{team}: {pct * 100:.1f}%  (rating {mean:+.2f} GD/game)")


if __name__ == "__main__":
    main()
