"""Scratch database helpers for live integration tests."""
from __future__ import annotations

import re
import uuid
from collections.abc import Iterator
from contextlib import contextmanager

import pymysql

from common.settings import MySQLSettings
from test.conftest import stack_env
from test.helpers.wait import wait_until

_IDENT = re.compile(r"^[A-Za-z0-9_]{1,64}$")


def _ident(value: str) -> str:
    if not _IDENT.match(value):
        raise ValueError(f"unsafe SQL identifier: {value!r}")
    return value


def _host_port(env: dict[str, str]) -> tuple[str, int]:
    return "127.0.0.1", int(env.get("MYSQL_PORT", "3306"))


def root_connection() -> pymysql.connections.Connection:
    env = stack_env()
    host, port = _host_port(env)
    return pymysql.connect(host=host, port=port, user="root", password=env["MYSQL_ROOT_PASSWORD"], autocommit=True, connect_timeout=5)


def app_connection_settings(db_name: str, max_connections: int = 5) -> MySQLSettings:
    env = stack_env()
    host, port = _host_port(env)
    return MySQLSettings(name=_ident(db_name), user=env["MYSQL_USER"], password=env["MYSQL_PASSWORD"], host=host, port=port, max_connections=max_connections, stale_timeout=300)


@contextmanager
def scratch_database() -> Iterator[str]:
    """Create ``rag_test_<uuid8>``, grant the application user on it, drop it on exit."""
    env = stack_env()
    name = _ident(f"rag_test_{uuid.uuid4().hex[:8]}")
    user = _ident(env["MYSQL_USER"])
    root = root_connection()
    try:
        with root.cursor() as cur:
            cur.execute("CREATE DATABASE `" + name + "` CHARACTER SET utf8mb4")  # noqa: S608 - identifier whitelisted above
            cur.execute("GRANT ALL PRIVILEGES ON `" + name + "`.* TO %s@'%%'", (user,))
        yield name
    finally:
        with root.cursor() as cur:
            cur.execute("DROP DATABASE IF EXISTS `" + name + "`")
        root.close()


def kill_connection(connection_id: int) -> None:
    root = root_connection()
    try:
        with root.cursor() as cur:
            cur.execute("KILL CONNECTION %s", (int(connection_id),))

        def gone() -> bool:
            with root.cursor() as c:
                c.execute("SELECT COUNT(*) FROM information_schema.processlist WHERE id = %s", (int(connection_id),))
                return c.fetchone()[0] == 0

        wait_until(gone, timeout=10, interval=0.05)
    finally:
        root.close()
