"""Versioned, idempotent migration runner (DATA-05, D-10).

Migrations are files ``NNNN_<name>.py`` in the migrations directory, each exposing
``VERSION`` (equal to its numeric prefix) and ``upgrade(db)``. The runner holds
``DatabaseLock("init_database_tables")`` for the whole run, applies every migration whose
number is greater than the stored ``schema.version`` in ascending order, each inside
``db.atomic()`` together with the version write, so a failing migration leaves the stored
version at the previous value.

MySQL commits DDL implicitly, so a migration that mixes DDL and data must make its DDL
idempotent. Use ``add_column_if_missing`` and ``add_index_if_missing`` (``playhouse.migrate.
MySQLMigrator`` behind ``get_columns``/``get_indexes`` existence checks) for alters; a rerun
after a partial failure then skips what already exists. Tables are created by migrations only,
never by ad-hoc table creation outside a migration.
"""
from __future__ import annotations

import importlib.util
import logging
import re
from pathlib import Path
from types import ModuleType
from typing import Any

import peewee
from playhouse.migrate import MySQLMigrator, migrate

from api.db.database import DB, DatabaseLock
from api.db.models.system import SCHEMA_VERSION_KEY, SystemSettings
from api.db.models.system import get_setting as _get_setting
from api.db.models.system import upsert_setting as _upsert_setting

logger = logging.getLogger(__name__)

MIGRATION_LOCK_NAME = "init_database_tables"
DEFAULT_MIGRATIONS_DIR = Path(__file__).resolve().parent
_FILE = re.compile(r"^(\d{4})_[A-Za-z0-9_]+\.py$")


class MigrationError(Exception):
    """A migration file is malformed or failed to apply."""


def ensure_system_settings(db: Any) -> None:
    """Create ``system_settings`` if absent (shared by the bootstrap and migration 0001)."""
    with db.bind_ctx([SystemSettings]):
        SystemSettings.create_table(safe=True)


def add_column_if_missing(db: Any, table: str, column: str, field: peewee.Field) -> bool:
    if column in {c.name for c in db.get_columns(table)}:
        return False
    migrate(MySQLMigrator(db).add_column(table, column, field))
    return True


def add_index_if_missing(db: Any, table: str, columns: tuple[str, ...], unique: bool = False) -> bool:
    wanted = tuple(columns)
    for existing in db.get_indexes(table):
        if tuple(existing.columns) != wanted:
            continue
        if bool(existing.unique) != bool(unique):
            raise MigrationError(
                "index on (%s) exists with different uniqueness (existing unique=%s, requested unique=%s)"
                % (", ".join(wanted), bool(existing.unique), bool(unique))
            )
        return False
    migrate(MySQLMigrator(db).add_index(table, columns, unique))
    return True


def _load(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location("devrag_migration_" + path.stem, path)
    if spec is None or spec.loader is None:
        raise MigrationError("cannot load migration %s" % path.name)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def discover(migrations_dir: Path) -> list[tuple[int, str, ModuleType]]:
    found: list[tuple[int, str, ModuleType]] = []
    for path in sorted(migrations_dir.glob("[0-9][0-9][0-9][0-9]_*.py")):
        match = _FILE.match(path.name)
        if not match:
            raise MigrationError("migration file name must be NNNN_name.py: %s" % path.name)
        number = int(match.group(1))
        module = _load(path)
        version = getattr(module, "VERSION", None)
        if version is None or not str(version).isdigit() or int(version) != number:
            raise MigrationError("%s: VERSION must equal the numeric prefix %04d" % (path.name, number))
        if not callable(getattr(module, "upgrade", None)):
            raise MigrationError("%s: missing upgrade(db)" % path.name)
        if found and found[-1][0] == number:
            raise MigrationError("duplicate migration number %04d" % number)
        found.append((number, path.name, module))
    return found


def current_version(db: Any = DB) -> int:
    """Stored ``schema.version`` read from ``db`` (not necessarily the global ``DB``)."""
    with db.bind_ctx([SystemSettings]):
        raw = _get_setting(SCHEMA_VERSION_KEY)
    return int(raw) if raw and raw.isdigit() else 0


def upsert_setting(key: str, value: str, db: Any = DB) -> None:
    """Write one setting on ``db`` (not necessarily the global ``DB``)."""
    with db.bind_ctx([SystemSettings]):
        _upsert_setting(key, value)


def run_migrations(db: Any = DB, migrations_dir: Path | str | None = None, lock_timeout: int = 60) -> list[str]:
    """Apply pending migrations under the DB lock and return the applied versions (4-digit strings)."""
    directory = Path(migrations_dir) if migrations_dir else DEFAULT_MIGRATIONS_DIR
    migrations = discover(directory)
    applied: list[str] = []
    with DatabaseLock(MIGRATION_LOCK_NAME, lock_timeout), db.connection_context():
        ensure_system_settings(db)
        stored = current_version(db)
        for number, name, module in migrations:
            if number <= stored:
                continue
            logger.info("applying migration %s", name)
            try:
                with db.atomic():
                    module.upgrade(db)
                    upsert_setting(SCHEMA_VERSION_KEY, "%04d" % number, db)
            except Exception as exc:
                raise MigrationError("migration %s failed: %s" % (name, exc)) from exc
            applied.append("%04d" % number)
            stored = number
    return applied
