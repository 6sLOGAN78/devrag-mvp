"""Python API server entry: ``python -m api.ragflow_server`` (API-13, D-10, D-15).

Boot order: logger, database verify (no DDL), then on the serving event loop (``before_serving``)
startup hooks and serve; hooks therefore share the loop that handles requests, so tasks they
create stay alive. Schema creation and
migrations belong to ``python -m api.db.init_db``. The first-superuser seed (D-03) runs as a startup
hook; plugin loading (Phase 7) and the update_progress daemon (Phase 4) are still absent; see B-08.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import signal
import sys
from collections.abc import Awaitable, Callable

import peewee
import pymysql
from hypercorn.asyncio import serve
from hypercorn.config import Config
from quart import Quart

from api.apps import create_app
from api.db.database import DB, init_database
from api.db.migrations.runner import current_version
from common.bootstrap import ensure_superuser
from common.constants import SERVICE_NAME
from common.log_utils import init_root_logger
from common.settings import ConfigError, Settings, get_settings

boot_logger = logging.getLogger("ragflow.boot")
logger = logging.getLogger(SERVICE_NAME)

StartupHook = Callable[[], Awaitable[None] | None]
_HOOKS: list[tuple[str, StartupHook]] = []


class BootError(Exception):
    """Startup cannot continue; the process exits non-zero."""


def register_startup_hook(name: str, hook: StartupHook) -> None:
    """Register ``hook`` under ``name``; registering the same name again replaces it (boot may run twice)."""
    _HOOKS[:] = [(n, h) for n, h in _HOOKS if n != name]
    _HOOKS.append((name, hook))


def install_superuser_hook(settings: Settings) -> None:
    """Seed the first superuser from settings after the database is verified (D-03, B-08)."""
    register_startup_hook("ensure_superuser", lambda: ensure_superuser.run(settings))


def _step(step: str) -> None:
    boot_logger.info("boot.step", extra={"step": step})


def verify_database(settings: Settings) -> None:
    """Open the pool, run ``SELECT 1`` and require a recorded ``schema.version``. Performs no DDL."""
    hint = "run `python -m api.db.init_db` first"
    try:
        init_database(settings.mysql)
        with DB.connection_context():
            DB.execute_sql("SELECT 1")
            version = current_version()
    except (peewee.PeeweeException, pymysql.MySQLError) as exc:
        # Only the exception type is reported: driver messages can carry host details.
        raise BootError(f"database is not ready ({type(exc).__name__}); {hint}") from exc
    if version < 1:
        raise BootError(f"database has no schema.version; {hint}")
    logger.info("database verified", extra={"schema_version": "%04d" % version})


async def _run_hooks() -> None:
    for name, hook in _HOOKS:
        result = hook()
        if asyncio.iscoroutine(result):
            await result
        logger.info("startup hook done", extra={"hook": name})
    logger.info("startup hooks complete", extra={"count": len(_HOOKS)})


def install_startup_hooks(app: Quart) -> None:
    """Run the registered hooks inside ``before_serving`` so they share the serving event loop."""

    @app.before_serving
    async def _startup() -> None:
        await _run_hooks()
        _step("hooks")
        _step("serve")


def boot(settings: Settings | None = None, init_logging: bool = True) -> Quart:
    """Run the boot steps in order and return the application (not yet serving)."""
    try:
        settings = settings or get_settings()
    except ConfigError as exc:
        raise BootError(f"configuration error: {exc}") from exc
    if init_logging:
        init_root_logger(SERVICE_NAME, settings.logging.dir or None, settings.logging.level)
    _step("logger")
    verify_database(settings)
    _step("database")
    install_superuser_hook(settings)
    app = create_app(settings)
    install_startup_hooks(app)
    return app


async def _serve(app: Quart, settings: Settings) -> None:
    config = Config()
    config.bind = [f"{settings.ragflow.host}:{settings.ragflow.http_port}"]
    config.accesslog = None
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, stop.set)
    await serve(app, config, shutdown_trigger=stop.wait)


def main() -> int:
    try:
        settings = get_settings()
        app = boot(settings)
    except BootError as exc:
        init_root_logger(SERVICE_NAME)
        logger.error("boot failed: %s", exc)
        return 1
    except ConfigError as exc:
        init_root_logger(SERVICE_NAME)
        logger.error("configuration error: %s", exc)
        return 1
    try:
        asyncio.run(_serve(app, settings))
    finally:
        with contextlib.suppress(Exception):
            DB.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
