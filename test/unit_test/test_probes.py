from __future__ import annotations

import asyncio
import threading
import time
from pathlib import Path

import pytest
import yaml

from api.apps.restful_apis.system_api import HEALTH_PATHS, LANGUAGE_PATH
from api.db.services.system_service import get_health
from common.health import probes as probes_module
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
    data = yaml.safe_load(ROUTES.read_text(encoding="utf-8"))
    # Exact families whose handlers do not exist yet (Phase 3 rows, implemented: false) are not served by the probe blueprint.
    implemented = {e["path"] for e in data["endpoints"] if e["owner"] == "python" and e["implemented"]}
    expected: set[str] = set()
    for entry in data["routes"]:
        if entry["owner"] == "python" and entry["match"] == "exact":
            expected.update(p for p in (entry["path"], *entry.get("also", [])) if p in implemented)
    # /api/v1/providers is an exact family too, but the provider blueprint (plan 03-12) serves it, not the system blueprint;
    # the same holds for /api/v1/models and /api/v1/models/default (models blueprint, plan 03-13)
    # and for /api/v1/datasets (dataset blueprint, plan 03-14).
    from api.apps.restful_apis.dataset_api import DATASETS
    from api.apps.restful_apis.models_api import MODELS, MODELS_DEFAULT
    from api.apps.restful_apis.provider_api import PROVIDERS

    other_blueprints = {PROVIDERS, MODELS, MODELS_DEFAULT, DATASETS}
    assert set(HEALTH_PATHS) == expected - other_blueprints
    assert other_blueprints <= expected


async def test_unauthenticated_unknown_path_is_401_not_404():
    resp = await make_test_app(authenticated=False).test_client().get("/nope")
    assert resp.status_code == 401
    assert await resp.get_json() == {"code": 401, "message": "unauthorized", "data": None}


async def test_openapi_served_with_health_paths():
    resp = await make_test_app().test_client().get("/api/v1/openapi.json")
    assert resp.status_code == 200
    doc = await resp.get_json()
    assert doc["openapi"].startswith("3")
    assert "/api/v1/system/healthz" in doc["paths"] and "/api/v1/system/status" in doc["paths"]


@pytest.fixture
def counting_probes(monkeypatch):
    """Replace the four probes by counters; ``ttl`` is shortened so a re-probe can be provoked without sleeping long."""
    calls = {name: 0 for name in CHECK_NAMES}
    release = {"event": None, "started": threading.Event()}
    fail = {"database": False}

    def make(name):
        def probe(settings):
            calls[name] += 1
            release["started"].set()
            if release["event"] is not None:
                release["event"].wait(5)
            if fail.get(name):
                raise ConnectionError("down")

        return probe

    monkeypatch.setattr(probes_module, "_PROBES", {name: make(name) for name in CHECK_NAMES})
    probes_module.reset_probe_cache()
    yield calls, release, fail
    probes_module.reset_probe_cache()


async def test_fifty_concurrent_callers_share_one_probe_set(counting_probes):
    calls, release, _ = counting_probes
    release["event"] = threading.Event()
    settings = memory_settings()
    tasks = [asyncio.create_task(run_probes(settings)) for _ in range(50)]
    assert await asyncio.to_thread(release["started"].wait, 5)
    release["event"].set()
    results = await asyncio.gather(*tasks)
    assert all(calls[name] == 1 for name in CHECK_NAMES), calls
    assert all(r == results[0] for r in results)
    assert all(c["status"] == "ok" for c in results[0].values())


async def test_second_call_within_ttl_is_served_from_cache(counting_probes):
    calls, _, _ = counting_probes
    settings = memory_settings()
    first = await run_probes(settings)
    second = await run_probes(settings)
    assert first == second
    assert all(calls[name] == 1 for name in CHECK_NAMES)


async def test_call_after_ttl_probes_again(counting_probes, monkeypatch):
    calls, _, _ = counting_probes
    clock = {"now": 1000.0}
    monkeypatch.setattr(probes_module, "_monotonic", lambda: clock["now"])
    settings = memory_settings()
    await run_probes(settings)
    clock["now"] += probes_module.cache_ttl_seconds() + 0.1
    await run_probes(settings)
    assert all(calls[name] == 2 for name in CHECK_NAMES)


async def test_failed_probe_is_cached_for_the_same_window(counting_probes):
    calls, _, fail = counting_probes
    fail["database"] = True
    settings = memory_settings()
    first = await run_probes(settings)
    second = await run_probes(settings)
    assert first["database"]["status"] == "down" == second["database"]["status"]
    assert calls["database"] == 1


@pytest.mark.parametrize(("raw", "expected"), [(None, 3.0), ("2", 2.0), ("0", 1.0), ("99", 5.0), ("abc", 3.0)])
def test_cache_ttl_is_configurable_and_bounded(monkeypatch, raw, expected):
    if raw is None:
        monkeypatch.delenv("HEALTH_CACHE_TTL_SECONDS", raising=False)
    else:
        monkeypatch.setenv("HEALTH_CACHE_TTL_SECONDS", raw)
    assert probes_module.cache_ttl_seconds() == expected
