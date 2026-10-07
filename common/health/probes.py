"""Concurrent, bounded dependency probes (SYS-06, SYS-07, D-08, T-08-02, T-08-05).

Each probe is capped at ``PROBE_TIMEOUT_SECONDS`` and returns only ``{status, elapsed_ms}``.
Hostnames, ports and exception text are never part of a result; failures are logged
at debug level without connection details.
"""
from __future__ import annotations

import asyncio
import logging
import os
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


async def _run_all(settings: Settings, cap: float) -> dict[str, dict[str, Any]]:
    results = await asyncio.gather(*(_run_one(name, fn, settings, cap) for name, fn in _PROBES.items()))
    return dict(results)


# Single-flight + short result cache (WR-06): /system/healthz is unauthenticated, so N concurrent callers must
# not open 4N backend connections. Callers share one in-flight probe set; a finished result (ok or down) is
# reused for ``cache_ttl_seconds()``.
CACHE_TTL_ENV = "HEALTH_CACHE_TTL_SECONDS"
DEFAULT_CACHE_TTL_SECONDS = 3.0
MIN_CACHE_TTL_SECONDS = 1.0
MAX_CACHE_TTL_SECONDS = 5.0

_monotonic = time.monotonic
_cached: tuple[Settings, float, dict[str, dict[str, Any]]] | None = None
_inflight: tuple[Settings, asyncio.AbstractEventLoop, asyncio.Task[dict[str, dict[str, Any]]]] | None = None


def cache_ttl_seconds() -> float:
    """Cache window from ``HEALTH_CACHE_TTL_SECONDS`` (default 3), clamped to 1..5; garbage falls back to the default."""
    raw = os.environ.get(CACHE_TTL_ENV)
    if raw is None:
        return DEFAULT_CACHE_TTL_SECONDS
    try:
        value = float(raw)
    except ValueError:
        return DEFAULT_CACHE_TTL_SECONDS
    return min(MAX_CACHE_TTL_SECONDS, max(MIN_CACHE_TTL_SECONDS, value))


def reset_probe_cache() -> None:
    global _cached, _inflight
    _cached = None
    _inflight = None


def _copy(result: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {name: dict(check) for name, check in result.items()}


async def _leader(settings: Settings, cap: float) -> dict[str, dict[str, Any]]:
    global _cached, _inflight
    try:
        result = await _run_all(settings, cap)
        _cached = (settings, _monotonic(), result)
        return result
    finally:
        _inflight = None


async def run_probes(settings: Settings, cap: float = PROBE_TIMEOUT_SECONDS) -> dict[str, dict[str, Any]]:
    global _inflight
    if _cached is not None and _cached[0] == settings and _monotonic() - _cached[1] < cache_ttl_seconds():
        return _copy(_cached[2])
    loop = asyncio.get_running_loop()
    if _inflight is None or _inflight[0] != settings or _inflight[1] is not loop:
        # The probe set runs as its own task so one cancelled caller cannot cancel the others.
        _inflight = (settings, loop, loop.create_task(_leader(settings, cap)))
    return _copy(await asyncio.shield(_inflight[2]))
