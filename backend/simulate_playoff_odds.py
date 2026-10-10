"""
Playoff Odds Simulator (v2.1: goals + MoneyPuck xG)

Monte Carlo simulation of the rest of the regular season to estimate each
team's probability of making the playoffs.

How it works:
  1. Rate each team by a blend of goal differential and MoneyPuck expected-
     goals (xG) differential per game, shrunk toward a prior: half of last
     season's xG differential per game, weighted as PRIOR_GAMES_XG
     pseudo-games. Early in the season the prior dominates; by midseason
     this season's results take over. If MoneyPuck is unreachable, it falls
     back to goals only (prior = last season's GD/game, PRIOR_GAMES).
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
from datetime import date

import psycopg2
import requests
from dotenv import load_dotenv

from logging_config import setup_logging

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

# Game model -- fit by calibrate_playoff_model.py.
HOME_EDGE = 0.264            # goals/game of home-ice advantage
SCALE = 1.47                 # logistic steepness, in goals/game
OT_PROBABILITY = 0.221       # share of games reaching overtime
SHOOTOUT_SHARE_OF_OT = 0.32  # share of OT games decided in a shootout

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

DEFAULT_TRIALS = 10000


def current_season_id(today=None):
    """Jul-Dec -> season starts this year; Jan-Jun -> it started last year."""
    today = today or date.today()
    start_year = today.year if today.month >= 7 else today.year - 1
    return int(f"{start_year}{start_year + 1}")


def previous_season_id(season_id):
    start = season_id // 10000
    return int(f"{start - 1}{start}")


def nhl_get(url, retries=6):
    """GET with a polite retry: the NHL API rate-limits bursts (HTTP 429)."""
    for attempt in range(retries):
        response = requests.get(url, timeout=20)
        if response.status_code != 429:
            response.raise_for_status()
            return response.json()
        time.sleep(int(response.headers.get("Retry-After", 0)) or 5 * (attempt + 1))
    response.raise_for_status()


def win_probability(home_rating, away_rating):
    """P(home team wins), ratings in goals/game of strength."""
    x = (home_rating - away_rating + HOME_EDGE) / SCALE
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
    return list(seen.values())


def split_games(games, as_of_date):
    """
    (completed games with scores up to the date, remaining (home, away)
    pairs). Standings for a date include that day's games once they're
    played, so a game on the as-of date is remaining until it has a final
    score -- the daily run happens before that day's games, and treating
    them as done dropped them from the simulation entirely.
    """
    return [g for g in games if _is_played(g, as_of_date)], [(g["home"], g["away"]) for g in remaining_games(games, as_of_date)]


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


def xg_model_ratings(standings, season_id, fetch=fetch_moneypuck_xgd):
    """Ratings from the xG blend, or None if MoneyPuck is unavailable."""
    start = season_id // 10000
    try:
        current = fetch(start)
        previous = fetch(start - 1)
    except Exception as exc:  # network, HTTP, or parse -- fall back to goals only
        logger.warning(f"MoneyPuck xG unavailable ({exc}); using the goals-only model")
        return None
    priors = {t: PRIOR_CARRYOVER * xgd / gp for t, (xgd, gp) in previous.items() if gp}
    return team_ratings(blend_xg(standings, current), priors, prior_games=PRIOR_GAMES_XG)


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


def simulate(standings, schedule, trials, ratings, rng=random):
    divisions = defaultdict(list)
    conferences = {}
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

        for home, away in schedule:
            home_wins = rng.random() < win_probability(strength[home], strength[away])
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

        for team in determine_playoff_teams(trial, divisions, conferences):
            made_playoffs[team] += 1

    return {team: made_playoffs[team] / trials for team in standings}


def sim_inputs(standings, ratings, games, season_id, as_of_date):
    """
    Everything the in-browser season simulator needs to play out the rest
    of the season exactly like simulate() does: the game model's constants,
    each team's record and strength rating, and the remaining schedule.
    """
    return {
        "season_id": season_id,
        "as_of_date": str(as_of_date),
        "model": {
            "home_edge": HOME_EDGE,
            "scale": SCALE,
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
        "games": [[g["date"], g["home"], g["away"]] for g in remaining_games(games, as_of_date)],
    }


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

    ratings = xg_model_ratings(standings, args.season)
    if ratings is not None:
        logger.info("Using the goals + MoneyPuck xG model")
    else:
        priors = load_priors(args.season)
        logger.info(f"Goals-only model: {len(priors)} prior ratings from season {previous_season_id(args.season)}")
        ratings = team_ratings(standings, priors)

    games = fetch_season_games(list(standings.keys()), args.season)
    _, schedule = split_games(games, args.as_of)
    logger.info(f"{len(schedule)} remaining games to simulate across {args.trials} trials")

    started = time.time()
    odds = simulate(standings, schedule, args.trials, ratings)
    logger.info(f"Simulated in {time.time() - started:.1f}s")

    if not args.no_save:
        save_odds(odds, args.season, args.as_of, args.trials)
        save_sim_inputs(sim_inputs(standings, ratings, games, args.season, args.as_of))

    for team, pct in sorted(odds.items(), key=lambda x: -x[1]):
        mean, _ = ratings[team]
        logger.info(f"{team}: {pct * 100:.1f}%  (rating {mean:+.2f} GD/game)")


if __name__ == "__main__":
    main()
