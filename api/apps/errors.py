"""Maps every failure to the ``{code, message, data}`` envelope with the real HTTP status (API-03, API-09)."""
from __future__ import annotations

import logging

from quart import Quart, Response
from quart_schema import RequestSchemaValidationError
from werkzeug.exceptions import BadRequest, HTTPException

from api.utils.api_utils import error_result
from common.constants import RetCode

logger = logging.getLogger(__name__)

_CODE_FOR_STATUS = {
    400: RetCode.BAD_REQUEST,
    401: RetCode.UNAUTHORIZED,
    403: RetCode.FORBIDDEN,
    404: RetCode.NOT_FOUND,
    405: RetCode.METHOD_NOT_ALLOWED,
    409: RetCode.CONFLICT,
    # No dedicated members (Go parity table); client errors stay in the 4xx class (R-63).
    413: RetCode.BAD_REQUEST,
    429: RetCode.BAD_REQUEST,
}
_MESSAGE_FOR_STATUS = {
    400: "bad request",
    401: "unauthorized",
    403: "forbidden",
    404: "not found",
    405: "method not allowed",
    409: "conflict",
    413: "payload too large",
    429: "too many requests",
}
INVALID_REQUEST = "invalid request"
INTERNAL_ERROR = "internal error"


def register_error_handlers(app: Quart) -> None:
    @app.errorhandler(RequestSchemaValidationError)
    async def _validation(_exc: RequestSchemaValidationError) -> Response:
        # Never echo the offending input (SEC-10).
        return error_result(RetCode.ARGUMENT_ERROR, INVALID_REQUEST, 400)

    @app.errorhandler(BadRequest)
    async def _bad_request(_exc: BadRequest) -> Response:
        # Malformed JSON bodies surface as BadRequest.
        return error_result(RetCode.ARGUMENT_ERROR, INVALID_REQUEST, 400)

    @app.errorhandler(HTTPException)
    async def _http(exc: HTTPException) -> Response:
        status = exc.code or 500
        code = _CODE_FOR_STATUS.get(status, RetCode.SERVER_ERROR if status >= 500 else RetCode.BAD_REQUEST)
        message = _MESSAGE_FOR_STATUS.get(status, INTERNAL_ERROR if status >= 500 else "request failed")
        return error_result(code, message, status)

    @app.errorhandler(Exception)
    async def _unhandled(exc: Exception) -> Response:
        logger.error("unhandled exception", exc_info=exc)
        return error_result(RetCode.SERVER_ERROR, INTERNAL_ERROR, 500)
