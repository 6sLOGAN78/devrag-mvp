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


PHASE2_CONFIRMED = [33, 36, 91, 95, 98, 100, 101, 102, 103, 104, 105, 106, 108, 109]
PHASE2_AUTO = [34, 35, 40, 88, 89, 90, 92, 93, 94, 96, 97, 99, 107, 110, 111, 112, 113, 114]


def set_status(root: Path, row: int, old: str, new: str) -> None:
    prefix = f"| R-{row:02d} |" if row < 100 else f"| R-{row} |"

    def change(text: str) -> str:
        return "\n".join(line.replace(f"| {old} |", f"| {new} |", 1) if line.startswith(prefix) else line for line in text.splitlines())

    mutate(root, change)


@pytest.mark.parametrize("row", PHASE2_CONFIRMED)
def test_phase2_user_decided_row_must_be_user_confirmed(repo_root, tmp_path, row):
    root = make_root(repo_root, tmp_path)
    set_status(root, row, "user-confirmed", "accepted (auto, not user-reviewed)")
    out = run_gate(repo_root, root)
    assert out.returncode == 1
    assert f"R-{row}: must be user-confirmed" in out.stdout or f"R-{row:02d}: must be user-confirmed" in out.stdout


@pytest.mark.parametrize("row", PHASE2_AUTO)
def test_phase2_auto_row_must_not_be_user_confirmed(repo_root, tmp_path, row):
    root = make_root(repo_root, tmp_path)
    set_status(root, row, "accepted (auto, not user-reviewed)", "user-confirmed")
    out = run_gate(repo_root, root)
    assert out.returncode == 1
    assert "must not be user-confirmed" in out.stdout
