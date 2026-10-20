"""
Player values for "what if they traded X?" questions.

Each skater's worth in goals/game over a replacement-level player, the same
unit as the playoff-odds model's team ratings, so a trade is arithmetic:
the team losing him drops by his value, the team getting him gains it, and
season_scenarios.roster_change() replays the season with those ratings.

How a value is built:
  1. Game Score (Dom Luszczyszyn's box-score composite): goals, assists,
     shots, blocks, penalties, faceoffs, plus 5-on-5 on-ice shot attempts
     and even-strength on-ice goals, from the NHL's stats API (it matches
     MoneyPuck's version at r = 0.999 per player, 2018-19 to 2025-26).
  2. Per game, blended over this season and last, pulled toward
     replacement level by SHRINK_GAMES pseudo-games, so six hot games don't
     make a star.
  3. Minus replacement level (fringe players' Game Score per game, by
     position), times GS_TO_GOALS: goals/game of team goal differential
     per point of team Game Score per game.

GS_TO_GOALS and the replacement levels come from `--calibrate` (3 seasons,
96 team-seasons; team Game Score tracks goal differential at r = 0.87).
Tried first and dropped: relative 5-on-5 xG alone, which rated Crosby and
Makar below average and third-pair defensemen among the league's best.

Known limits: skaters only (no goalies); line-mates and team quality leak
into on-ice numbers; a player coming in is assumed to replace a
replacement-level player. Answers should say "roughly".

Usage:
    python player_values.py --calibrate     # refit the constants
    python player_values.py --top 20        # today's most valuable skaters
"""

import argparse
import csv
import io
from collections import defaultdict

import requests

MONEYPUCK_HEADERS = {"User-Agent": "nhl-dashboard (personal, non-commercial; credits MoneyPuck.com)"}

# From --calibrate on NHL stats, 2023-24 to 2025-26 (MoneyPuck's data gave 0.194 and D 0.165).
GS_TO_GOALS = 0.200                         # team GD/game per team Game Score/game
REPLACEMENT_GS = {"F": 0.183, "D": 0.168}   # Game Score/game of fringe (5-29 GP) players
SHRINK_GAMES = 10                           # pseudo-games of replacement level
FRINGE_GP = (5, 30)


def _f(row, key):
    return float(row.get(key) or 0)


def game_score(all_row, ev_row):
    """Season Game Score from a player's all-situations and 5-on-5 rows."""
    return (
        0.75 * _f(all_row, "I_F_goals") + 0.7 * _f(all_row, "I_F_primaryAssists")
        + 0.55 * _f(all_row, "I_F_secondaryAssists") + 0.075 * _f(all_row, "I_F_shotsOnGoal")
        + 0.05 * _f(all_row, "shotsBlockedByPlayer")
        + 0.15 * _f(all_row, "penaltiesDrawn") - 0.15 * _f(all_row, "penalties")
        + 0.01 * _f(all_row, "faceoffsWon") - 0.01 * _f(all_row, "faceoffsLost")
        + 0.05 * _f(ev_row, "OnIce_F_shotAttempts") - 0.05 * _f(ev_row, "OnIce_A_shotAttempts")
        + 0.15 * _f(ev_row, "OnIce_F_goals") - 0.15 * _f(ev_row, "OnIce_A_goals")
    )


def position_group(position):
    return "D" if position == "D" else "F"


def season_game_scores(csv_text):
    """{player_id: {"name", "team", "pos", "gp", "gs"}} from a MoneyPuck skaters CSV (the backtest's old cache)."""
    by_player = defaultdict(dict)
    for row in csv.DictReader(io.StringIO(csv_text)):
        by_player[int(row["playerId"])][row["situation"]] = row
    out = {}
    for pid, rows in by_player.items():
        if "all" not in rows or "5on5" not in rows:
            continue
        gp = int(_f(rows["all"], "games_played"))
        if gp:
            out[pid] = {"name": rows["all"]["name"], "team": rows["all"]["team"], "pos": rows["all"]["position"],
                        "gp": gp, "gs": game_score(rows["all"], rows["5on5"])}
    return out


