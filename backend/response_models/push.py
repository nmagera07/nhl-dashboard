from typing import List

from pydantic import BaseModel, Field


class PushKeys(BaseModel):
    p256dh: str = Field(..., max_length=200)
    auth: str = Field(..., max_length=100)


class PushSubscriptionIn(BaseModel):
    """What the browser's PushManager.subscribe() returns, plus preferences."""

    endpoint: str = Field(..., max_length=1000)
    keys: PushKeys
    teams: List[str] = Field(..., min_length=1, max_length=32)
    goals: bool = True
    finals: bool = True


class PushUnsubscribeIn(BaseModel):
    endpoint: str = Field(..., max_length=1000)
