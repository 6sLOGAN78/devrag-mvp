"""routes.yaml-driven ownership: every declared route is answered by its declared owner (R-53, API-02/04/05)."""
from __future__ import annotations

import re
import shutil
import uuid
from pathlib import Path

import httpx
import pytest
import yaml

from api.apps import create_app
from test.helpers.app import memory_settings
from test.testcases._routes import ROUTES_FILE, Probe, load_probes, ownership_mismatches

pytestmark = pytest.mark.e2e

PROBES = load_probes()
COLLISIONS = ["/api/v1/system/tokens", "/api/v1/system/stats", "/api/v1/mcp/servers"]
# Rules registered in Python that are intentionally outside a Python entry (documented in routes.yaml notes).
PYTHON_EXCEPTIONS = {"/api/v1/language", "/api/v1/openapi.json"}


def test_probe_count_matches_expanded_routes() -> None:
    raw = yaml.safe_load(ROUTES_FILE.read_text(encoding="utf-8"))["routes"]
    expected = sum(1 + len(e.get("also", [])) for e in raw)
    assert len(PROBES) == expected
    assert expected >= 15


@pytest.mark.parametrize("probe", PROBES, ids=[p.id for p in PROBES])
def test_declared_owner_answers(ingress: httpx.Client, probe: Probe) -> None:
    resp = ingress.get(probe.request_path())
    assert resp.headers.get("x-api-source") == probe.owner, f"{probe.id} answered {resp.status_code}"


@pytest.mark.parametrize("path", COLLISIONS)
def test_python_documented_paths_under_go_looking_prefixes(ingress: httpx.Client, path: str) -> None:
    resp = ingress.get(path)
    assert resp.headers["x-api-source"] == "python"
    assert resp.status_code == 404
    assert resp.json() == {"code": 404, "message": "not found", "data": None}


@pytest.mark.parametrize("prefix", ["/v1", "/api/v1"])
def test_both_version_prefixes_reach_python(ingress: httpx.Client, prefix: str) -> None:
    resp = ingress.get(f"{prefix}/system-probe-{uuid.uuid4().hex}")
    assert resp.headers["x-api-source"] == "python"
    assert resp.json()["code"] == 404


def test_spa_root_is_html_without_source_header(ingress: httpx.Client) -> None:
    resp = ingress.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "x-api-source" not in resp.headers


def test_python_url_map_is_covered_by_routes_yaml() -> None:
    app = create_app(memory_settings())
    python_entries = [p for p in PROBES if p.owner == "python"]

    def covered(rule: str) -> bool:
        pattern = re.sub(r"<[^>]+>", "x", rule)
        return any((p.match == "exact" and p.path == pattern) or (p.match == "prefix" and pattern.startswith(p.path)) for p in python_entries)

    uncovered = [r.rule for r in app.url_map.iter_rules() if r.endpoint != "static" and r.rule not in PYTHON_EXCEPTIONS and not covered(r.rule)]
    assert uncovered == []


def test_matcher_detects_wrong_owner(ingress: httpx.Client, tmp_path: Path) -> None:
    copy = tmp_path / "routes.yaml"
    shutil.copy(ROUTES_FILE, copy)
    data = yaml.safe_load(copy.read_text(encoding="utf-8"))
    first = next(e for e in data["routes"] if e["path"] == "/health")
    first["owner"] = "python"
    copy.write_text(yaml.safe_dump(data), encoding="utf-8")
    bad = ownership_mismatches(ingress, [p for p in load_probes(copy) if p.path == "/health"])
    assert len(bad) == 1 and "declared python" in bad[0]