# The same Game Score inputs from the NHL's own stats API (api.nhle.com),
# one report each. Its on-ice goals are even strength (5-on-5 plus 4-on-4
# and 3-on-3) where MoneyPuck's are 5-on-5 only; --calibrate refits for it.
NHL_SKATER_URL = "https://api.nhle.com/stats/rest/en/skater/{report}?limit=-1&cayenneExp=seasonId={season}%20and%20gameTypeId=2"
NHL_SKATER_REPORTS = ("scoringpergame", "penalties", "faceoffwins", "summaryshooting", "goalsForAgainst")


def fetch_nhl_skaters(year):
    """[row]: each skater's regular season (starting in `year`), the NHL reports merged by player."""
    season = f"{year}{year + 1}"
    merged = defaultdict(dict)
    for report in NHL_SKATER_REPORTS:
        response = requests.get(NHL_SKATER_URL.format(report=report, season=season), timeout=60)
        response.raise_for_status()
        for row in response.json()["data"]:
            merged[row["playerId"]].update(row)
    return list(merged.values())


def nhl_game_scores(rows):
    """season_game_scores()'s shape from fetch_nhl_skaters() rows. A traded player's team is his last."""
    out = {}
    for row in rows:
        gp = int(row.get("gamesPlayed") or 0)
        if not gp:
            continue
        all_row = {"I_F_goals": row.get("goals"), "I_F_primaryAssists": row.get("totalPrimaryAssists"),
                   "I_F_secondaryAssists": row.get("totalSecondaryAssists"), "I_F_shotsOnGoal": row.get("shots"),
                   "shotsBlockedByPlayer": row.get("blockedShots"), "penaltiesDrawn": row.get("penaltiesDrawn"),
                   "penalties": row.get("penalties"), "faceoffsWon": row.get("totalFaceoffWins"),
                   "faceoffsLost": row.get("totalFaceoffLosses")}
        ev_row = {"OnIce_F_shotAttempts": row.get("satFor"), "OnIce_A_shotAttempts": row.get("satAgainst"),
                  "OnIce_F_goals": row.get("evenStrengthGoalsFor"), "OnIce_A_goals": row.get("evenStrengthGoalsAgainst")}
        out[int(row["playerId"])] = {"name": row.get("skaterFullName"), "team": (row.get("teamAbbrevs") or "").split(",")[-1],
                                     "pos": row.get("positionCode"), "gp": gp, "gs": game_score(all_row, ev_row)}
    return out


def season_skaters(year):
    """This module's skater input for the season starting in `year`, from the NHL."""
    return nhl_game_scores(fetch_nhl_skaters(year))


NHL_TEAM_SUMMARY_URL = "https://api.nhle.com/stats/rest/en/team/summary?limit=-1&cayenneExp=seasonId={season}%20and%20gameTypeId=2"
NHL_TEAMS_URL = "https://api.nhle.com/stats/rest/en/team"


def fetch_nhl_team_goals(year):
    """{team: (goal differential, games played)} for the regular season starting in `year`."""
    codes = {t["id"]: t["triCode"] for t in requests.get(NHL_TEAMS_URL, timeout=60).json()["data"]}
    response = requests.get(NHL_TEAM_SUMMARY_URL.format(season=f"{year}{year + 1}"), timeout=60)
    response.raise_for_status()
    return {codes[r["teamId"]]: (r["goalsFor"] - r["goalsAgainst"], r["gamesPlayed"]) for r in response.json()["data"]}


def fetch_csv(url, year):
    response = requests.get(url.format(year=year), headers=MONEYPUCK_HEADERS, timeout=30)
    response.raise_for_status()
    return response.text


