"""Request timing, access log, source header and CORS allow-list (API-09, API-10, API-11, D-14)."""
from __future__ import annotations

import logging
import posixpath
import re
import time

from quart import Quart, Response, g, request
from quart_cors import cors

from common.constants import API_SOURCE_PYTHON
from common.log_utils import truncate_field
from common.settings import ConfigError, Settings

access_logger = logging.getLogger("ragflow.access")

# The Go-owned family whose last path segment is a credential (an API token). Nginx sends it to Go, so Python normally never sees it;
# the substitution keeps the access log clean even if a request reaches an unmatched Python path under that prefix (T-02-94).
CREDENTIAL_PATH_FAMILY = "/api/v1/system/tokens/"


_API_TOKEN_SHAPE = re.compile(r"ragflow-[A-Za-z0-9_-]{20,}")


def _is_credential_path(path: str) -> bool:
    """True for any spelling of the token family (doubled slash, dot segments, letter case, extra segments)."""
    return posixpath.normpath("/" + path.lstrip("/")).lower().startswith(CREDENTIAL_PATH_FAMILY)


def logged_path() -> str:
    """The path an access-log line may carry: the matched route's template, never the values that filled it.

    ``request.url_rule`` is None for an unmatched request (404, and 405 for a known path with another method). That case logs the raw
    path with two protections (T-02-94): any spelling of the credential family is replaced by its template, and a credential-shaped
    segment anywhere else (a mistyped endpoint) is masked before the path is truncated.
    """
    rule = request.url_rule
    if rule is not None:
        return truncate_field(rule.rule)
    if _is_credential_path(request.path):
        return CREDENTIAL_PATH_FAMILY + ":token"
    return truncate_field(_API_TOKEN_SHAPE.sub("ragflow-***", request.path))


def register_middleware(app: Quart, settings: Settings) -> None:
    origins = list(settings.cors.allowed_origins)
    if "*" in origins:
        raise ConfigError("cors.allowed_origins must be an explicit list; '*' is not allowed")

    @app.before_request
    async def _start_timer() -> None:
        g.request_started = time.perf_counter()

    @app.after_request
    async def _finish(response: Response) -> Response:
        response.headers["X-API-Source"] = API_SOURCE_PYTHON
        started = getattr(g, "request_started", None)
        duration_ms = round((time.perf_counter() - started) * 1000, 3) if started is not None else 0.0
        access_logger.info("request", extra={"method": request.method, "path": logged_path(), "status": response.status_code, "duration_ms": duration_ms})
        return response

    if origins:
        cors(app, allow_origin=origins)
