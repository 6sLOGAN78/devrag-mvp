"""Response envelope helpers: every Python response is ``{code, message, data}`` (D-13)."""
from __future__ import annotations

import json
from typing import Any

from quart import Response

from common.constants import RetCode

_HTTP_FOR_CODE = {
    RetCode.BAD_REQUEST: 400,
    RetCode.ARGUMENT_ERROR: 400,
    RetCode.UNAUTHORIZED: 401,
    RetCode.AUTHENTICATION_ERROR: 401,
    RetCode.FORBIDDEN: 403,
    RetCode.PERMISSION_ERROR: 403,
    RetCode.NOT_FOUND: 404,
    RetCode.METHOD_NOT_ALLOWED: 405,
    RetCode.CONFLICT: 409,
    RetCode.SERVER_ERROR: 500,
    RetCode.SERVICE_UNAVAILABLE: 503,
}


def http_status_for(code: int) -> int:
    """HTTP status for an envelope code; legacy application codes map to 200 unless listed."""
    return _HTTP_FOR_CODE.get(code, 200) if code != RetCode.SUCCESS else 200  # type: ignore[call-overload]


def _envelope(code: int, message: str, data: Any, status: int) -> Response:
    # json.dumps keeps the documented key order (code, message, data); Quart's provider sorts keys.
    body = json.dumps({"code": int(code), "message": message, "data": data}, ensure_ascii=False, default=str)
    return Response(body, status=status, mimetype="application/json")


def json_result(data: Any = None, message: str = "", code: int = RetCode.SUCCESS, http_status: int | None = None) -> Response:
    return _envelope(code, message, data, http_status if http_status is not None else http_status_for(code))


def error_result(code: int, message: str, http_status: int | None = None, data: Any = None) -> Response:
    return _envelope(code, message, data, http_status if http_status is not None else http_status_for(code))
