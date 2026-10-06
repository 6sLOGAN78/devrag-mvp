from __future__ import annotations

import dataclasses
import logging

import pytest

from api.db.database import DB
from api.ragflow_server import BootError, boot
from common.settings import load_settings
from test.helpers.db import app_connection_settings, scratch_database

pytestmark = pytest.mark.integration


class _Steps(logging.Handler):
    def __init__(self) -> None:
        super().__init__(logging.INFO)
        self.steps: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        if record.getMessage() == "boot.step":
            self.steps.append(record.step)  # type: ignore[attr-defined]


@pytest.fixture
def steps():
    handler = _Steps()
    logger = logging.getLogger("ragflow.boot")
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    yield handler
    logger.removeHandler(handler)
    if not DB.is_closed():
        DB.close()


def test_empty_database_fails_boot_without_ddl(steps):
    with scratch_database() as name:
        settings = dataclasses.replace(load_settings(), mysql=app_connection_settings(name))
        with pytest.raises(BootError) as err:
            boot(settings, init_logging=False)
        assert "api.db.init_db" in str(err.value)
        assert steps.steps == ["logger"]
        from test.helpers.db import root_connection

        root = root_connection()
        try:
            with root.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = %s", (name,))
                assert cur.fetchone()[0] == 0
        finally:
            root.close()


async def test_migrated_database_boots_in_order(steps):
    app = boot(load_settings(), init_logging=False)
    assert steps.steps == ["logger", "database"]
    async with app.test_app():
        pass
    assert steps.steps == ["logger", "database", "hooks", "serve"]
    assert app.name == "ragflow_server"