def player_values(current, previous, rosters=None):
    """
    {player_id: {"name", "team", "pos", "gp", "value"}}: goals/game over
    replacement, from this season's and last season's season_game_scores().
    `rosters` ({player_id: team}) overrides MoneyPuck's team, which is stale
    for a player who moved in the offseason and hasn't played yet.
    """
    out = {}
    for pid in set(current) | set(previous):
        cur, prev = current.get(pid), previous.get(pid)
        latest = cur or prev
        team = (rosters or {}).get(pid, latest["team"])
        if rosters is not None and pid not in rosters:
            continue  # not on an NHL roster now (retired, unsigned, in the minors)
        repl = REPLACEMENT_GS[position_group(latest["pos"])]
        gs = (cur or {}).get("gs", 0) + (prev or {}).get("gs", 0)
        gp = (cur or {}).get("gp", 0) + (prev or {}).get("gp", 0)
        per_game = (gs + SHRINK_GAMES * repl) / (gp + SHRINK_GAMES)
        out[pid] = {
            "name": latest["name"], "team": team, "pos": latest["pos"],
            "gp": (cur or {}).get("gp", 0), "gp_last_season": (prev or {}).get("gp", 0),
            "value": round(GS_TO_GOALS * (per_game - repl), 4),
        }
    return out


# Lineup slots per game, for team_roster_strength().
LINEUP_SLOTS = {"F": 12, "D": 6}


def team_roster_strength(values, last, rosters, slots=LINEUP_SLOTS):
    """
    {team: goals/game its skaters add vs. a league-average roster}: each
    rostered skater's value (goals/game over replacement) times his
    expected share of games (last season's games / a full season). If a
    team's regulars at a position add up to more than its lineup slots
    (12 forwards, 6 defensemen), their shares are scaled down to fit, since
    some will sit; slots left over are filled at replacement level (0).
    Centered on the league. A WAR-style team rating: the sum of its players.
    """
    shares = defaultdict(lambda: defaultdict(list))  # team -> F/D -> [(value, share)]
    for pid, team in rosters.items():
        v = values.get(pid)
        played = min(last.get(pid, {}).get("gp", 0) / FULL_SEASON_GP, 1.0)
        if v and played:
            shares[team][position_group(v["pos"])].append((v["value"], played))
    totals = {}
    for team, groups in shares.items():
        total = 0.0
        for group, players in groups.items():
            weight = sum(s for _, s in players)
            scale = min(1.0, slots[group] / weight) if weight else 0.0
            total += scale * sum(v * s for v, s in players)
        totals[team] = total
    if not totals:
        return {}
    mean = sum(totals.values()) / len(totals)
    return {t: round(v - mean, 4) for t, v in totals.items()}


# Relocated franchises: last season's roster counts toward the new team.
FRANCHISE_MOVES = {"ARI": "UTA"}
FULL_SEASON_GP = 82


def roster_strength_change(last, before_last, rosters):
    """
    {team: goals/game gained (+) or lost (-) to roster moves since last
    season}. Each skater counts at his value (from last season and the one
    before) times his share of a full season played last year, so a regular
    who leaves costs more than a call-up. Players who stayed cancel out;
    newcomers with no NHL history count as replacement level (0).
    `rosters` is {player_id: team} now.
    """
    change = defaultdict(float)
    teams_now = set(rosters.values())
    for pid, v in player_values(last, before_last).items():
        played = min(last.get(pid, {}).get("gp", 0) / FULL_SEASON_GP, 1.0)
        if not played:
            continue
        old_team = v["team"] if v["team"] in teams_now else FRANCHISE_MOVES.get(v["team"], v["team"])
        new_team = rosters.get(pid)
        if new_team == old_team:
            continue
        change[old_team] -= v["value"] * played
        if new_team:
            change[new_team] += v["value"] * played
    return dict(change)


# Goalies: goals saved above expected (GSAx = xG against - goals against)
# per 60 minutes, from MoneyPuck's goalie season summaries. Year to year it
# barely repeats (r = 0.16 for 25+ GP, 2020-21 to 2025-26), so each goalie
# is pulled hard toward the regular-goalie average, GOALIE_SHRINK_GAMES
# pseudo-games of it. Fringe goalies (5-19 GP) run -0.217 per 60, and a
# goalie with no NHL history counts at that level.
MONEYPUCK_GOALIES_URL = "https://moneypuck.com/moneypuck/playerData/seasonSummary/{year}/regular/goalies.csv"
GOALIE_AVERAGE = 0.0
GOALIE_REPLACEMENT = -0.217
GOALIE_SHRINK_GAMES = 100   # backtested: 100 beat 50 and 250 (simulate_playoff_odds.GOALIE_WEIGHT)
GOALIE_NEWCOMER_GAMES = 5   # expected-starts weight for a goalie with no games last season


