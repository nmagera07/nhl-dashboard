from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel


class PlayoffOdds(BaseModel):
    """
    One team's playoff-odds simulation result, as returned by GET /playoff-odds.
    Always the latest as_of_date for the latest season_id -- see the query's
    WHERE clause, which is the source of truth for that "latest" selection.
    """

    id: int
    season_id: int
    as_of_date: date
    team_abbrev: str
    playoff_pct: float
    trials: int
    computed_at: datetime

    # Joined in from `teams`.
    team_name: str
    division: Optional[str] = None
    conference: Optional[str] = None
    logo_url: Optional[str] = None
