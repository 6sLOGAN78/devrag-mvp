"""Fixed-window rate limiter on the stack's Valkey (plan 03-10; D-29, research security domain V13).

``FixedWindowLimiter.hit`` counts one event under a key and raises ``RateLimited`` once the window's limit is exceeded. It
fails closed: any Valkey or network failure raises ``RateLimitUnavailable`` so an outage can never switch a limit off. A
client is created per call and closed in ``finally`` (calls are rare and may come from any worker thread). The window starts
at the first hit (``EXPIRE ... NX``) and later hits do not extend it. This module imports nothing from api, rag or quart.
"""

from __future__ import annotations

import valkey
from valkey.exceptions import ValkeyError

from common.settings import RedisSettings

SOCKET_TIMEOUT_SECONDS = 2


class RateLimited(Exception):
    """The window's limit is used up; ``retry_after`` is the whole seconds until it resets (at least 1)."""

    def __init__(self, retry_after: float) -> None:
        super().__init__("rate limited")
        self.retry_after = retry_after


class RateLimitUnavailable(Exception):
    """The counter store cannot be reached, so the caller must refuse the action (fail closed)."""


class FixedWindowLimiter:
    def __init__(self, redis: RedisSettings) -> None:
        self._redis = redis

    def _client(self) -> valkey.Valkey:
        rd = self._redis
        return valkey.Valkey(
            host=rd.host,
            port=rd.port,
            password=rd.password or None,
            db=rd.db,
            socket_timeout=SOCKET_TIMEOUT_SECONDS,
            socket_connect_timeout=SOCKET_TIMEOUT_SECONDS,
        )

    def hit(self, key: str, limit: int, window_seconds: int) -> None:
        client = self._client()
        try:
            pipe = client.pipeline(transaction=True)
            pipe.incr(key)
            pipe.expire(key, window_seconds, nx=True)
            pipe.ttl(key)
            count, _, ttl = pipe.execute()
        except (ValkeyError, OSError):
            raise RateLimitUnavailable("rate limit store unavailable") from None
        finally:
            client.close()
        if int(count) > limit:
            raise RateLimited(retry_after=max(1, int(ttl) if int(ttl) > 0 else window_seconds))
