"""
Small in-process TTL cache for read endpoints whose data changes once a day
(the daily ingest runs at 06:00 UTC). Each API replica keeps its own copy.

- Entries expire after DAILY_CACHE_TTL_SECONDS (default 600 = 10 minutes).
- At most DAILY_CACHE_MAX_ENTRIES (default 256) entries, least recently used
  evicted first, so cycling query strings can't grow memory without bound.
- Thread safe: FastAPI runs sync endpoints in a thread pool, so all access
  goes through one lock. A miss computes outside the lock (two concurrent
  misses may both hit the DB once; the later result wins -- harmless).
- Only successful results are stored; an exception (404, DB error) is never
  cached.
- DAILY_CACHE_DISABLED=1 (or true/yes) turns it off: every call computes.
"""

import functools
import os
import threading
import time
from collections import OrderedDict

from starlette.requests import Request
from starlette.responses import Response


def _env_disabled():
    return (os.environ.get("DAILY_CACHE_DISABLED") or "").strip().lower() in ("1", "true", "yes", "on")


class TTLCache:
    def __init__(self, ttl_seconds=600.0, max_entries=256, enabled=True, clock=time.monotonic):
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries
        self.enabled = enabled
        self._clock = clock
        self._data: OrderedDict = OrderedDict()  # key -> (expires_at, value)
        self._lock = threading.Lock()

    def get_or_compute(self, key, compute):
        if not self.enabled:
            return compute()
        now = self._clock()
        with self._lock:
            hit = self._data.get(key)
            if hit is not None:
                if hit[0] > now:
                    self._data.move_to_end(key)
                    return hit[1]
                del self._data[key]
        value = compute()
        with self._lock:
            self._data[key] = (self._clock() + self.ttl_seconds, value)
            self._data.move_to_end(key)
            while len(self._data) > self.max_entries:
                self._data.popitem(last=False)
        return value

    def clear(self):
        with self._lock:
            self._data.clear()

    def __len__(self):
        with self._lock:
            return len(self._data)


cache = TTLCache(
    ttl_seconds=float(os.environ.get("DAILY_CACHE_TTL_SECONDS") or "600"),
    max_entries=int(os.environ.get("DAILY_CACHE_MAX_ENTRIES") or "256"),
    enabled=not _env_disabled(),
)


def daily_cached(func):
    """
    Cache an endpoint's result in `cache`, keyed by the endpoint and its
    arguments (a query parameter like ?view=table or ?sort_by=... gets its own
    entry; the Request object a rate-limited endpoint takes is left out of the
    key). Put it directly above the function, under @app.get and
    @limiter.limit, so rate limits still apply to cached responses.
    Exceptions propagate and are never cached. A Response the endpoint builds
    itself is stored as its parts and rebuilt per request, so no two requests
    share one Response object.
    """
    store = cache  # the object api.py imports, even if this module is reloaded later

    @functools.wraps(func)  # keeps the signature FastAPI reads for parameters
    def wrapper(*args, **kwargs):
        key = (func.__name__,) + tuple(sorted((k, v) for k, v in kwargs.items() if not isinstance(v, Request)))
        value = store.get_or_compute(key, lambda: _storable(func(*args, **kwargs)))
        return _servable(value)
    return wrapper


class _StoredResponse:
    __slots__ = ("body", "status_code", "media_type", "headers")

    def __init__(self, response):
        self.body = response.body
        self.status_code = response.status_code
        self.media_type = response.media_type
        self.headers = {k: v for k, v in response.headers.items() if k.lower() != "content-length"}


def _storable(value):
    return _StoredResponse(value) if isinstance(value, Response) else value


def _servable(value):
    if isinstance(value, _StoredResponse):
        return Response(content=value.body, status_code=value.status_code, media_type=value.media_type, headers=value.headers)
    return value
