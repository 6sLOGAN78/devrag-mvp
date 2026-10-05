"""scripts/clean_room.sh refuses any compose project except devrag-stack before touching Docker (T-15-01, B-05)."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "clean_room.sh"


def _run(tmp_path: Path, project: str) -> tuple[subprocess.CompletedProcess[str], Path]:
    log = tmp_path / "calls.log"
    fake = tmp_path / "bin"
    fake.mkdir()
    docker = fake / "docker"
    docker.write_text(f'#!/bin/sh\necho "$@" >> "{log}"\nexit 0\n')
    docker.chmod(0o755)
    env = {**os.environ, "PATH": f"{fake}:{os.environ['PATH']}", "COMPOSE_PROJECT_NAME": project}
    result = subprocess.run([str(SCRIPT), "--runs", "1"], capture_output=True, text=True, env=env, check=False, cwd=ROOT)
    return result, log


@pytest.mark.parametrize("project", ["devrag", "docker", "ragflow"])
def test_foreign_project_is_refused_before_any_docker_call(tmp_path: Path, project: str) -> None:
    result, log = _run(tmp_path, project)
    assert result.returncode == 3
    assert "B-05" in result.stderr
    assert not log.exists()


def test_script_has_single_guarded_volume_removal_and_no_prune() -> None:
    text = SCRIPT.read_text()
    assert text.count("down -v") == 1
    assert text.index("down -v") > text.index("exit 3")
    code = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))
    for word in ("prune", "rmi", "builder", "sleep"):
        assert word not in code
    assert "down -v" not in (ROOT / "Makefile").read_text()
