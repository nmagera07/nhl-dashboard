"""
Web Push: validating browser subscriptions and sending notifications.

A subscription is the browser's private "push address" (an endpoint URL on
Apple's, Google's, Mozilla's, or Microsoft's push service) plus two keys used
to encrypt the message so only that browser can read it. Messages are signed
with this app's VAPID key pair; the public half is given to browsers when
they subscribe, the private half only lives in the notifier job's secrets.
"""

import json
import logging
import os
import re
from urllib.parse import urlparse

from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

VAPID_PUBLIC_KEY = os.getenv("VAPID_PUBLIC_KEY", "")
VAPID_PRIVATE_KEY = os.getenv("VAPID_PRIVATE_KEY", "")
VAPID_SUBJECT = os.getenv("VAPID_SUBJECT", "mailto:nhl-dashboard@users.noreply.github.com")

# The server POSTs to whatever endpoint a subscription names, so only real
# browser push services are accepted -- otherwise anyone could register an
# arbitrary URL and make the notifier send requests to it.
PUSH_SERVICE_HOSTS = (
    "fcm.googleapis.com",                 # Chrome, Edge (Android), most Android browsers
    "jmt17.google.com",                   # Google's push service for open-source Chromium builds
    "updates.push.services.mozilla.com",  # Firefox
    "web.push.apple.com",                 # Safari, iOS home-screen apps
    ".notify.windows.com",                # Edge on Windows (WNS)
)

_B64URL = re.compile(r"^[A-Za-z0-9_-]+={0,2}$")


class SubscriptionGone(Exception):
    """The push service says this subscription no longer exists (404/410)."""


def is_allowed_endpoint(endpoint: str) -> bool:
    try:
        url = urlparse(endpoint)
    except ValueError:
        return False
    host = (url.hostname or "").lower()
    if url.scheme != "https" or not host or url.port not in (None, 443):
        return False
    return any(host == h or (h.startswith(".") and host.endswith(h)) for h in PUSH_SERVICE_HOSTS)


def valid_keys(p256dh: str, auth: str) -> bool:
    """The browser's encryption keys: base64url, a 65-byte P-256 key and a 16-byte secret."""
    return (
        bool(_B64URL.match(p256dh or "")) and 80 <= len(p256dh) <= 100
        and bool(_B64URL.match(auth or "")) and 20 <= len(auth) <= 30
    )


def send(subscription: dict, payload: dict, ttl: int = 600) -> None:
    """
    Send one notification. subscription: {endpoint, p256dh, auth}. Raises
    SubscriptionGone when the browser has unsubscribed, so the caller can
    delete it; other failures are logged and swallowed (one bad device
    shouldn't stop everyone else's notifications).
    """
    from pywebpush import WebPushException, webpush

    if not is_allowed_endpoint(subscription["endpoint"]):
        raise SubscriptionGone("endpoint is not a known push service")
    try:
        webpush(
            subscription_info={
                "endpoint": subscription["endpoint"],
                "keys": {"p256dh": subscription["p256dh"], "auth": subscription["auth"]},
            },
            data=json.dumps(payload),
            vapid_private_key=VAPID_PRIVATE_KEY,
            vapid_claims={"sub": VAPID_SUBJECT},
            ttl=ttl,  # a goal alert an hour late is noise; let the push service drop it
            timeout=10,
        )
    except WebPushException as exc:
        status = getattr(exc.response, "status_code", None)
        if status in (404, 410):
            raise SubscriptionGone(str(status)) from exc
        logger.warning("Push to %s failed (%s)", urlparse(subscription["endpoint"]).hostname, status or exc)
