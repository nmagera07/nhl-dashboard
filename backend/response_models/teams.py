from typing import Optional

from pydantic import BaseModel


class Team(BaseModel):
    """One row of the `teams` table, as returned by GET /teams."""

    team_abbrev: str
    team_name: str
    common_name: Optional[str] = None
    place_name: Optional[str] = None
    conference: Optional[str] = None
    division: Optional[str] = None
    logo_url: Optional[str] = None
