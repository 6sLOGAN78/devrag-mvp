"""Pooled, retrying MySQL access for the Python engine (DATA-03, DATA-04, DATA-08).

* ``RetryingPooledMySQLDatabase`` retries lost connections (MySQL error 2006/2013 and
  ``InterfaceError`` on an open connection) with exponential backoff, up to ``max_retries``.
  A statement inside an open transaction is never retried: reconnecting would silently drop
  the earlier statements of that transaction and break atomicity, so the error propagates.
* ``DB`` is a ``DatabaseProxy`` so models can bind before configuration is known.
* ``DatabaseLock`` wraps MySQL ``GET_LOCK`` on its own dedicated connection, outside the pool,
  so no pool recycling or ``DB.close()`` can release it early or on a different session.
All values reach SQL as parameters; nothing is formatted into statement text.
"""
from __future__ import annotations

import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import peewee
import pymysql
from playhouse.pool import PooledMySQLDatabase

from common.settings import MySQLSettings, get_settings

logger = logging.getLogger(__name__)

LOST_CONNECTION_CODES = (2006, 2013)
MAX_LOCK_NAME_LENGTH = 64  # MySQL 8 limit for GET_LOCK names
CONNECT_TIMEOUT_SECONDS = 5

DB = peewee.DatabaseProxy()


class LockTimeoutError(Exception):
    """GET_LOCK did not grant the lock within the timeout."""


class LockError(Exception):
    """The lock could not be acquired or released for a reason other than a timeout."""


def _is_lost_connection(exc: Exception) -> bool:
    if isinstance(exc, peewee.InterfaceError):
        return True
    code = exc.args[0] if exc.args else None
    return isinstance(exc, peewee.OperationalError) and code in LOST_CONNECTION_CODES


class RetryingPooledMySQLDatabase(PooledMySQLDatabase):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.max_retries: int = kwargs.pop("max_retries", 5)
        self.retry_delay: float = kwargs.pop("retry_delay", 1)
        self.retry_count: int = 0
        super().__init__(*args, **kwargs)

    def _connect(self) -> Any:
        # peewee passes the deprecated ``db=`` keyword, which PyMySQL 1.2 warns about; use ``database=``.
        return pymysql.connect(database=self.database, autocommit=True, **self.connect_params)

    def _should_retry(self, exc: Exception, attempt: int, was_open: bool) -> bool:
        if attempt >= self.max_retries or not _is_lost_connection(exc):
            return False
        # InterfaceError on a connection that was never opened is a programming error, not a loss.
        return was_open or not isinstance(exc, peewee.InterfaceError)

    def _backoff(self, attempt: int, exc: Exception, what: str) -> None:
        self.retry_count += 1
        delay = self.retry_delay * (2**attempt)
        logger.warning("database connection lost during %s (attempt %d/%d), retrying in %.2fs: %s", what, attempt + 1, self.max_retries, delay, exc)
        self._drop_connection()
        time.sleep(delay)
        self.connect(reuse_if_open=True)

    def _drop_connection(self) -> None:
        try:
            self.manual_close()
        except Exception:  # noqa: BLE001 - the connection is already dead; closing is best effort
            logger.debug("closing a dead connection failed", exc_info=True)
            try:
                self.close()
            except Exception:  # noqa: BLE001
                logger.debug("pool close after failed manual_close failed", exc_info=True)

    def execute_sql(self, sql: str, params: Any = None) -> Any:
        attempt = 0
        while True:
            was_open = not self.is_closed()
            try:
                return super().execute_sql(sql, params)
            except (peewee.OperationalError, peewee.InterfaceError) as exc:
                if self.transaction_depth() > 0 or not self._should_retry(exc, attempt, was_open):
                    logger.error("database execution failure: %s", exc)
                    raise
                self._backoff(attempt, exc, "statement")
                attempt += 1

    def begin(self) -> None:
        attempt = 0
        while True:
            was_open = not self.is_closed()
            try:
                return super().begin()
            except (peewee.OperationalError, peewee.InterfaceError) as exc:
                if not self._should_retry(exc, attempt, was_open):
                    raise
                self._backoff(attempt, exc, "transaction begin")
                attempt += 1


def init_database(mysql: MySQLSettings | None = None, **overrides: Any) -> RetryingPooledMySQLDatabase:
    """Build the pool from settings, bind it to ``DB`` and return it. Connections open lazily."""
    cfg = mysql or get_settings().mysql
    database = RetryingPooledMySQLDatabase(
        cfg.name,
        host=cfg.host,
        port=cfg.port,
        user=cfg.user,
        password=cfg.password,
        charset="utf8mb4",
        max_connections=cfg.max_connections,
        stale_timeout=cfg.stale_timeout,
        autoconnect=False,
        connect_timeout=CONNECT_TIMEOUT_SECONDS,
        **overrides,
    )
    DB.initialize(database)
    return database


@contextmanager
def transaction() -> Iterator[None]:
    """Run the block in ``DB.atomic()``: commit on success, roll back everything on any exception."""
    with DB.atomic():
        yield


class DatabaseLock:
    """Named cross-process lock backed by MySQL ``GET_LOCK`` on one dedicated connection."""

    def __init__(self, lock_name: str, timeout: int = 10) -> None:
        if not lock_name or len(lock_name) > MAX_LOCK_NAME_LENGTH:
            raise ValueError("lock name must be 1..%d characters" % MAX_LOCK_NAME_LENGTH)
        self.lock_name = lock_name
        self.timeout = int(timeout)
        self._conn: pymysql.connections.Connection | None = None

    def _open(self) -> pymysql.connections.Connection:
        params = dict(DB.connect_params)
        return pymysql.connect(database=DB.database, autocommit=True, **params)

    def acquire(self) -> None:
        if self._conn is not None:
            raise LockError("lock %s is already held by this object" % self.lock_name)
        conn = self._open()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT GET_LOCK(%s, %s)", (self.lock_name, self.timeout))
                row = cur.fetchone()
        except Exception:
            conn.close()
            raise
        result = row[0] if row else None
        if result == 1:
            self._conn = conn
            return
        conn.close()
        if result == 0:
            raise LockTimeoutError("timed out after %ds waiting for lock %s" % (self.timeout, self.lock_name))
        raise LockError("failed to acquire lock %s (result %r)" % (self.lock_name, result))

    def holds_lock(self) -> bool:
        """True while this object's own session owns the lock (IS_USED_LOCK equals CONNECTION_ID)."""
        if self._conn is None:
            return False
        with self._conn.cursor() as cur:
            cur.execute("SELECT IS_USED_LOCK(%s) = CONNECTION_ID()", (self.lock_name,))
            row = cur.fetchone()
        return bool(row and row[0] == 1)

    def release(self) -> None:
        conn, self._conn = self._conn, None
        if conn is None:
            return
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT RELEASE_LOCK(%s)", (self.lock_name,))
                row = cur.fetchone()
            if not row or row[0] != 1:
                raise LockError("lock %s was not held by its session (result %r)" % (self.lock_name, row[0] if row else None))
        finally:
            conn.close()

    def __enter__(self) -> DatabaseLock:
        self.acquire()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.release()
