"""Request body for POST /feedback."""

from typing import Literal, Optional

from pydantic import BaseModel, Field


class FeedbackIn(BaseModel):
    kind: Literal["idea", "bug"]
    message: str = Field(..., min_length=3, max_length=2000)  # trimmed to 1000 when stored
    contact: Optional[str] = Field(None, max_length=200)
    page: Optional[str] = Field(None, max_length=300)
    # Honeypot: hidden from people, so only bots fill it in.
    website: Optional[str] = Field(None, max_length=300)
