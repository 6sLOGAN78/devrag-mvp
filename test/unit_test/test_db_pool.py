"""Fake-driver proofs that the retrying pool really pools, caps, bounds reconnects and never replays writes (DATA-03)."""
from __future__ import annotations

import threading
import time

import peewee
import pymysql
import pytest
from playhouse.pool import MaxConnectionsExceeded

from api.db import database as database_module
from api.db.database import RetryingPooledMySQLDatabase, init_database
from common.settings import MySQLSettings

pytestmark = pytest.mark.unit

HANG_CAP_SECONDS = 4.0


class FakeCursor:
    def __init__(self, conn: FakeConnection) -> None:
        self._conn = conn

    def execute(self, sql: str, params: object = ()) -> None:
        driver = self._conn.driver
        driver.executed.append((self._conn.number, sql))
        for rule in driver.execute_failures:
            if rule["remaining"] > 0 and rule["match"] in sql:
                rule["remaining"] -= 1
                raise pymysql.err.OperationalError(2013, "Lost connection to MySQL server during query")

    def fetchone(self) -> tuple[int]:
        return (1,)

    def close(self) -> None:
        return None


class FakeConnection:
    server_version = "8.0.40"

    def __init__(self, driver: FakeDriver, number: int) -> None:
        self.driver = driver
        self.number = number
        self.open = True
        self.closed = False
        self.dead = False
        self.hung = False
        self.read_timeout: float | None = None

    def ping(self, reconnect: bool = True) -> None:
        if self.hung:
            # A paused server never answers: the call returns only when the driver's socket read timeout fires.
            threading.Event().wait(self.read_timeout if self.read_timeout else HANG_CAP_SECONDS)
            raise pymysql.err.OperationalError(2013, "Lost connection to MySQL server during query")
        if self.dead:
            raise pymysql.err.OperationalError(2006, "MySQL server has gone away")

    def close(self) -> None:
        self.open = False
        self.closed = True

    def cursor(self, *args: object) -> FakeCursor:
        return FakeCursor(self)

    def commit(self) -> None:
        return None

    def rollback(self) -> None:
        return None


class FakeDriver:
    def __init__(self) -> None:
        self.connections: list[FakeConnection] = []
        self.connect_attempts = 0
        self.connect_kwargs: list[dict[str, object]] = []
        self.connect_failures_remaining = 0
        self.executed: list[tuple[int, str]] = []
        self.execute_failures: list[dict[str, object]] = []

    def connect(self, **kwargs: object) -> FakeConnection:
        self.connect_attempts += 1
        if self.connect_failures_remaining > 0:
            self.connect_failures_remaining -= 1
            raise pymysql.err.OperationalError(2003, "Can't connect to MySQL server")
        conn = FakeConnection(self, len(self.connections) + 1)
        conn.read_timeout = kwargs.get("read_timeout")  # type: ignore[assignment]
        self.connect_kwargs.append(kwargs)
        self.connections.append(conn)
        return conn

    def fail_execute(self, match: str, times: int) -> None:
        self.execute_failures.append({"match": match, "remaining": times})

    def statements(self, match: str) -> list[str]:
        return [sql for _, sql in self.executed if match in sql]


@pytest.fixture
def driver(monkeypatch):
    fake = FakeDriver()
    monkeypatch.setattr(database_module.pymysql, "connect", fake.connect)
    return fake


@pytest.fixture
def sleeps(monkeypatch):
    recorded: list[float] = []
    monkeypatch.setattr(database_module.time, "sleep", recorded.append)
    return recorded


def make_db(**kwargs: object) -> RetryingPooledMySQLDatabase:
    params: dict[str, object] = {"max_connections": 2, "stale_timeout": 300, "autoconnect": False, "host": "h", "retry_delay": 1}
    params.update(kwargs)
    return RetryingPooledMySQLDatabase("x", **params)


def test_connect_close_cycles_reuse_one_physical_connection(driver):
    db = make_db()
    for _ in range(5):
        db.connect()
        db.close()
    assert len(driver.connections) == 1
    assert [c for c in driver.connections if c.closed] == []
    assert len(db._connections) == 1


