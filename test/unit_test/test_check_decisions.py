import shutil
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


def make_root(repo_root: Path, tmp_path: Path) -> Path:
    (tmp_path / ".planning" / "research").mkdir(parents=True)
    shutil.copy(repo_root / ".planning" / "research" / "SUMMARY.md", tmp_path / ".planning" / "research" / "SUMMARY.md")
    shutil.copy(repo_root / ".planning" / "DECISIONS.md", tmp_path / ".planning" / "DECISIONS.md")
    return tmp_path


def run_gate(repo_root: Path, root: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(repo_root / "scripts" / "ci" / "check_decisions.py"), "--root", str(root)],
        capture_output=True,
        text=True,
        check=False,
    )


def mutate(root: Path, fn) -> None:
    path = root / ".planning" / "DECISIONS.md"
    path.write_text(fn(path.read_text(encoding="utf-8")), encoding="utf-8")


def test_real_repo_passes(repo_root):
    out = run_gate(repo_root, repo_root)
    assert out.returncode == 0, out.stdout


def test_missing_row_fails(repo_root, tmp_path):
    root = make_root(repo_root, tmp_path)
    mutate(root, lambda t: "\n".join(line for line in t.splitlines() if not line.startswith("| R-05 |")))
    out = run_gate(repo_root, root)
    assert out.returncode == 1
    assert "R-05: missing" in out.stdout


def test_confirmed_row_set_to_open_fails(repo_root, tmp_path):
    root = make_root(repo_root, tmp_path)

    def change(text: str) -> str:
        return "\n".join(
            line.replace("| user-confirmed |", "| open |", 1) if line.startswith("| R-03 |") else line for line in text.splitlines()
        )

    mutate(root, change)
    out = run_gate(repo_root, root)
    assert out.returncode == 1
    assert "R-03" in out.stdout


def test_invalid_status_fails(repo_root, tmp_path):
    root = make_root(repo_root, tmp_path)

    def change(text: str) -> str:
        return "\n".join(
            line.replace("| accepted (auto, not user-reviewed) |", "| maybe |", 1) if line.startswith("| R-05 |") else line
            for line in text.splitlines()
        )

    mutate(root, change)
    out = run_gate(repo_root, root)
    assert out.returncode == 1
    assert "invalid status" in out.stdout
