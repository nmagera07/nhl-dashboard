from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel


class StandingsSnapshotFields(BaseModel):
    """Columns straight off the `standings_snapshots` table."""

    id: int
    snapshot_date: date
    team_abbrev: str
    season_id: int
    games_played: Optional[int] = None
    wins: Optional[int] = None
    losses: Optional[int] = None
    ot_losses: Optional[int] = None
    points: Optional[int] = None
    point_pctg: Optional[float] = None
    goal_for: Optional[int] = None
    goal_against: Optional[int] = None
    goal_differential: Optional[int] = None
    home_wins: Optional[int] = None
    home_losses: Optional[int] = None
    road_wins: Optional[int] = None
    road_losses: Optional[int] = None
    l10_wins: Optional[int] = None
    l10_losses: Optional[int] = None
    l10_ot_losses: Optional[int] = None
    streak_code: Optional[str] = None
    streak_count: Optional[int] = None
    division_sequence: Optional[int] = None
    conference_sequence: Optional[int] = None
    league_sequence: Optional[int] = None
    wildcard_sequence: Optional[int] = None
    created_at: datetime


class StandingsLatestRow(StandingsSnapshotFields):
    """
    One team in GET /standings/latest -- the most recent snapshot_date for
    every team, joined with team metadata.
    """

    team_name: str
    common_name: Optional[str] = None
    division: Optional[str] = None
    conference: Optional[str] = None
    logo_url: Optional[str] = None


class StandingsHistoryRow(StandingsSnapshotFields):
    """
    One day's snapshot for one team in GET /standings/{team_abbrev}
    (optionally date-filtered via ?start=&end=).

    404s only when team_abbrev isn't a real team (checked against `teams`
    directly). A real team with no snapshot rows yet -- or none in the
    given start/end range -- returns an empty 200 list instead, matching
    GET /teams/{team_abbrev}/roster and GET /standings/{team_abbrev}/seasons.
    """

    team_name: str


class SeasonFinalStanding(BaseModel):
    """
    One completed season's final standing for one team, as returned by
    GET /standings/{team_abbrev}/seasons. Always returns an empty 200 list
    (never 404s) when team_abbrev has no rows, deliberately unlike
    StandingsHistoryRow -- team_abbrev is not a foreign key on this table
    (relocated/renamed franchises like 'ARI' are tracked under their
    historical abbreviation, which no longer exists in `teams`), so there's
    no reliable way to validate "is this a real team" here without breaking
    legitimate historical lookups. No team metadata is joined in here the
    way it is for StandingsLatestRow, for the same reason.
    """

    id: int
    season_id: int
    team_abbrev: str
    games_played: Optional[int] = None
    wins: Optional[int] = None
    losses: Optional[int] = None
    ot_losses: Optional[int] = None
    points: Optional[int] = None
    point_pctg: Optional[float] = None
    goal_for: Optional[int] = None
    goal_against: Optional[int] = None
    goal_differential: Optional[int] = None
    division_sequence: Optional[int] = None
    conference_sequence: Optional[int] = None
    league_sequence: Optional[int] = None
    made_playoffs: bool
    created_at: datetime
