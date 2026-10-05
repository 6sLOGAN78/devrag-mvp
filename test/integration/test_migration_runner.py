"""Live checks of the versioned migration runner and the init_db entry point (DATA-05)."""
from __future__ import annotations

import re
import subprocess
import sys
import textwrap
import threading
from pathlib import Path

import peewee
import pytest

from api.db.database import DB, DatabaseLock, LockTimeoutError, init_database
from api.db.migrations.runner import (
    DEFAULT_MIGRATIONS_DIR,
    MIGRATION_LOCK_NAME,
    MigrationError,
    add_column_if_missing,
    add_index_if_missing,
    current_version,
    discover,
    run_migrations,
)
from api.db.models.system import SCHEMA_VERSION_KEY, SystemSettings, get_setting
from scripts.render_conf import render
from test.conftest import REPO_ROOT, stack_env
from test.helpers.db import app_connection_settings, scratch_database

pytestmark = pytest.mark.integration

M0001 = '''
VERSION = "0001"

def upgrade(db):
    from api.db.migrations.runner import ensure_system_settings
    ensure_system_settings(db)
    db.execute_sql("CREATE TABLE IF NOT EXISTS scratch (id INT AUTO_INCREMENT PRIMARY KEY, v INT NOT NULL) ENGINE=InnoDB")
'''
M0002 = '''
VERSION = "0002"

def upgrade(db):
    db.execute_sql("INSERT INTO scratch (v) VALUES (%s)", (2,))
'''
M0002_FAIL = '''
VERSION = "0002"

def upgrade(db):
    db.execute_sql("INSERT INTO scratch (v) VALUES (%s)", (2,))
    raise RuntimeError("migration exploded")
'''


@pytest.fixture
def scratch():
    with scratch_database() as name:
        database = init_database(app_connection_settings(name))
        try:
            yield name
        finally:
            database.close_all()
            DB.initialize(None)


def write_migrations(directory: Path, **files: str) -> Path:
    for name, body in files.items():
        (directory / f"{name}.py").write_text(textwrap.dedent(body))
    return directory


def scratch_rows() -> int:
    with DB.connection_context():
        return DB.execute_sql("SELECT COUNT(*) FROM scratch").fetchone()[0]


def test_empty_database_gets_versions_and_schema_version(scratch, tmp_path):
    migrations = write_migrations(tmp_path, **{"0001_base": M0001, "0002_data": M0002})
    assert run_migrations(DB, migrations) == ["0001", "0002"]
    with DB.connection_context():
        assert get_setting(SCHEMA_VERSION_KEY) == "0002"
        assert current_version() == 2
    assert scratch_rows() == 1


@pytest.mark.serial
def test_second_run_is_idempotent(scratch, tmp_path):
    migrations = write_migrations(tmp_path, **{"0001_base": M0001, "0002_data": M0002})
    run_migrations(DB, migrations)
    assert run_migrations(DB, migrations) == []
    assert scratch_rows() == 1
    with DB.connection_context():
        assert SystemSettings.select().count() == 1


@pytest.mark.serial
def test_failed_migration_keeps_previous_version(scratch, tmp_path):
    migrations = write_migrations(tmp_path, **{"0001_base": M0001, "0002_data": M0002_FAIL})
    with pytest.raises(MigrationError, match="0002_data"):
        run_migrations(DB, migrations)
    with DB.connection_context():
        assert get_setting(SCHEMA_VERSION_KEY) == "0001"
    assert scratch_rows() == 0


@pytest.mark.serial
def test_concurrent_runners_apply_once(scratch, tmp_path):
    migrations = write_migrations(tmp_path, **{"0001_base": M0001, "0002_data": M0002})
    barrier = threading.Barrier(2)
    results: list[list[str]] = []
    errors: list[BaseException] = []

    def runner() -> None:
        try:
            barrier.wait(timeout=10)
            results.append(run_migrations(DB, migrations))
        except BaseException as exc:  # noqa: BLE001 - surfaced by the assertion below
            errors.append(exc)

    threads = [threading.Thread(target=runner) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
    assert not errors, errors
    assert sorted(results) == [[], ["0001", "0002"]]
    assert scratch_rows() == 1


@pytest.mark.serial
def test_lock_timeout_raises_then_succeeds_after_release(scratch, tmp_path):
    migrations = write_migrations(tmp_path, **{"0001_base": M0001})
    holder = DatabaseLock(MIGRATION_LOCK_NAME, timeout=5)
    holder.acquire()
    try:
        with pytest.raises(LockTimeoutError):
            run_migrations(DB, migrations, lock_timeout=1)
    finally:
        holder.release()
    assert run_migrations(DB, migrations, lock_timeout=5) == ["0001"]


def test_real_migrations_apply_and_match_highest_prefix(scratch):
    highest = max(int(m.group(1)) for p in DEFAULT_MIGRATIONS_DIR.glob("*.py") if (m := re.match(r"^(\d{4})_", p.name)))
    applied = run_migrations(DB)
    assert applied[0] == "0001" and applied[-1] == "%04d" % highest
    with DB.connection_context():
        assert get_setting(SCHEMA_VERSION_KEY) == "%04d" % highest


def test_discover_rejects_version_mismatch(tmp_path):
    write_migrations(tmp_path, **{"0003_bad": 'VERSION = "0004"\ndef upgrade(db):\n    pass\n'})
    with pytest.raises(MigrationError, match="VERSION"):
        discover(tmp_path)


def test_alter_helpers_are_idempotent(scratch, tmp_path):
    run_migrations(DB, write_migrations(tmp_path, **{"0001_base": M0001}))
    with DB.connection_context():
        assert add_column_if_missing(DB, "scratch", "note", peewee.CharField(max_length=20, default=""))
        assert not add_column_if_missing(DB, "scratch", "note", peewee.CharField(max_length=20, default=""))
        assert add_index_if_missing(DB, "scratch", ("v",))
        assert not add_index_if_missing(DB, "scratch", ("v",))


def _conf_env(db_name: str) -> dict[str, str]:
    env = stack_env()
    return {
        "PATH": "/usr/bin:/bin",
        "MYSQL_DBNAME": db_name,
        "MYSQL_USER": env["MYSQL_USER"],
        "MYSQL_HOST": "127.0.0.1",
        "MYSQL_PORT": env.get("MYSQL_PORT", "3306"),
        "MYSQL_PASSWORD": env["MYSQL_PASSWORD"],
        "REDIS_PASSWORD": "x",
        "MINIO_PASSWORD": "x",
        "ELASTIC_PASSWORD": "x",
    }


def test_init_db_entry_point_exit_codes(scratch, tmp_path):
    conf = tmp_path / "service_conf.yaml"
    conf.write_text(render((REPO_ROOT / "conf/service_conf.yaml.template").read_text(), _conf_env(scratch)))
    base = _conf_env(scratch)
    run = lambda extra: subprocess.run([sys.executable, "-m", "api.db.init_db"], capture_output=True, text=True, cwd=REPO_ROOT, check=False, env={**base, **extra})  # noqa: E731
    ok = run({"SERVICE_CONF": str(conf)})
    assert ok.returncode == 0, ok.stdout + ok.stderr
    with DB.connection_context():
        assert get_setting(SCHEMA_VERSION_KEY) is not None
        rows = SystemSettings.select().count()
    assert run({"SERVICE_CONF": str(conf)}).returncode == 0
    with DB.connection_context():
        assert SystemSettings.select().count() == rows
    missing = run({"SERVICE_CONF": str(tmp_path / "absent.yaml")})
    assert missing.returncode == 1
    assert "configuration error" in missing.stdout
