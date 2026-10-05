"""Fixture self-tests for check_no_sleep.py (patterns are assembled so this file never matches itself)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "check_no_sleep.py"
pytestmark = pytest.mark.unit
PY_SLEEP = "import time\ntime.sl" + "eep(1)\n"
ASYNC_SLEEP = "import asyncio\nasync def f():\n    await asyncio.sl" + "eep(1)\n"
GO_SLEEP = "package x\nfunc F() {\n\ttime.Sl" + "eep(1)\n}\n"
TS_TIMEOUT = "export const a = () => set" + "Timeout(() => 1, 5);\n"


def run(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(SCRIPT), "--root", str(root)], capture_output=True, text=True, timeout=60, check=False)


def put(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.mark.parametrize(
    ("rel", "body"),
    [
        ("test/test_x.py", PY_SLEEP),
        ("test/test_x.py", ASYNC_SLEEP),
        ("internal/x_test.go", GO_SLEEP),
        ("web/src/a.test.ts", TS_TIMEOUT),
        ("web/src/test/b.tsx", TS_TIMEOUT),
    ],
)
def test_sleep_in_test_path_fails(tmp_path: Path, rel: str, body: str) -> None:
    put(tmp_path, rel, body)
    r = run(tmp_path)
    assert r.returncode == 1, r.stdout
    assert f"{rel}:" in r.stdout


@pytest.mark.parametrize(
    ("rel", "body"),
    [
        ("test/helpers/wait.py", PY_SLEEP),
        ("internal/testutil/wait.go", GO_SLEEP),
        ("web/src/test/wait-until.ts", TS_TIMEOUT),
    ],
)
def test_the_three_helper_files_are_allowed(tmp_path: Path, rel: str, body: str) -> None:
    put(tmp_path, rel, body)
    assert run(tmp_path).returncode == 0


def test_production_trees_are_not_scanned(tmp_path: Path) -> None:
    put(tmp_path, "api/retry.py", PY_SLEEP)
    assert run(tmp_path).returncode == 0


def test_comment_mentions_pass(tmp_path: Path) -> None:
    put(tmp_path, "test/test_x.py", "# never call time.sl" + "eep(1) here\nx = 1\n")
    assert run(tmp_path).returncode == 0
