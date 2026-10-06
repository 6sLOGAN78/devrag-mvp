"""Live checks of the pooled retrying database, transactions and DatabaseLock (DATA-03/04/08)."""
from __future__ import annotations

import threading
import time
import uuid

import peewee
import pytest
from playhouse.pool import MaxConnectionsExceeded

from api.db.database import DB, DatabaseLock, LockError, LockTimeoutError, RetryingPooledMySQLDatabase, init_database, transaction
from test.helpers.db import app_connection_settings, kill_connection, scratch_database
from test.helpers.wait import wait_until

pytestmark = pytest.mark.integration


@pytest.fixture
def db():
    with scratch_database() as name:
        database = init_database(app_connection_settings(name), retry_delay=0.01)
        DB.connect()
        DB.execute_sql("CREATE TABLE scratch (id INT AUTO_INCREMENT PRIMARY KEY, v INT NOT NULL) ENGINE=InnoDB")
        try:
            yield database
        finally:
            database.close_all()
            DB.initialize(None)


def count_rows() -> int:
    return DB.execute_sql("SELECT COUNT(*) FROM scratch").fetchone()[0]


@pytest.mark.serial
def test_retry_after_kill(db):
    conn_id = DB.execute_sql("SELECT CONNECTION_ID()").fetchone()[0]
    kill_connection(conn_id)
    assert DB.execute_sql("SELECT 1").fetchone()[0] == 1
    assert DB.retry_count >= 1
    new_id = DB.execute_sql("SELECT CONNECTION_ID()").fetchone()[0]
    assert new_id != conn_id
    DB.close()
    DB.connect()
    assert DB.execute_sql("SELECT CONNECTION_ID()").fetchone()[0] != conn_id


def threads_connected() -> int:
    return int(DB.execute_sql("SHOW STATUS LIKE 'Threads_connected'").fetchone()[1])


def test_pool_reuses_one_physical_connection(db):
    before = threads_connected()
    DB.close()
    ids = set()
    for _ in range(5):
        DB.connect()
        ids.add(DB.execute_sql("SELECT CONNECTION_ID()").fetchone()[0])
        DB.close()
    DB.connect()
    after = threads_connected()
    assert len(ids) == 1
    assert after - before <= 1


def test_pool_cap_enforced_against_live_mysql(db):
    cfg = app_connection_settings(db.database, max_connections=1)
    capped = RetryingPooledMySQLDatabase(
        cfg.name, host=cfg.host, port=cfg.port, user=cfg.user, password=cfg.password, max_connections=1, stale_timeout=300, autoconnect=False
    )
    capped.connect()
    errors: list[BaseException] = []

    def other() -> None:
        try:
            capped.connect()
        except BaseException as exc:  # noqa: BLE001 - captured for the assertion
            errors.append(exc)

    try:
        thread = threading.Thread(target=other)
        thread.start()
        thread.join(timeout=15)
        assert not thread.is_alive()
        assert len(errors) == 1 and isinstance(errors[0], MaxConnectionsExceeded)
    finally:
        capped.close_all()


@pytest.mark.serial
def test_write_after_kill_applied_once(db):
    conn_id = DB.execute_sql("SELECT CONNECTION_ID()").fetchone()[0]
    DB.close()  # idle in the pool
    kill_connection(conn_id)
    DB.connect()  # checkout pings the dead idle connection, discards it and opens a fresh one
    assert DB.execute_sql("SELECT CONNECTION_ID()").fetchone()[0] != conn_id
    DB.execute_sql("INSERT INTO scratch (v) VALUES (1)")
    assert count_rows() == 1


@pytest.mark.serial
def test_write_on_held_killed_connection_is_not_replayed(db):
    kill_connection(DB.execute_sql("SELECT CONNECTION_ID()").fetchone()[0])
    with pytest.raises((peewee.OperationalError, peewee.InterfaceError)):
        DB.execute_sql("INSERT INTO scratch (v) VALUES (1)")
    DB.close()
    DB.connect()
    assert count_rows() == 0