def season_goalies(csv_text):
    """{player_id: {"name", "team", "gp", "games", "gsax"}} ("games" = 60-minute games played)."""
    out = {}
    for row in csv.DictReader(io.StringIO(csv_text)):
        games = _f(row, "icetime") / 3600
        if row["situation"] != "all" or games <= 0:
            continue
        out[int(row["playerId"])] = {"name": row["name"], "team": row["team"], "gp": int(_f(row, "games_played")),
                                     "games": games, "gsax": _f(row, "xGoals") - _f(row, "goals")}
    return out


# The same from our own xG: each goalie's xG and goals against on the
# unblocked shots he faced (team_game_xg's play-by-play, xg_model.py), with
# games and teams from the NHL's goalie report.
NHL_GOALIE_URL = "https://api.nhle.com/stats/rest/en/goalie/summary?limit=-1&cayenneExp=seasonId={season}%20and%20gameTypeId=2"


def fetch_nhl_goalies(year):
    """[row]: each goalie's regular season (starting in `year`) from the NHL's goalie summary."""
    response = requests.get(NHL_GOALIE_URL.format(season=f"{year}{year + 1}"), timeout=60)
    response.raise_for_status()
    return response.json()["data"]


def xg_scale(faced):
    """League goals over league xG on the shots goalies faced: our xG's level that season (1.0 = right on)."""
    xga = sum(x for x, _ in faced.values())
    return sum(g for _, g in faced.values()) / xga if xga else 1.0


def our_season_goalies(nhl_rows, faced, scale=1.0):
    """
    season_goalies()'s shape from our xG: faced is {player_id: (xG against,
    goals against)}; xG is multiplied by `scale` (xg_scale() to put the
    league's GSAx at zero). A traded goalie's team is his last.
    """
    out = {}
    for row in nhl_rows:
        pid, games = int(row["playerId"]), (row.get("timeOnIce") or 0) / 3600
        if games <= 0 or pid not in faced:
            continue
        xga, ga = faced[pid]
        out[pid] = {"name": row.get("goalieFullName"), "team": (row.get("teamAbbrevs") or "").split(",")[-1],
                    "gp": int(row.get("gamesPlayed") or 0), "games": games, "gsax": scale * xga - ga}
    return out


def goalie_rates(last, before_last, shrink=GOALIE_SHRINK_GAMES):
    """{player_id: GSAx per 60 over the last two seasons, shrunk toward average}."""
    rates = {}
    for pid in set(last) | set(before_last):
        a, b = last.get(pid, {}), before_last.get(pid, {})
        gsax = a.get("gsax", 0) + b.get("gsax", 0)
        games = a.get("games", 0) + b.get("games", 0)
        rates[pid] = (gsax + shrink * GOALIE_AVERAGE) / (games + shrink)
    return rates