def test_pool_refuses_connection_beyond_max_connections(driver):
    db = make_db(max_connections=1)
    db.connect()
    errors: list[BaseException] = []

    def other_thread() -> None:
        try:
            db.connect()
        except BaseException as exc:  # noqa: BLE001 - captured for the assertion below
            errors.append(exc)

    thread = threading.Thread(target=other_thread)
    thread.start()
    thread.join(timeout=10)
    assert not thread.is_alive()
    assert len(errors) == 1 and isinstance(errors[0], MaxConnectionsExceeded)
    assert len(driver.connections) == 1


def test_close_all_closes_every_created_connection(driver):
    db = make_db()
    db.connect()
    db.close()
    db.connect()
    db.close_all()
    assert driver.connections and all(c.closed for c in driver.connections)


def test_reconnect_failures_consume_the_budget_then_succeed(driver, sleeps):
    db = make_db(max_retries=5, retry_delay=0.5)
    db.connect()
    driver.fail_execute("SELECT 1", 1)
    driver.connect_failures_remaining = 2
    assert db.execute_sql("SELECT 1").fetchone() == (1,)
    assert sleeps == [0.5, 1.0, 2.0]
    assert db.retry_count == 3
    assert driver.connect_attempts == 4  # initial + two failures + one success


def test_reconnect_failures_past_max_retries_raise(driver, sleeps):
    db = make_db(max_retries=5, retry_delay=1)
    db.connect()
    driver.fail_execute("SELECT 1", 1)
    driver.connect_failures_remaining = 100
    with pytest.raises(peewee.OperationalError):
        db.execute_sql("SELECT 1")
    assert sleeps == [1, 2, 4, 8, 16]
    assert db.retry_count == 5
    assert driver.connect_attempts == 6  # initial + five budgeted reconnects


def test_read_only_statement_is_retried_after_lost_connection(driver, sleeps):
    db = make_db()
    db.connect()
    driver.fail_execute("SELECT 1", 1)
    assert db.execute_sql("SELECT 1").fetchone() == (1,)
    assert len(driver.statements("SELECT 1")) == 2
    assert db.retry_count == 1


@pytest.mark.parametrize("sql", ["  /* lead */ select 1", "-- c\nSHOW TABLES", "DESCRIBE t", "EXPLAIN SELECT 1"])
def test_read_only_keywords_after_comments_are_retried(driver, sleeps, sql):
    db = make_db()
    db.connect()
    driver.fail_execute(sql, 1)
    db.execute_sql(sql)
    assert len(driver.statements(sql)) == 2


@pytest.mark.parametrize("sql", ["UPDATE t SET v=v+1", "INSERT INTO t VALUES (1)", "DELETE FROM t", "CREATE TABLE t (id INT)", "SET @a=1", "CALL p()"])
def test_standalone_writes_are_never_re_executed(driver, sleeps, sql):
    db = make_db()
    db.connect()
    driver.fail_execute(sql, 1)
    with pytest.raises(peewee.OperationalError):
        db.execute_sql(sql)
    assert len(driver.statements(sql)) == 1
    assert sleeps == []


def test_dead_idle_connection_is_discarded_on_checkout(driver, sleeps):
    db = make_db()
    db.connect()
    db.close()
    driver.connections[0].dead = True
    db.connect()
    assert len(driver.connections) == 2
    db.execute_sql("UPDATE t SET v=v+1")
    assert driver.executed == [(2, "UPDATE t SET v=v+1")]
    assert sleeps == []


def _settings(**extra: object) -> MySQLSettings:
    return MySQLSettings(name="x", user="u", password="p", host="h", port=3306, max_connections=2, stale_timeout=300, **extra)  # type: ignore[arg-type]


def test_init_database_passes_read_and_write_timeouts_to_the_driver(driver):
    db = init_database(_settings())
    db.connect()
    kwargs = driver.connect_kwargs[0]
    assert kwargs["read_timeout"] == 30 and kwargs["write_timeout"] == 30
    db.close()


def test_paused_server_cannot_block_checkout_past_the_read_timeout(driver, sleeps):
    db = init_database(_settings(read_timeout=0.2, write_timeout=0.2))
    db.connect()
    db.close()
    driver.connections[0].hung = True
    started = time.monotonic()
    db.connect()
    assert time.monotonic() - started < HANG_CAP_SECONDS / 2
    assert len(driver.connections) == 2
    assert driver.connect_kwargs[1]["read_timeout"] == 0.2
    db.close()
