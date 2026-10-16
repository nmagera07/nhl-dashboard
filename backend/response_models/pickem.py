"""Request bodies for the pick'em routes. Keys travel in bodies, never URLs."""

from datetime import date
from typing import Optional

from pydantic import BaseModel, Field


class PickemJoinIn(BaseModel):
    name: str = Field(..., max_length=40)


class PickemMeIn(BaseModel):
    key: str = Field(..., max_length=100)
    day: Optional[date] = Field(None, alias="date")  # which day's picks to return (default: today, Eastern)


class PickemPickIn(BaseModel):
    key: str = Field(..., max_length=100)
    game_id: int = Field(..., gt=0)
    team: str = Field(..., min_length=2, max_length=3)