def team_goalie_strength(rates, last, rosters, starts=None, prior_starts=None):
    """
    {team: goals/game its goalies save vs. a league-average tandem}: each
    rostered goalie's rate weighted by who's expected in net (a newcomer
    gets GOALIE_NEWCOMER_GAMES at replacement level), centered on the
    league. The xG prior has no goaltending in it at all (xG only measures
    shots), so this is added in full, not as a change.

    Expected starts: with `starts` ({player_id: starts for his team this
    season}), each goalie's weight is his share of the team's games last
    season times `prior_starts`, plus his starts so far. Preseason that's
    last season's split; as games are played, this season's usage takes
    over, so a new starter rises and an injured one fades. Without
    `starts`, it's last season's games alone.

    The model doesn't pass `starts`: backtested 2026-10, every weighting of
    this season's starts was worse (the more weight, the worse), likely
    because this season's goals, half of each rating, already show who's
    been in net. Kept for the backtest ("roster+goalie-starts").
    """
    last_games = {pid: last.get(pid, {}).get("gp", 0) or GOALIE_NEWCOMER_GAMES for pid in rosters}
    team_last = defaultdict(float)
    for pid, team in rosters.items():
        team_last[team] += last_games[pid]
    totals = defaultdict(lambda: [0.0, 0.0])
    for pid, team in rosters.items():
        if starts is None:
            weight = last_games[pid]
        else:
            weight = prior_starts * last_games[pid] / team_last[team] + starts.get(pid, 0)
        totals[team][0] += weight * rates.get(pid, GOALIE_REPLACEMENT)
        totals[team][1] += weight
    level = {t: s / w for t, (s, w) in totals.items() if w}
    if not level:
        return {}
    mean = sum(level.values()) / len(level)
    return {t: round(v - mean, 4) for t, v in level.items()}


# Aging: the change in a skater's Game Score per game from one season to the
# next, by age on Feb 1 of the new season. Fit by --calibrate-aging (delta
# method: 4,063 pairs of consecutive 20+ GP seasons, 2018-19 to 2025-26,
# weighted by the harmonic mean of games played) as a cubic in (age - 27),
# ages clamped to 19-39. Young players improve (+0.13 at 19), the peak is
# about 25, and it falls off after 30 (-0.05 at 34).
#
# NOT used by the playoff model: backtested 2026-10 (backtest_playoff_odds.py,
# "roster+goalies+aging"), adding team_aging() to the prior made Brier worse
# at every weight and carryover tried. Likely survivor bias: a young player
# only forms a pair if he stayed in the NHL, so young gains are overstated
# (it rated Buffalo the top "aging gainer" two years running). Kept for a
# future fix, e.g. counting players who dropped out as declines.
AGING_CURVE = (-0.00978, -0.00845, 0.00075, -0.00005)
AGING_PIVOT = 27
AGING_AGES = (19, 39)
NHL_BIOS_URL = "https://api.nhle.com/stats/rest/en/skater/bios?limit=-1&cayenneExp=seasonId={season}%20and%20gameTypeId=2"


def age_on_feb1(birth_date, season_start):
    """Age on Feb 1 of the season starting in `season_start` (e.g. 2026 for 2026-27)."""
    year, month, day = (int(x) for x in str(birth_date)[:10].split("-"))
    return season_start + 1 - year - ((month, day) > (2, 1))


def aging_change(age, curve=AGING_CURVE):
    """Expected goals/game change in a skater's value this season, at this age."""
    x = min(max(age, AGING_AGES[0]), AGING_AGES[1]) - AGING_PIVOT
    return GS_TO_GOALS * sum(c * x ** k for k, c in enumerate(curve))


def team_aging(last, rosters, ages):
    """
    {team: goals/game its current skaters should gain or lose to aging},
    centered on the league. Each skater counts at his share of a full
    season played last year, like roster_strength_change(); players
    without a known age or last-season games count for nothing. Without
    this, a player who stayed cancelled out exactly, so a young core and an
    old one looked the same.
    """
    totals = defaultdict(float)
    for pid, team in rosters.items():
        played = min(last.get(pid, {}).get("gp", 0) / FULL_SEASON_GP, 1.0)
        if played and pid in ages:
            totals[team] += aging_change(ages[pid]) * played
    if not totals:
        return {}
    mean = sum(totals.values()) / len(totals)
    return {t: round(v - mean, 4) for t, v in totals.items()}


