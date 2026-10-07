"""WR-05: a route declared auth != none that answers 200 unauthenticated must carry public_until_phase."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from api.apps import create_app
from test.helpers.app import memory_settings
from test.testcases._routes import ROUTES_FILE, load_probes

pytestmark = pytest.mark.unit

# Adding a public auth route needs a conscious edit here plus a DECISIONS row.
# /api/v1/system/version left this set in plan 02-10 (D-19: the Go gate now authenticates it) and
# /api/v1/system/status in plan 02-14 (the Python gate authenticates it). The set is empty from here on.
EXPECTED_MARKED: set[str] = set()


def marker_violations(path: Path = ROUTES_FILE) -> list[str]:
    """Return one message per breach of the public_until_phase rules in a routes file."""
    entries: list[dict[str, Any]] = yaml.safe_load(path.read_text(encoding="utf-8"))["routes"]
    bad: list[str] = []
    marked: set[str] = set()
    for e in entries:
        phase = e.get("public_until_phase")
        if phase is None:
            continue
        marked.add(e["path"])
        if e.get("auth", "none") == "none":
            bad.append(f"{e['path']}: public_until_phase is only legal with auth != none")
        if not isinstance(phase, int) or isinstance(phase, bool):
            bad.append(f"{e['path']}: public_until_phase must be an integer")
        if not str(e.get("note", "")).strip():
            bad.append(f"{e['path']}: public_until_phase requires a note")
    for p in sorted(EXPECTED_MARKED - marked):
        bad.append(f"{p}: expected public_until_phase marker is missing")
    for p in sorted(marked - EXPECTED_MARKED):
        bad.append(f"{p}: unexpected public_until_phase marker (needs a DECISIONS row and test edit)")
    return bad


def test_marker_rules_hold_for_routes_yaml() -> None:
    assert marker_violations() == []


def test_the_marker_set_is_empty() -> None:
    """D-19, WR-25: no route is public by marker any more; the gate on both stacks denies by default."""
    assert EXPECTED_MARKED == set()
    entries = yaml.safe_load(ROUTES_FILE.read_text(encoding="utf-8"))["routes"]
    assert [e["path"] for e in entries if "public_until_phase" in e] == []
    assert "public_until_phase:" not in "\n".join(
        line for line in ROUTES_FILE.read_text(encoding="utf-8").splitlines() if not line.lstrip().startswith("#")
    )


def test_status_marker_must_not_return(tmp_path: Path) -> None:
    data = yaml.safe_load(ROUTES_FILE.read_text(encoding="utf-8"))
    entry = next(e for e in data["routes"] if e["path"] == "/api/v1/system/status")
    entry["public_until_phase"] = 2
    entry["note"] = "regression"
    copy = tmp_path / "routes.yaml"
    copy.write_text(yaml.safe_dump(data), encoding="utf-8")
    assert any("/api/v1/system/status" in v and "unexpected" in v for v in marker_violations(copy))


def test_version_marker_must_not_return(tmp_path: Path) -> None:
    data = yaml.safe_load(ROUTES_FILE.read_text(encoding="utf-8"))
    entry = next(e for e in data["routes"] if e["path"] == "/api/v1/system/version")
    entry["public_until_phase"] = 2
    entry["note"] = "regression"
    copy = tmp_path / "routes.yaml"
    copy.write_text(yaml.safe_dump(data), encoding="utf-8")
    assert any("/api/v1/system/version" in v and "unexpected" in v for v in marker_violations(copy))


def test_marker_on_auth_none_route_is_rejected(tmp_path: Path) -> None:
    data = yaml.safe_load(ROUTES_FILE.read_text(encoding="utf-8"))
    entry = next(e for e in data["routes"] if e["path"] == "/health")
    entry["public_until_phase"] = 2
    copy = tmp_path / "routes.yaml"
    copy.write_text(yaml.safe_dump(data), encoding="utf-8")
    assert any("/health" in v and "only legal" in v for v in marker_violations(copy))


async def test_python_unmarked_auth_routes_do_not_answer_200_unauthenticated() -> None:
    client = create_app(memory_settings()).test_client()
    probes = [p for p in load_probes() if p.owner == "python" and p.auth != "none" and p.public_until_phase is None]
    assert probes, "expected at least the Python catch-all auth entries"
    bad = []
    for p in probes:
        resp = await client.get(p.request_path())
        if resp.status_code == 200:
            bad.append(p.id)
    assert bad == []


async def test_python_auth_routes_answer_401_unauthenticated_and_nothing_is_marked() -> None:
    client = create_app(memory_settings()).test_client()
    probes = [p for p in load_probes() if p.owner == "python" and p.auth != "none"]
    assert {p.path for p in probes} >= {"/api/v1/system/status", "/system/status", "/api/", "/v1/"}
    wrong = []
    for p in probes:
        resp = await client.get(p.request_path())
        if resp.status_code != 401:
            wrong.append(f"{p.id}: {resp.status_code}")
    assert wrong == []
