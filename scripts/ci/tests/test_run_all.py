"""Self-tests for run_all.py using throwaway gate directories."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "run_all.py"
pytestmark = pytest.mark.unit


def run(scripts_dir: Path, root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(root), "--scripts-dir", str(scripts_dir)],
        capture_output=True, text=True, timeout=60, check=False,
    )


def gate(directory: Path, name: str, code: int) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    if name.endswith(".sh"):
        (directory / name).write_text(f"#!/usr/bin/env bash\necho gate {name}\nexit {code}\n", encoding="utf-8")
    else:
        (directory / name).write_text(f"import sys\nprint('gate {name}')\nsys.exit({code})\n", encoding="utf-8")


def test_all_pass_in_sorted_order(tmp_path: Path) -> None:
    d = tmp_path / "gates"
    gate(d, "check_b.py", 0)
    gate(d, "check_a.py", 0)
    gate(d, "check_c.sh", 0)
    (d / "helper.py").write_text("raise SystemExit(9)\n", encoding="utf-8")
    r = run(d, tmp_path)
    assert r.returncode == 0, r.stdout
    pass_lines = [ln for ln in r.stdout.splitlines() if ln.startswith("PASS")]
    assert pass_lines == ["PASS a", "PASS b", "PASS c"]


def test_any_failure_fails_the_run_but_all_gates_still_run(tmp_path: Path) -> None:
    d = tmp_path / "gates"
    gate(d, "check_a.py", 1)
    gate(d, "check_b.sh", 0)
    r = run(d, tmp_path)
    assert r.returncode == 1
    assert "FAIL a" in r.stdout and "PASS b" in r.stdout


def test_no_gates_is_a_failure(tmp_path: Path) -> None:
    d = tmp_path / "gates"
    d.mkdir()
    assert run(d, tmp_path).returncode == 1
