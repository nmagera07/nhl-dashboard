from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel


class PlayerBio(BaseModel):
    """Columns straight off the `players` table -- current roster only."""

    player_id: int
    team_abbrev: str
    first_name: str
    last_name: str
    position_code: str
    sweater_number: Optional[int] = None
    shoots_catches: Optional[str] = None
    height_in_inches: Optional[int] = None
    weight_in_pounds: Optional[int] = None
    birth_date: Optional[date] = None
    birth_city: Optional[str] = None
    birth_country: Optional[str] = None
    headshot_url: Optional[str] = None
    updated_at: datetime


class LatestSeasonStatsFields(BaseModel):
    """
    The single latest player_season_stats row, flattened onto the player's
    own row by a `LEFT JOIN LATERAL ... LIMIT 1`. Every field here is
    Optional for two independent reasons:
      - the LEFT JOIN means a player with no season_stats row at all yields
        NULL for every one of these columns (season_id included).
      - skater and goalie stats share one table (see schema.sql), so a
        skater's row has wins/losses/goals_against_avg/etc as NULL, and a
        goalie's row has goals/assists/points/etc as NULL.
    """

    season_id: Optional[int] = None
    games_played: Optional[int] = None
    # skater stats
    goals: Optional[int] = None
    assists: Optional[int] = None
    points: Optional[int] = None
    plus_minus: Optional[int] = None
    pim: Optional[int] = None
    shots: Optional[int] = None
    shooting_pctg: Optional[float] = None
    power_play_goals: Optional[int] = None
    power_play_points: Optional[int] = None
    shorthanded_goals: Optional[int] = None
    shorthanded_points: Optional[int] = None
    game_winning_goals: Optional[int] = None
    ot_goals: Optional[int] = None
    # goalie stats
    wins: Optional[int] = None
    losses: Optional[int] = None
    ot_losses: Optional[int] = None
    goals_against_avg: Optional[float] = None
    save_pctg: Optional[float] = None
    shutouts: Optional[int] = None


class RosterPlayer(PlayerBio, LatestSeasonStatsFields):
    """One player in GET /teams/{team_abbrev}/roster."""


class PlayerLeader(PlayerBio, LatestSeasonStatsFields):
    """
    One player in GET /players/leaders -- same shape as RosterPlayer plus
    the team fields joined in since this endpoint isn't scoped to one team.
    """

    team_name: str
    team_logo_url: Optional[str] = None


class PlayerSeasonStat(BaseModel):
    """One row of `player_season_stats`, as nested under GET /players/{player_id}."""

    id: int
    player_id: int
    season_id: int
    games_played: Optional[int] = None
    goals: Optional[int] = None
    assists: Optional[int] = None
    points: Optional[int] = None
    plus_minus: Optional[int] = None
    pim: Optional[int] = None
    shots: Optional[int] = None
    shooting_pctg: Optional[float] = None
    power_play_goals: Optional[int] = None
    power_play_points: Optional[int] = None
    shorthanded_goals: Optional[int] = None
    shorthanded_points: Optional[int] = None
    game_winning_goals: Optional[int] = None
    ot_goals: Optional[int] = None
    wins: Optional[int] = None
    losses: Optional[int] = None
    ot_losses: Optional[int] = None
    goals_against_avg: Optional[float] = None
    save_pctg: Optional[float] = None
    shutouts: Optional[int] = None
    updated_at: datetime


class PlayerAdvancedStat(BaseModel):
    """
    The current season's row of `player_advanced_stats`, as nested under
    GET /players/{player_id} -- sourced from MoneyPuck's public seasonSummary
    CSVs (see ingest_advanced_stats.py), 5-on-5 situation only. Skaters only;
    goalies never have a row here (on-ice possession shares aren't a
    meaningful goalie stat). Every field is Optional because a rookie or a
    player MoneyPuck hasn't published a row for yet still has a valid 200
    response -- see PlayerDetail's advanced_stats field for the
    None-if-missing pattern this follows (same shape as career_totals).
    """

    season_id: int
    games_played: Optional[int] = None
    icetime_seconds: Optional[int] = None
    corsi_for_pct: Optional[float] = None
    fenwick_for_pct: Optional[float] = None
    xgoals_for_pct: Optional[float] = None
    xgoals_for: Optional[float] = None
    xgoals_against: Optional[float] = None
    individual_xgoals: Optional[float] = None
    pdo: Optional[float] = None


