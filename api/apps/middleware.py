"""Request timing, access log, source header and CORS allow-list (API-09, API-10, API-11, D-14)."""
from __future__ import annotations

import logging
import time

from quart import Quart, Response, g, request
from quart_cors import cors

from common.constants import API_SOURCE_PYTHON
from common.settings import ConfigError, Settings

access_logger = logging.getLogger("ragflow.access")


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
        access_logger.info("request", extra={"method": request.method, "path": request.path, "status": response.status_code, "duration_ms": duration_ms})
        return response

    if origins:
        cors(app, allow_origin=origins)
