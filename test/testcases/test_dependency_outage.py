"""Dependency outage and recovery against the live stack (SC-4b, D-08). Acts only on devrag-stack redis/es01."""
from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

import httpx
import pytest

from test.helpers.wait import wait_until
from test.testcases.conftest import compose, service_health

pytestmark = [pytest.mark.e2e, pytest.mark.serial]

LEAK_WORDS = ("es01", "devrag", "6379", "9200", "3306", "traceback", "errno", "refused", "connection", ".py")


def _get(client: httpx.Client, path: str) -> httpx.Response | None:
    try:
        return client.get(path)
    except httpx.HTTPError:
        return None


def _status_is(client: httpx.Client, path: str, status: int, dep: str | None = None, state: str = "down") -> Callable[[], Any]:
    def check() -> Any:
        resp = _get(client, path)
        if resp is None or resp.status_code != status:
            return None
        if dep is not None:
            checks = resp.json()["data"]["checks"]
            if checks[dep]["status"] != state:
                return None
        return resp

    return check


def _assert_no_leak(resp: httpx.Response) -> None:
    assert resp.headers["content-type"].startswith("application/json")
    assert list(resp.json()) == ["code", "message", "data"]
    body = resp.text.lower()
    assert not [w for w in LEAK_WORDS if w in body], resp.text


@contextmanager
def stopped(service: str, client: httpx.Client, recovery_timeout: float = 180) -> Iterator[None]:
    """Stop a service; always start it again, wait for health and for 200s on both engines."""
    out = compose("stop", service)
    assert out.returncode == 0, out.stderr
    try:
        yield
    finally:
        started = compose("start", service)
        wait_until(lambda: service_health(service) == "healthy", timeout=recovery_timeout, interval=2)
        wait_until(_status_is(client, "/health", 200), timeout=recovery_timeout, interval=1)
        wait_until(_status_is(client, "/api/v1/system/status", 200), timeout=recovery_timeout, interval=1)
        assert started.returncode == 0, started.stderr
        assert service_health(service) == "healthy"
        assert service_health("app") == "healthy"


def test_redis_outage_reported_by_both_engines_and_recovers(ingress: httpx.Client) -> None:
    with stopped("redis", ingress):
        go = wait_until(_status_is(ingress, "/health", 503, "redis"), timeout=60, interval=1)
        assert go.headers["x-api-source"] == "go"
        assert go.json()["code"] == 503 or go.json()["code"] != 0
        assert go.json()["data"]["checks"]["database"]["status"] == "ok"
        _assert_no_leak(go)
        py = wait_until(_status_is(ingress, "/api/v1/system/status", 503, "redis"), timeout=60, interval=1)
        assert py.headers["x-api-source"] == "python"
        assert py.json()["data"]["checks"]["database"]["status"] == "ok"
        _assert_no_leak(py)
    assert ingress.get("/health").status_code == 200
    assert ingress.get("/api/v1/system/status").status_code == 200


def test_doc_store_outage_is_independent_of_go(ingress: httpx.Client) -> None:
    with stopped("es01", ingress, recovery_timeout=240):
        py = wait_until(_status_is(ingress, "/api/v1/system/status", 503, "doc_store"), timeout=90, interval=1)
        assert py.headers["x-api-source"] == "python"
        assert py.json()["data"]["checks"]["database"]["status"] == "ok"
        _assert_no_leak(py)
        go = ingress.get("/health")
        assert go.status_code == 200
        assert go.headers["x-api-source"] == "go"
    assert ingress.get("/api/v1/system/status").status_code == 200