class CareerTotalsStats(BaseModel):
    """
    One season-type slice (regular season OR playoffs) of a player's
    career totals, from player_career_totals. Same skater/goalie split
    and nullability reasoning as LatestSeasonStatsFields -- skater and
    goalie stats share one table, so whichever doesn't apply to this
    player's position stays NULL. DB columns not relevant to the API
    response (id, player_id, season_type, updated_at) are simply not
    declared here -- Pydantic drops unrecognized fields by default, so
    passing the full raw DB row straight through is safe.
    """

    games_played: Optional[int] = None
    goals: Optional[int] = None
    assists: Optional[int] = None
    points: Optional[int] = None
    plus_minus: Optional[int] = None
    pim: Optional[int] = None
    shots: Optional[int] = None
    shooting_pctg: Optional[float] = None
    power_play_goals: Optional[int] = None
    power_play_points: Optional[int] = None
    shorthanded_goals: Optional[int] = None
    shorthanded_points: Optional[int] = None
    game_winning_goals: Optional[int] = None
    ot_goals: Optional[int] = None
    wins: Optional[int] = None
    losses: Optional[int] = None
    ot_losses: Optional[int] = None
    goals_against_avg: Optional[float] = None
    save_pctg: Optional[float] = None
    shutouts: Optional[int] = None


class CareerTotals(BaseModel):
    """
    GET /players/{id}'s career_totals field. Either sub-object is None
    when the player has no row for that season type at all -- e.g. a
    rookie (or any player who's never made the playoffs) has
    playoffs=None, not a zero-filled object. A player with zero
    player_career_totals rows whatsoever (ingestion hasn't run for them
    yet) gets regular_season=None, playoffs=None -- both None, not the
    whole career_totals field omitted, so PlayerDetail can declare this
    as a plain nested object that's simply empty rather than Optional
    itself.
    """

    regular_season: Optional[CareerTotalsStats] = None
    playoffs: Optional[CareerTotalsStats] = None


class SeasonHistoryEntry(BaseModel):
    """
    One (season, season_type) row from player_season_history -- one
    season's regular-season or playoffs line, filtered to the NHL only.
    Same skater/goalie nullability split as CareerTotalsStats. A
    mid-season trade's multiple real per-team entries are already
    combined into this single row by ingest_player_stats.py's
    upsert_season_history() -- counting stats summed, shooting_pctg and
    goalie rate stats recomputed from underlying counts, not averaged.
    """

    season_id: int
    season_type: str
    games_played: Optional[int] = None
    goals: Optional[int] = None
    assists: Optional[int] = None
    points: Optional[int] = None
    plus_minus: Optional[int] = None
    pim: Optional[int] = None
    shots: Optional[int] = None
    shooting_pctg: Optional[float] = None
    power_play_goals: Optional[int] = None
    power_play_points: Optional[int] = None
    shorthanded_goals: Optional[int] = None
    shorthanded_points: Optional[int] = None
    game_winning_goals: Optional[int] = None
    ot_goals: Optional[int] = None
    wins: Optional[int] = None
    losses: Optional[int] = None
    ot_losses: Optional[int] = None
    goals_against_avg: Optional[float] = None
    save_pctg: Optional[float] = None
    shutouts: Optional[int] = None


class PlayerDetail(PlayerBio):
    """
    GET /players/{player_id}. 404s (not an empty body) when the player_id
    doesn't exist -- see the endpoint's explicit HTTPException.

    season_stats is a genuinely nested list (unlike the flattened
    single-row join used by RosterPlayer/PlayerLeader) because the endpoint
    runs a separate follow-up query and assigns its full fetchall() result
    onto the player dict -- a player can have multiple season rows (one per
    season_id) and 0 rows is valid (e.g. a rookie), not an error.

    advanced_stats is None (not an empty list) when MoneyPuck has no row
    for this player/season yet -- goalies always get None, since
    player_advanced_stats is skater-only -- following the same
    None-if-missing shape as career_totals below, rather than
    season_stats' possibly-empty-list shape, since this is always at most
    one row (the current season only, not a history).

    career_totals is always present as an object -- even a player with zero
    player_career_totals rows gets {"regular_season": None, "playoffs": None}
    rather than the field being omitted, see CareerTotals.

    season_history is a third, separately-nested list -- one row per
    player_season_history row (regular season and playoffs kept as
    separate entries, most recent season first) -- covering every NHL
    season the player has ever played, not just the current one like
    season_stats. 0 rows is valid (ingestion hasn't backfilled this
    player's history yet), same as season_stats.
    """

    team_name: str
    team_logo_url: Optional[str] = None
    season_stats: List[PlayerSeasonStat]
    advanced_stats: Optional[PlayerAdvancedStat] = None
    career_totals: CareerTotals
    season_history: List[SeasonHistoryEntry]
