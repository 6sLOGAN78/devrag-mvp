"""Live routing through Nginx: which engine answers the system routes (SC-4a/4b/4c, SYS-01..07)."""
from __future__ import annotations

import re

import httpx
import pytest

from test.conftest import REPO_ROOT
from test.testcases.conftest import exec_app

pytestmark = pytest.mark.e2e

GO_EXACT = ["/health", "/api/v1/system/ping", "/api/v1/system/config", "/api/v1/system/version", "/api/v1/language"]
PY_STATUS = ["/system/healthz", "/system/status", "/api/v1/system/healthz", "/api/v1/system/status"]


def _latest_migration() -> str:
    names = [p.name[:4] for p in (REPO_ROOT / "api" / "db" / "migrations").glob("[0-9][0-9][0-9][0-9]_*.py")]
    return max(names)


@pytest.mark.parametrize("path", GO_EXACT)
def test_go_routes_answer_from_go(ingress: httpx.Client, path: str) -> None:
    resp = ingress.get(path)
    assert resp.status_code == 200
    assert resp.headers["x-api-source"] == "go"
    assert resp.json()["code"] == 0


def test_version_reports_latest_schema(ingress: httpx.Client) -> None:
    data = ingress.get("/api/v1/system/version").json()["data"]
    assert data["schema_version"] == _latest_migration()


@pytest.mark.parametrize("path", PY_STATUS)
def test_python_health_status_routes(ingress: httpx.Client, path: str) -> None:
    resp = ingress.get(path)
    assert resp.status_code == 200
    assert resp.headers["x-api-source"] == "python"
    data = resp.json()["data"]
    assert data["engine"] == "python"
    assert sorted(data["checks"]) == ["database", "doc_store", "redis", "storage"]
    assert all(c["status"] == "ok" for c in data["checks"].values())


def test_direct_python_language_names_python() -> None:
    out = exec_app("curl", "-fsS", "http://127.0.0.1:9380/api/v1/language")
    assert out.returncode == 0, out.stderr
    assert re.search(r'"engine":\s*"python"', out.stdout)


def test_direct_go_language_names_go() -> None:
    out = exec_app("curl", "-fsS", "http://127.0.0.1:9384/api/v1/language")
    assert out.returncode == 0, out.stderr
    assert re.search(r'"engine":\s*"go"', out.stdout)