def test_retries_exhausted_propagates(db, monkeypatch):
    calls = {"n": 0}

    def always_lost(self, sql, params=None):
        calls["n"] += 1
        raise peewee.OperationalError(2006, "MySQL server has gone away")

    monkeypatch.setattr(peewee.Database, "execute_sql", always_lost)
    with pytest.raises(peewee.OperationalError):
        DB.execute_sql("SELECT 1")
    assert calls["n"] == db.max_retries + 1
    assert db.retry_count == db.max_retries


def test_non_connection_errors_are_not_retried(db):
    before = DB.retry_count
    with pytest.raises(peewee.ProgrammingError):
        DB.execute_sql("SELECT * FROM no_such_table")
    assert DB.retry_count == before


def test_backoff_is_exponential(db, monkeypatch):
    delays: list[float] = []
    monkeypatch.setattr(time, "sleep", delays.append)

    def lost(self, sql, params=None):
        raise peewee.OperationalError(2013, "Lost connection")

    monkeypatch.setattr(peewee.Database, "execute_sql", lost)
    with pytest.raises(peewee.OperationalError):
        DB.execute_sql("SELECT 1")
    assert delays == [0.01 * 2**i for i in range(db.max_retries)]


def test_atomic_rolls_back(db):
    with pytest.raises(RuntimeError):
        with DB.atomic():
            DB.execute_sql("INSERT INTO scratch (v) VALUES (%s)", (1,))
            DB.execute_sql("INSERT INTO scratch (v) VALUES (%s)", (2,))
            raise RuntimeError("boom")
    assert count_rows() == 0


def test_atomic_commits(db):
    with transaction():
        DB.execute_sql("INSERT INTO scratch (v) VALUES (%s)", (1,))
        DB.execute_sql("INSERT INTO scratch (v) VALUES (%s)", (2,))
    assert count_rows() == 2


@pytest.mark.serial
def test_no_retry_inside_transaction(db):
    with pytest.raises((peewee.OperationalError, peewee.InterfaceError)):
        with DB.atomic():
            DB.execute_sql("INSERT INTO scratch (v) VALUES (%s)", (1,))
            kill_connection(DB.execute_sql("SELECT CONNECTION_ID()").fetchone()[0])
            DB.execute_sql("INSERT INTO scratch (v) VALUES (%s)", (2,))
    DB.close()
    DB.connect()
    assert count_rows() == 0


@pytest.mark.serial
def test_lock_contention(db):
    name = f"t_{uuid.uuid4().hex[:8]}"
    holder = DatabaseLock(name, timeout=1)
    holder.acquire()
    result: dict[str, object] = {}

    def contender() -> None:
        started = time.monotonic()
        try:
            DatabaseLock(name, timeout=1).acquire()
            result["outcome"] = "acquired"
        except LockTimeoutError:
            result["outcome"] = "timeout"
        result["elapsed"] = time.monotonic() - started

    thread = threading.Thread(target=contender)
    thread.start()
    thread.join(timeout=15)
    assert not thread.is_alive()
    assert result["outcome"] == "timeout"
    assert 0.8 <= result["elapsed"] < 5

    holder.release()
    second = DatabaseLock(name, timeout=5)
    second.acquire()
    second.release()


@pytest.mark.serial
def test_lock_release_uses_same_connection(db):
    name = f"t_{uuid.uuid4().hex[:8]}"
    lock = DatabaseLock(name, timeout=2)
    with lock:
        assert lock.holds_lock()
        assert DB.execute_sql("SELECT IS_FREE_LOCK(%s)", (name,)).fetchone()[0] == 0
    assert not lock.holds_lock()
    wait_until(lambda: DB.execute_sql("SELECT IS_FREE_LOCK(%s)", (name,)).fetchone()[0] == 1, timeout=5)


def test_lock_survives_db_close(db):
    name = f"t_{uuid.uuid4().hex[:8]}"
    with DatabaseLock(name, timeout=2) as lock:
        DB.close()
        DB.connect()
        assert lock.holds_lock()


def test_lock_name_validation():
    with pytest.raises(ValueError):
        DatabaseLock("x" * 65)
    with pytest.raises(ValueError):
        DatabaseLock("")


def test_double_acquire_rejected(db):
    lock = DatabaseLock(f"t_{uuid.uuid4().hex[:8]}", timeout=1)
    with lock:
        with pytest.raises(LockError):
            lock.acquire()
