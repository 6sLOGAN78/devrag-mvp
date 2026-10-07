"""First-superuser startup hook (D-03): ``python -m common.bootstrap.ensure_superuser`` or boot hook.

Nothing is created unless BOTH ``auth.superuser_email`` and ``auth.superuser_password`` are set; no
default credential exists anywhere. The seed itself lives in ``api.db.services.superuser_service``.
The module entry point lets an operator (and the cross-stack e2e test) run the same seed; there the
process environment variables ``SUPERUSER_EMAIL`` and ``SUPERUSER_PASSWORD`` override the config file.
The password is never logged.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import sys

from api.db.database import DB, init_database
from api.db.services import superuser_service
from common.log_utils import init_root_logger
from common.settings import ConfigError, Settings, get_settings

logger = logging.getLogger("ensure_superuser")


async def run(settings: Settings) -> bool:
    """Seed from ``settings``; False when either value is unset (no database access in that case)."""
    email = settings.auth.superuser_email.strip()
    password = settings.auth.superuser_password
    if not email or not password:
        logger.info("superuser seed not configured; nothing created")
        return False
    superuser_service.validate_credentials(email, password)  # fail before any database work
    # Peewee is synchronous: run it in a worker thread so the serving loop is never blocked.
    return await asyncio.to_thread(superuser_service.ensure_superuser, email, password)


def main() -> int:
    init_root_logger("ensure_superuser")
    try:
        settings = get_settings()
        email = os.environ.get("SUPERUSER_EMAIL", settings.auth.superuser_email)
        password = os.environ.get("SUPERUSER_PASSWORD", settings.auth.superuser_password)
        init_database(settings.mysql)
        created = superuser_service.ensure_superuser(email, password) if email.strip() and password else False
    except ConfigError as exc:
        logger.error("configuration error: %s", exc)
        return 1
    except (superuser_service.SuperuserConfigError, superuser_service.SuperuserSeedError) as exc:
        logger.error("superuser seed failed: %s", exc)
        return 1
    except Exception as exc:  # noqa: BLE001 - only the type is reported: driver messages can carry host details
        logger.error("superuser seed failed (%s)", type(exc).__name__)
        return 1
    finally:
        with contextlib.suppress(Exception):  # DB is unbound when configuration failed first
            DB.close()
    logger.info("superuser seed finished", extra={"superuser_created": created})
    return 0


if __name__ == "__main__":
    sys.exit(main())
