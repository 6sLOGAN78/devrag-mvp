"""Layering (API-06): handlers -> services -> models/adapters, enforced on the import graph."""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]


def _imports(path: Path) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module)
            names.update(f"{node.module}.{alias.name}" for alias in node.names)
    return names


def _violations(directory: str, forbidden: tuple[str, ...]) -> list[str]:
    found = []
    for path in sorted((ROOT / directory).rglob("*.py")):
        for name in _imports(path):
            if any(name == f or name.startswith(f + ".") for f in forbidden):
                found.append(f"{path.relative_to(ROOT)} imports {name}")
    return found


def test_apps_do_not_touch_models_database_peewee_or_probes():
    assert _violations("api/apps", ("api.db.models", "api.db.database", "peewee", "common.health")) == []


def test_services_do_not_import_quart():
    assert _violations("api/db/services", ("quart", "quart_schema", "quart_cors")) == []


def test_models_do_not_import_upper_layers():
    assert _violations("api/db/models", ("api.apps", "api.db.services")) == []


def test_detector_flags_a_violation(tmp_path, monkeypatch):
    bad = tmp_path / "x.py"
    bad.write_text("from api.db.models.base import BaseModel\nimport peewee\n")
    assert {"api.db.models.base.BaseModel", "peewee"} <= _imports(bad)
