"""Fixture self-tests for check_placeholders.py."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "check_placeholders.py"
pytestmark = pytest.mark.unit


def run(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(SCRIPT), "--root", str(root)], capture_output=True, text=True, timeout=60, check=False)


def put(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


BAD_PY = [
    ("class FakeEmbedder:\n    pass\n", "fake"),
    ("class MockStore:\n    pass\n", "mock"),
    ("def stub_thing():\n    return 1\n", "stub"),
    ("def f():\n    raise NotImplementedError\n", "NotImplementedError"),
    ("def f():\n    raise NotImplementedError('later')\n", "NotImplementedError"),
    ("x = 1  # TODO later\n", "TODO"),
    ("# FIXME broken\nx = 1\n", "FIXME"),
    ("# XXX hack\nx = 1\n", "XXX"),
    ("from unittest import mock\n", "mock"),
    ("import unittest.mock\n", "mock"),
]


@pytest.mark.parametrize(("body", "needle"), BAD_PY)
def test_python_bad_constructs_fail(tmp_path: Path, body: str, needle: str) -> None:
    put(tmp_path, "api/x.py", body)
    r = run(tmp_path)
    assert r.returncode == 1, r.stdout
    assert "api/x.py:" in r.stdout
    assert needle.lower() in r.stdout.lower()


@pytest.mark.parametrize(
    "rel",
    ["test/test_x.py", "api/tests/test_y.py", "internal/x_test.go", "web/src/a.test.tsx", "web/src/test/helper.ts"],
)
def test_same_constructs_in_test_paths_pass(tmp_path: Path, rel: str) -> None:
    body = "class FakeEmbedder:\n    pass\n// TODO x\n" if rel.endswith((".go", ".ts", ".tsx")) else "class FakeEmbedder:\n    pass\n# TODO x\n"
    put(tmp_path, rel, body)
    put(tmp_path, "api/ok.py", "x = 1\n")
    assert run(tmp_path).returncode == 0


def test_jsx_placeholder_attribute_passes(tmp_path: Path) -> None:
    put(tmp_path, "web/src/pages/x.tsx", 'export const X = () => <input placeholder="x" />;\n')
    r = run(tmp_path)
    assert r.returncode == 0, r.stdout


def test_string_contents_are_not_scanned(tmp_path: Path) -> None:
    put(tmp_path, "web/src/pages/y.tsx", 'const s = "TODO FakeThing // not a comment";\nconst t = `Mock ${1}`;\n')
    assert run(tmp_path).returncode == 0


def test_gate_ok_with_reason_passes(tmp_path: Path) -> None:
    put(tmp_path, "api/x.py", "def f():\n    raise NotImplementedError  # gate-ok: abstract hook, subclasses implement\n")
    assert run(tmp_path).returncode == 0


def test_gate_ok_with_empty_reason_fails(tmp_path: Path) -> None:
    put(tmp_path, "api/x.py", "def f():\n    raise NotImplementedError  # gate-ok:\n")
    r = run(tmp_path)
    assert r.returncode == 1
    assert "api/x.py:" in r.stdout


def test_go_not_implemented_panic_and_fake_identifier_fail(tmp_path: Path) -> None:
    put(tmp_path, "internal/a.go", 'package a\nfunc F() {\n\tpanic("not implemented")\n}\n')
    r = run(tmp_path)
    assert r.returncode == 1 and "internal/a.go:3" in r.stdout
    put(tmp_path, "internal/a.go", "package a\ntype FakeStore struct{}\n")
    r = run(tmp_path)
    assert r.returncode == 1 and "internal/a.go:2" in r.stdout


def test_ts_todo_comment_fails(tmp_path: Path) -> None:
    put(tmp_path, "web/src/lib/a.ts", "export const a = 1;\n// TODO wire this\n")
    r = run(tmp_path)
    assert r.returncode == 1 and "web/src/lib/a.ts:2" in r.stdout


def test_skips_when_tree_absent(tmp_path: Path) -> None:
    r = run(tmp_path)
    assert r.returncode == 0
    assert "skipped: tree absent" in r.stdout


def test_docs_tree_is_never_scanned(tmp_path: Path) -> None:
    put(tmp_path, "docs/api/x.py", "class FakeX:\n    pass\n")
    put(tmp_path, "api/ok.py", "x = 1\n")
    assert run(tmp_path).returncode == 0
