"""Maps typed service errors to the ``{code, message, data}`` answers handlers return (plan 03-12, D-19, D-20, Pitfall 7).

One table, one place. ``NOT_FOUND`` is always the same body whatever the reason, so an absent id, another workspace's id and an
unconfigured provider cannot be told apart (D-20). No mapping produces an authentication failure, in the status or in the envelope code: a refused
provider configuration must not look like an expired session to the SPA. ``data`` carries the machine ``reason`` and nothing derived from the
exception object, so no class name or text of the cause can reach a client.
"""
from __future__ import annotations

import math

from quart import Response

from api.apps.errors import forbidden_response
from api.db.services.service_errors import Kind, ServiceError
from api.utils.api_utils import error_result
from common.constants import RetCode

NOT_FOUND_MESSAGE = "not found"

# kind -> (envelope code, HTTP status)
_TABLE: dict[Kind, tuple[RetCode, int]] = {
    Kind.INVALID: (RetCode.ARGUMENT_ERROR, 400),
    Kind.CONFLICT: (RetCode.CONFLICT, 409),
    Kind.PAYLOAD_TOO_LARGE: (RetCode.BAD_REQUEST, 413),
    Kind.RATE_LIMITED: (RetCode.BAD_REQUEST, 429),
    Kind.UNAVAILABLE: (RetCode.SERVICE_UNAVAILABLE, 503),
    Kind.TIMEOUT: (RetCode.SERVER_ERROR, 504),
    Kind.BAD_GATEWAY: (RetCode.SERVER_ERROR, 502),
}


def not_found_response() -> Response:
    return error_result(RetCode.NOT_FOUND, NOT_FOUND_MESSAGE, 404)


def _retry_after_seconds(seconds: float) -> str:
    """Whole seconds, at least one. ``0.0`` is a real value ("retry now"), not absence."""
    return str(max(1, math.ceil(seconds)))


def service_error_response(exc: ServiceError) -> Response:
    if exc.kind is Kind.NOT_FOUND:
        return not_found_response()
    if exc.kind is Kind.FORBIDDEN:
        return forbidden_response()
    code, status = _TABLE.get(exc.kind, (RetCode.SERVER_ERROR, 500))
    response = error_result(code, exc.message, status, data={"reason": exc.reason, **(exc.data or {})})
    if exc.retry_after is not None:
        response.headers["Retry-After"] = _retry_after_seconds(exc.retry_after)
    return response
