"""Access-token contract shared with Go (internal/common/token.go).

The wire format is itsdangerous URLSafeTimedSerializer: zlib-compressed JSON string,
big-endian minimal Unix timestamp, HMAC-SHA1 signature. Vectors live in
test/fixtures/access_token_vectors.json and are verified by both stacks.
"""

from __future__ import annotations

from itsdangerous import BadData, TimestampSigner, URLSafeTimedSerializer

MAX_AGE_SECONDS = 2_592_000  # 30 days (D-11)
MAX_TOKEN_LENGTH = 1024
MIN_INNER_LENGTH = 32
INVALID_PREFIX = "INVALID_"


def _serializer(secret: str, now: int | None) -> URLSafeTimedSerializer:
    class _Signer(TimestampSigner):
        def get_timestamp(self) -> int:
            return now if now is not None else super().get_timestamp()

    return URLSafeTimedSerializer(secret, signer=_Signer)


def dump(inner: str, secret: str, now: int | None = None) -> str:
    return _serializer(secret, now).dumps(inner)


def verify(token: str, secret: str, max_age: int = MAX_AGE_SECONDS, now: int | None = None) -> str | None:
    """Return the inner string for a valid, unexpired token; None otherwise.

    ``now`` is injected for tests.
    """
    if not isinstance(token, str) or not token or len(token) > MAX_TOKEN_LENGTH:
        return None
    if not secret:
        return None
    try:
        # itsdangerous also rejects timestamps in the future (age < 0).
        value = _serializer(secret, now).loads(token, max_age=max_age)
    except BadData:
        return None
    return value if isinstance(value, str) else None


def valid_inner(value: object) -> bool:
    """AUTH-08: trimmed non-empty, length >= 32, not starting with INVALID_."""
    if not isinstance(value, str):
        return False
    if not value.strip() or len(value) < MIN_INNER_LENGTH:
        return False
    return not value.startswith(INVALID_PREFIX)
