from __future__ import annotations

import time
from pathlib import Path

import pytest
import yaml

from api.apps.restful_apis.system_api import HEALTH_PATHS, LANGUAGE_PATH
from api.db.services.system_service import get_health
from common.health.probes import CHECK_NAMES, run_probes
from test.helpers.app import make_test_app, memory_settings

pytestmark = pytest.mark.unit

ROUTES = Path(__file__).resolve().parents[2] / "conf" / "routes.yaml"


async def test_closed_ports_are_down_quickly_without_leaks():
    started = time.monotonic()
    result = await run_probes(memory_settings())
    assert time.monotonic() - started < 3.0
    assert tuple(result) == CHECK_NAMES
    for check in result.values():
        assert set(check) == {"status", "elapsed_ms"}
        assert check["status"] == "down"
        assert isinstance(check["elapsed_ms"], int)
    assert "127.0.0.1" not in repr(result)


async def test_health_service_is_503_when_any_down():
    status, data = await get_health(memory_settings())
    assert status == 503
    assert data["status"] == "down" and data["engine"] == "python"


@pytest.mark.parametrize("path", HEALTH_PATHS)
async def test_health_routes_return_503_envelope_with_checks(path):
    resp = await make_test_app().test_client().get(path)
    assert resp.status_code == 503
    body = await resp.get_json()
    assert body["code"] == 503 and body["message"] == "service unavailable"
    assert body["data"]["engine"] == "python"
    assert {k: v["status"] for k, v in body["data"]["checks"].items()} == dict.fromkeys(CHECK_NAMES, "down")
    assert "127.0.0.1" not in (await resp.get_data(as_text=True))
    assert resp.headers["X-API-Source"] == "python"


async def test_language_direct_returns_python():
    resp = await make_test_app().test_client().get(LANGUAGE_PATH)
    assert resp.status_code == 200
    assert (await resp.get_json())["data"] == {"engine": "python"}


def test_blueprint_urls_match_python_exact_routes():
    entries = yaml.safe_load(ROUTES.read_text(encoding="utf-8"))["routes"]
    expected: set[str] = set()
    for entry in entries:
        if entry["owner"] == "python" and entry["match"] == "exact":
            expected.add(entry["path"])
            expected.update(entry.get("also", []))
    assert set(HEALTH_PATHS) == expected


async def test_openapi_served_with_health_paths():
    resp = await make_test_app().test_client().get("/api/v1/openapi.json")
    assert resp.status_code == 200
    doc = await resp.get_json()
    assert doc["openapi"].startswith("3")
    assert "/api/v1/system/healthz" in doc["paths"] and "/api/v1/system/status" in doc["paths"]
