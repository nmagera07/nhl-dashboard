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
    # What to be alerted about (all on unless the device's alert settings say otherwise).
    starts: bool = True         # puck drop
    goals: bool = True          # goals by the followed teams
    goals_against: bool = True  # goals by their opponents
    finals: bool = True


class PushUnsubscribeIn(BaseModel):
    endpoint: str = Field(..., max_length=1000)


class PushReceiptIn(BaseModel):
    """The service worker's report that a push arrived: its subscription, and the alert's event key."""

    endpoint: str = Field(..., max_length=1000)
    key: str = Field(..., max_length=100, pattern=r"^[a-z-]+:[A-Za-z0-9:-]+$")


class PushRenewIn(BaseModel):
    """The service worker's pushsubscriptionchange: the browser replaced a subscription."""

    old_endpoint: str = Field(..., max_length=1000)
    endpoint: str = Field(..., max_length=1000)
    keys: PushKeys
