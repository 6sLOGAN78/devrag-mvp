"""System route behaviours that need the live stack (SYS-01..07, R-55)."""
from __future__ import annotations

import httpx
import pytest

pytestmark = pytest.mark.e2e

FORBIDDEN = ("mysql", "minio", "es01", "redis:", "traceback", "9200", "3306")


@pytest.mark.parametrize("path", ["/system/status", "/api/v1/system/status"])
def test_status_is_public_and_leaks_no_hostnames(ingress: httpx.Client, path: str) -> None:
    resp = ingress.get(path)
    assert resp.status_code == 200
    body = resp.text.lower()
    assert not [w for w in FORBIDDEN if w in body]


def test_ping_and_config_are_public(ingress: httpx.Client) -> None:
    assert ingress.get("/api/v1/system/ping").status_code == 200
    cfg = ingress.get("/api/v1/system/config")
    assert cfg.status_code == 200
    assert cfg.json()["code"] == 0


def test_go_health_reports_its_dependencies(ingress: httpx.Client) -> None:
    data = ingress.get("/health").json()["data"]
    assert data["engine"] == "go"
    assert data["checks"]["database"]["status"] == "ok"
    assert data["checks"]["redis"]["status"] == "ok"
