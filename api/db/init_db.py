"""One-shot database initialisation: ``python -m api.db.init_db`` (runs before the servers start)."""
from __future__ import annotations

import logging
import sys

from api.db.database import DB, LockError, LockTimeoutError, init_database
from api.db.migrations.runner import MigrationError, current_version, run_migrations
from common.log_utils import init_root_logger
from common.settings import ConfigError, get_settings

logger = logging.getLogger("init_db")


def main() -> int:
    try:
        settings = get_settings()
    except ConfigError as exc:
        init_root_logger("init_db")
        logger.error("configuration error: %s", exc)
        return 1
    init_root_logger("init_db", settings.logging.dir or None, settings.logging.level)
    try:
        init_database(settings.mysql)
        applied = run_migrations()
        with DB.connection_context():
            version = current_version()
    except (LockTimeoutError, LockError, MigrationError) as exc:
        logger.error("database initialisation failed: %s", exc)
        return 1
    except Exception:
        logger.exception("database initialisation failed")
        return 1
    logger.info("database initialised", extra={"applied": applied, "schema_version": "%04d" % version})
    return 0


if __name__ == "__main__":
    sys.exit(main())
