"""Request body for POST /post-kit/{day}/actions."""

from typing import Literal

from pydantic import BaseModel, Field


class PostActionIn(BaseModel):
    # What the owner did in the post kit: tapped Post on X / Post on Reddit, or copied the text or title.
    action: Literal["posted_x", "copied_x", "posted_reddit", "copied_reddit"]
    text: str = Field(..., min_length=1, max_length=600)  # the X text (as edited) or the Reddit title
    creator_key: str = Field(..., max_length=200)  # only the owner's devices (push.is_creator_key)
