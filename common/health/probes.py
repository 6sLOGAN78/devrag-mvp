"""Concurrent, bounded dependency probes (SYS-06, SYS-07, D-08, T-08-02, T-08-05).

Each probe is capped at ``PROBE_TIMEOUT_SECONDS`` and returns only ``{status, elapsed_ms}``.
Hostnames, ports and exception text are never part of a result; failures are logged
at debug level without connection details.
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from typing import Any

import pymysql
import urllib3
import valkey
from elasticsearch import Elasticsearch
from minio import Minio

from common.constants import BUCKET_NAME
from common.settings import Settings

logger = logging.getLogger(__name__)

PROBE_TIMEOUT_SECONDS = 2.0
CHECK_NAMES = ("database", "redis", "storage", "doc_store")


def probe_database(settings: Settings) -> None:
    my = settings.mysql
    conn = pymysql.connect(host=my.host, port=my.port, user=my.user, password=my.password, database=my.name, connect_timeout=2, read_timeout=2, write_timeout=2)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
    finally:
        conn.close()


def probe_redis(settings: Settings) -> None:
    rd = settings.redis
    client = valkey.Valkey(host=rd.host, port=rd.port, password=rd.password or None, db=rd.db, socket_timeout=2, socket_connect_timeout=2)
    try:
        if not client.ping():
            raise ConnectionError("ping failed")
    finally:
        client.close()


def probe_storage(settings: Settings) -> None:
    mn = settings.minio
    http = urllib3.PoolManager(timeout=urllib3.Timeout(connect=2, read=2), retries=urllib3.Retry(total=0))
    try:
        client = Minio(f"{mn.host}:{mn.port}", access_key=mn.user, secret_key=mn.password, secure=False, http_client=http)
        if not client.bucket_exists(BUCKET_NAME):
            raise LookupError("bucket missing")
    finally:
        http.clear()


def probe_doc_store(settings: Settings) -> None:
    es = settings.es
    client = Elasticsearch(es.hosts, basic_auth=(es.username, es.password), request_timeout=2, max_retries=0)
    try:
        client.info()
    finally:
        client.close()


_PROBES: dict[str, Callable[[Settings], None]] = {
    "database": probe_database,
    "redis": probe_redis,
    "storage": probe_storage,
    "doc_store": probe_doc_store,
}


async def _run_one(name: str, fn: Callable[[Settings], None], settings: Settings, cap: float) -> tuple[str, dict[str, Any]]:
    started = time.perf_counter()
    status = "ok"
    try:
        async with asyncio.timeout(cap):
            await asyncio.to_thread(fn, settings)
    except Exception as exc:  # noqa: BLE001 - any failure means "down"; only the type is logged
        status = "down"
        logger.debug("probe failed", extra={"probe": name, "error_type": type(exc).__name__})
    return name, {"status": status, "elapsed_ms": int((time.perf_counter() - started) * 1000)}


async def run_probes(settings: Settings, cap: float = PROBE_TIMEOUT_SECONDS) -> dict[str, dict[str, Any]]:
    results = await asyncio.gather(*(_run_one(name, fn, settings, cap) for name, fn in _PROBES.items()))
    return dict(results)
