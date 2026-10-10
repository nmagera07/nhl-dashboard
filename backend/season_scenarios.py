"""
"What if" questions against the playoff-odds model, for NHL Intelligence's
tools (and anyone else): what happens to a team's odds if it goes W-L over
its next N games, and what record over its next N games it needs.

Both run the same season simulation as simulate_playoff_odds.py, from the
inputs the daily run saves (season_sim_inputs): each team's record and
strength rating, the model's constants, and the remaining schedule.
"""

import random
from collections import defaultdict

import simulate_playoff_odds as sim

DEFAULT_TRIALS = 2000


class UnknownTeam(ValueError):
    pass


def _next_games(payload, team, n):
    """Indexes (into payload['games']) of the team's next n games."""
    found = [i for i, (_, home, away) in enumerate(payload["games"]) if team in (home, away)]
    return found[:n]


def _simulate(payload, trials, seed, team, window, forced=None):
    """
    Plays out the season `trials` times and returns `team`'s playoff odds
    and average final points. `window` is the team's next games.
    `forced` = {"wins": w, "ot_losses": o} fixes how those window games go
    (which ones are wins is shuffled per trial). Every game draws the same
    random numbers whether forced or not, so a scenario and its baseline
    with the same seed differ only because of the forced results -- the
    comparison isn't drowned in simulation noise.
    """
    model, teams, games = payload["model"], payload["teams"], payload["games"]
    home_edge, scale = model["home_edge"], model["scale"]
    ot_p, so_share = model["ot_probability"], model["shootout_share_of_ot"]
    divisions, conferences = defaultdict(list), {}
    for abbrev, t in teams.items():
        divisions[t["division"]].append(abbrev)
        conferences[abbrev] = t["conference"]

    rng, shuffle_rng = random.Random(seed), random.Random(seed + 1)
    made = points = 0

    for _ in range(trials):
        strength = {a: rng.gauss(t["rating"], t["rating_sd"]) for a, t in teams.items()}
        rec = {a: {"points": t["points"], "wins": t["wins"], "regulation_wins": t["regulation_wins"], "row": t["row"]}
               for a, t in teams.items()}
        outcomes = None
        if forced:
            outcomes = ["W"] * forced["wins"] + ["OTL"] * forced["ot_losses"]
            outcomes += ["L"] * (len(window) - len(outcomes))
            shuffle_rng.shuffle(outcomes)
            outcomes = dict(zip(window, outcomes))

        for i, (_, home, away) in enumerate(games):
            if home not in rec or away not in rec:
                continue
            x = (strength[home] - strength[away] + home_edge) / scale
            home_wins = rng.random() < 1 / (1 + 2.718281828459045 ** -x)
            went_ot = rng.random() < ot_p
            shootout = rng.random() < so_share
            if outcomes and i in outcomes:
                result = outcomes[i]
                team_is_home = home == team
                team_wins = result == "W"
                home_wins = team_wins == team_is_home
                went_ot = result == "OTL" or (team_wins and went_ot)
            winner, loser = (home, away) if home_wins else (away, home)
            rec[winner]["points"] += 2
            rec[winner]["wins"] += 1
            if went_ot:
                rec[loser]["points"] += 1
                if not shootout:
                    rec[winner]["row"] += 1
            else:
                rec[winner]["regulation_wins"] += 1
                rec[winner]["row"] += 1

        in_playoffs = team in sim.determine_playoff_teams(rec, divisions, conferences)
        made += in_playoffs
        points += rec[team]["points"]

    return {"playoff_pct": made / trials, "avg_points": points / trials}


def _check_team(payload, team):
    team = team.upper()
    if team not in payload["teams"]:
        raise UnknownTeam(team)
    return team


def _opponents(payload, team, window):
    out = []
    for i in window:
        date, home, away = payload["games"][i]
        out.append(f"{date} {'vs' if home == team else '@'} {away if home == team else home}")
    return out


def scenario(payload, team, games, wins, ot_losses=0, trials=DEFAULT_TRIALS, seed=7):
    """The team's playoff odds and projected points if it goes wins-losses(-OT) in its next `games`."""
    team = _check_team(payload, team)
    window = _next_games(payload, team, games)
    games = len(window)
    if wins < 0 or ot_losses < 0 or wins + ot_losses > games:
        raise ValueError(f"{team} has {games} games left in that span; wins + OT losses can't exceed it")
    base = _simulate(payload, trials, seed, team, window)
    what_if = _simulate(payload, trials, seed, team, window, forced={"wins": wins, "ot_losses": ot_losses})
    return {
        "team": team,
        "as_of": payload["as_of_date"],
        "scenario": f"{wins}-{games - wins - ot_losses}-{ot_losses} over the next {games} games",
        "games": _opponents(payload, team, window),
        "baseline": {"playoff_pct": round(base["playoff_pct"], 3), "avg_points": round(base["avg_points"], 1)},
        "with_scenario": {"playoff_pct": round(what_if["playoff_pct"], 3), "avg_points": round(what_if["avg_points"], 1)},
        "trials": trials,
    }


def playoff_path(payload, team, games=10, trials_per_record=500, seed=11):
    """
    The team's playoff odds for every record over its next `games` (0 wins
    up to all of them), each from its own forced-results simulation -- the
    same question as scenario(), so the table and a "what if they go 7-3?"
    answer agree. Shared seeds keep the rows from wobbling against each other.
    """
    team = _check_team(payload, team)
    window = _next_games(payload, team, games)
    base = _simulate(payload, trials_per_record, seed, team, window)
    rows = []
    for wins in range(len(window) + 1):
        result = _simulate(payload, trials_per_record, seed, team, window, forced={"wins": wins, "ot_losses": 0})
        rows.append({"record": f"{wins}-{len(window) - wins}", "playoff_pct": round(result["playoff_pct"], 3)})
    return {
        "team": team,
        "as_of": payload["as_of_date"],
        "games": _opponents(payload, team, window),
        "current_playoff_pct": round(base["playoff_pct"], 3),
        "by_record": rows,
        "note": "Losses counted as regulation losses; each overtime loss instead would add a point.",
        "trials_per_record": trials_per_record,
    }
