"""Typed service errors that handlers map to HTTP answers (plan 03-09).

Services raise ``ServiceError`` with a ``Kind`` (the intent), a stable machine ``reason`` (see ``api.utils.reasons``)
and a short ``message`` meant for the user. Messages must never contain keys, urls, provider bodies or SQL; this module
cannot enforce that, so every raise site is responsible. ``str(error)`` returns only the reason so a logged exception
cannot leak anything the message might have held. Services do not import quart: the handler owns the status code.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any


class Kind(StrEnum):
    NOT_FOUND = "not_found"
    FORBIDDEN = "forbidden"
    CONFLICT = "conflict"
    INVALID = "invalid"
    RATE_LIMITED = "rate_limited"
    TIMEOUT = "timeout"
    UNAVAILABLE = "unavailable"
    PAYLOAD_TOO_LARGE = "payload_too_large"
    BAD_GATEWAY = "bad_gateway"


class ServiceError(Exception):
    def __init__(self, kind: Kind, reason: str, message: str, *, retry_after: float | None = None, data: dict[str, Any] | None = None) -> None:
        super().__init__(reason)
        self.kind = kind
        self.reason = reason
        self.message = message
        self.retry_after = retry_after
        self.data = data

    def __str__(self) -> str:
        return self.reason

    def __repr__(self) -> str:
        return f"ServiceError(kind={self.kind.value!r}, reason={self.reason!r})"