def fit_aging_curve(pairs, degree=3):
    """Weighted least squares of (age, change in GS/gp, weight) on a
    polynomial in (age - AGING_PIVOT), ages clamped like aging_change()."""
    n = degree + 1
    a = [[0.0] * n for _ in range(n)]
    b = [0.0] * n
    for age, change, weight in pairs:
        x = min(max(age, AGING_AGES[0]), AGING_AGES[1]) - AGING_PIVOT
        f = [x ** k for k in range(n)]
        for i in range(n):
            b[i] += weight * f[i] * change
            for j in range(n):
                a[i][j] += weight * f[i] * f[j]
    for i in range(n):  # Gaussian elimination; the normal equations are well conditioned here
        for j in range(i + 1, n):
            r = a[j][i] / a[i][i]
            a[j] = [aj - r * ai for aj, ai in zip(a[j], a[i])]
            b[j] -= r * b[i]
    coef = [0.0] * n
    for i in reversed(range(n)):
        coef[i] = (b[i] - sum(a[i][k] * coef[k] for k in range(i + 1, n))) / a[i][i]
    return coef


def aging_pairs(seasons_by_year, ages_by_year, min_gp=20):
    """(age, change in GS/gp, weight) for each skater's consecutive seasons."""
    pairs = []
    for year in sorted(seasons_by_year):
        before = seasons_by_year.get(year - 1)
        if not before:
            continue
        for pid, p in seasons_by_year[year].items():
            q = before.get(pid)
            age = ages_by_year.get(year, {}).get(pid)
            if q and age is not None and p["gp"] >= min_gp and q["gp"] >= min_gp:
                weight = 2 / (1 / p["gp"] + 1 / q["gp"])
                pairs.append((age, p["gs"] / p["gp"] - q["gs"] / q["gp"], weight))
    return pairs


def fetch_ages(season_start):
    """{player_id: age on Feb 1} for every skater who played that season (NHL stats API)."""
    season = f"{season_start}{season_start + 1}"
    response = requests.get(NHL_BIOS_URL.format(season=season), timeout=60)
    response.raise_for_status()
    return {r["playerId"]: age_on_feb1(r["birthDate"], season_start)
            for r in response.json()["data"] if r.get("birthDate")}


def calibrate(years, skaters=season_skaters, team_goals=fetch_nhl_team_goals):
    """Refit GS_TO_GOALS (team GD/game on team Game Score/game) and the replacement levels."""
    xs, ys, fringe = [], [], defaultdict(lambda: [0.0, 0])
    for year in years:
        players = skaters(year)
        team_gs = defaultdict(float)
        for p in players.values():
            team_gs[p["team"]] += p["gs"]
            if FRINGE_GP[0] <= p["gp"] < FRINGE_GP[1]:
                group = fringe[position_group(p["pos"])]
                group[0] += p["gs"]
                group[1] += p["gp"]
        for team, (gd, gp) in team_goals(year).items():
            xs.append(team_gs[team] / gp)
            ys.append(gd / gp)
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    syy = sum((y - my) ** 2 for y in ys)
    return {
        "team_seasons": n,
        "gs_to_goals": round(sxy / sxx, 3),
        "r": round(sxy / (sxx * syy) ** 0.5, 2),
        "replacement_gs": {k: round(gs / gp, 3) for k, (gs, gp) in fringe.items()},
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--calibrate", action="store_true")
    parser.add_argument("--calibrate-aging", action="store_true", help="Refit AGING_CURVE (8 seasons)")
    parser.add_argument("--top", type=int, default=0)
    parser.add_argument("--season-start", type=int, default=None, help="e.g. 2026 for 2026-27 (default: current)")
    args = parser.parse_args()
    from simulate_playoff_odds import current_season_id

    start = args.season_start or current_season_id() // 10000
    if args.calibrate:
        print(calibrate([start - 3, start - 2, start - 1]))
    if args.calibrate_aging:
        years = range(start - 8, start)
        seasons = {y: season_skaters(y) for y in years}
        pairs = aging_pairs(seasons, {y: fetch_ages(y) for y in years})
        print({"pairs": len(pairs), "curve": [round(c, 5) for c in fit_aging_curve(pairs)]})
    if args.top:
        values = player_values(season_skaters(start), season_skaters(start - 1))
        for pid, v in sorted(values.items(), key=lambda kv: -kv[1]["value"])[: args.top]:
            print(f"{v['name']:24} {v['team']} {v['pos']}  {v['value']:+.3f} goals/game")


if __name__ == "__main__":
    main()
