"""Pooled, retrying MySQL access for the Python engine (DATA-03, DATA-04, DATA-08).

* ``RetryingPooledMySQLDatabase`` is a real pool (``PooledDatabase`` checkout wraps the driver
  call): connections are reused, ``max_connections`` is enforced, ``stale_timeout`` applies and idle
  connections are pinged (``reconnect=False``) on checkout.
* After a lost connection (MySQL error 2006/2013, ``InterfaceError`` on an open connection) only
  read-only standalone statements (SELECT/SHOW/DESCRIBE/EXPLAIN) are retried, with exponential
  backoff; failed reconnects consume the same ``max_retries`` budget. A write is never re-executed
  (error 2013 can arrive after it committed) and a statement inside an open transaction is never
  retried (a reconnect would drop earlier statements); the error propagates (R-83).
* ``DB`` is a ``DatabaseProxy`` so models can bind before configuration is known.
* ``DatabaseLock`` wraps MySQL ``GET_LOCK`` on its own dedicated connection, outside the pool,
  so no pool recycling or ``DB.close()`` can release it early or on a different session.
All values reach SQL as parameters; nothing is formatted into statement text.
"""
from __future__ import annotations

import logging
import re
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import peewee
import pymysql
from playhouse.pool import PooledDatabase

from common.settings import MySQLSettings, get_settings

logger = logging.getLogger(__name__)

LOST_CONNECTION_CODES = (2006, 2013)
READ_ONLY_KEYWORDS = frozenset({"SELECT", "SHOW", "DESCRIBE", "EXPLAIN"})
MAX_LOCK_NAME_LENGTH = 64  # MySQL 8 limit for GET_LOCK names
CONNECT_TIMEOUT_SECONDS = 5

DB = peewee.DatabaseProxy()


class LockTimeoutError(Exception):
    """GET_LOCK did not grant the lock within the timeout."""


class LockError(Exception):
    """The lock could not be acquired or released for a reason other than a timeout."""


_LEADING_NOISE = re.compile(r"\A(?:\s+|--[^\n]*(?:\n|\Z)|#[^\n]*(?:\n|\Z)|/\*.*?\*/)*", re.DOTALL)


def _is_read_only(sql: str) -> bool:
    """True when the first keyword (after whitespace and comments) is SELECT/SHOW/DESCRIBE/EXPLAIN."""
    rest = sql[_LEADING_NOISE.match(sql).end():]
    word = re.match(r"[A-Za-z]+", rest)
    return bool(word) and word.group(0).upper() in READ_ONLY_KEYWORDS


def _is_lost_connection(exc: Exception) -> bool:
    if isinstance(exc, peewee.InterfaceError):
        return True
    code = exc.args[0] if exc.args else None
    return isinstance(exc, peewee.OperationalError) and code in LOST_CONNECTION_CODES


class _PyMySQLDatabase(peewee.MySQLDatabase):
    """MySQLDatabase whose driver call uses ``database=``; sits BELOW PooledDatabase in the MRO."""

    def _connect(self) -> Any:
        # peewee passes the deprecated ``db=`` keyword, which PyMySQL 1.2 warns about; use ``database=``.
        return pymysql.connect(database=self.database, autocommit=True, **self.connect_params)


class RetryingPooledMySQLDatabase(PooledDatabase, _PyMySQLDatabase):
    """Pooled MySQL with bounded reconnect. ``PooledDatabase._connect`` wraps the driver call (R-83)."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.max_retries: int = kwargs.pop("max_retries", 5)
        self.retry_delay: float = kwargs.pop("retry_delay", 1)
        self.retry_count: int = 0
        super().__init__(*args, **kwargs)

    def _is_closed(self, conn: Any) -> bool:
        # Pre-send liveness on checkout; reconnect=False so a dead socket is discarded, never silently revived.
        try:
            conn.ping(reconnect=False)
        except Exception:  # noqa: BLE001 - any failure means the idle connection is unusable
            return True
        return False

    def _should_retry(self, exc: Exception, attempt: int, was_open: bool) -> bool:
        if attempt >= self.max_retries or not _is_lost_connection(exc):
            return False
        # InterfaceError on a connection that was never opened is a programming error, not a loss.
        return was_open or not isinstance(exc, peewee.InterfaceError)

    def _reconnect(self, attempt: int, exc: Exception, what: str) -> int:
        """Back off and reconnect; failed reconnects consume the same budget. Returns the new attempt count."""
        self._drop_connection()
        while True:
            self.retry_count += 1
            delay = self.retry_delay * (2**attempt)
            logger.warning("database connection lost during %s (attempt %d/%d), retrying in %.2fs: %s", what, attempt + 1, self.max_retries, delay, exc)
            time.sleep(delay)
            attempt += 1
            try:
                self.connect(reuse_if_open=True)
            except (peewee.OperationalError, peewee.InterfaceError) as connect_exc:
                if attempt >= self.max_retries:
                    logger.error("database reconnect failed after %d attempts: %s", attempt, connect_exc)
                    raise
                exc = connect_exc
                continue
            return attempt

    def _drop_connection(self) -> None:
        try:
            self.manual_close()
        except Exception:  # noqa: BLE001 - the connection is already dead; closing is best effort
            logger.debug("closing a dead connection failed", exc_info=True)
            try:
                self.close()
            except Exception:  # noqa: BLE001
                logger.debug("pool close after failed manual_close failed", exc_info=True)

    def execute_sql(self, sql: str, params: Any = None, commit: Any = None) -> Any:
        read_only = _is_read_only(sql)
        attempt = 0
        while True:
            was_open = not self.is_closed()
            try:
                return super().execute_sql(sql, params)
            except (peewee.OperationalError, peewee.InterfaceError) as exc:
                if self.transaction_depth() > 0 or not read_only or not self._should_retry(exc, attempt, was_open):
                    logger.error("database execution failure: %s", exc)
                    raise
                attempt = self._reconnect(attempt, exc, "statement")

    def begin(self) -> None:
        attempt = 0
        while True:
            was_open = not self.is_closed()
            try:
                return super().begin()
            except (peewee.OperationalError, peewee.InterfaceError) as exc:
                if not self._should_retry(exc, attempt, was_open):
                    raise
                attempt = self._reconnect(attempt, exc, "transaction begin")


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
