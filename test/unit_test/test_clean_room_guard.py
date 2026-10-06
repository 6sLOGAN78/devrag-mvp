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


# --- WR-15 / WR-16: --runs validation, foreign-checkout refusal, uncached go-race ---------------------------------

SCRIPTS_SRC = Path(os.environ.get("GUARD_TEST_SCRIPTS_DIR", str(ROOT / "scripts")))

FAKE_DOCKER = """#!/bin/sh
echo "$@" >> "$FAKE_DOCKER_LOG"
case "$*" in
  *"{{.ID}}"*) for _ in $FAKE_IDS; do echo id; done; exit 0 ;;
  "ps "*) printf '%s' "$FAKE_LABELS"; exit 0 ;;
  *" stop"*) exit 1 ;;
esac
exit 0
"""


def _checkout(tmp_path: Path) -> Path:
    """A throwaway checkout whose path has a space and an '@', like the real repo path."""
    root = tmp_path / "desktop x" / "devRag_@"
    (root / "scripts").mkdir(parents=True)
    for name in ("clean_room.sh", "preflight.sh"):
        target = root / "scripts" / name
        target.write_text((SCRIPTS_SRC / name).read_text())
        target.chmod(0o755)
    return root


def _guard(tmp_path: Path, args: list[str], labels: list[str] | None = None, project: bool = True) -> tuple[subprocess.CompletedProcess[str], Path]:
    root = _checkout(tmp_path)
    log = tmp_path / "calls.log"
    fake = tmp_path / "bin"
    fake.mkdir()
    docker = fake / "docker"
    docker.write_text(FAKE_DOCKER)
    docker.chmod(0o755)
    labels = labels if labels is not None else []
    env = {key: value for key, value in os.environ.items() if not key.startswith(("PREFLIGHT_", "COMPOSE_"))}
    env.update(
        PATH=f"{fake}:{os.environ['PATH']}",
        FAKE_DOCKER_LOG=str(log),
        FAKE_IDS=" ".join(str(i) for i in range(len(labels))),
        FAKE_LABELS="".join(f"{label}\n" for label in labels),
    )
    result = subprocess.run([str(root / "scripts" / "clean_room.sh"), *args], capture_output=True, text=True, env=env, check=False, cwd=root)
    return result, log


def _calls(log: Path) -> list[str]:
    return log.read_text().splitlines() if log.exists() else []


@pytest.mark.parametrize("args", [["--runs", "0"], ["--runs", "abc"], ["--runs", ""], ["--runs", "-1"], ["--runs", "1.5"], ["--runs"]])
def test_invalid_runs_exit_2_before_any_docker_call(tmp_path: Path, args: list[str]) -> None:
    result, log = _guard(tmp_path, args)
    assert result.returncode == 2, result.stderr
    assert "positive integer" in result.stderr
    assert not log.exists()


def test_foreign_checkout_is_refused_before_stop_or_down(tmp_path: Path) -> None:
    result, log = _guard(tmp_path, ["--runs", "1"], ["/elsewhere/docker"])
    assert result.returncode != 0
    assert "B-05" in result.stdout + result.stderr
    assert "/elsewhere/docker" in result.stdout + result.stderr
    assert not any(" stop" in f" {call}" or "down" in call.split() for call in _calls(log))


def test_foreign_label_among_local_ones_is_refused(tmp_path: Path) -> None:
    local = str(tmp_path / "desktop x" / "devRag_@" / "docker")
    result, log = _guard(tmp_path, ["--runs", "1"], [local, "/elsewhere/docker"])
    assert result.returncode != 0
    assert not any(" stop" in f" {call}" for call in _calls(log))


@pytest.mark.parametrize("labels", [[], ["LOCAL"], ["LOCAL", "LOCAL"]])
def test_own_checkout_with_space_and_at_is_accepted(tmp_path: Path, labels: list[str]) -> None:
    local = str(tmp_path / "desktop x" / "devRag_@" / "docker")
    result, log = _guard(tmp_path, ["--runs", "1"], [local if x == "LOCAL" else x for x in labels])
    assert "project name collision" not in result.stdout
    assert any(" stop" in f" {call}" for call in _calls(log)), result.stdout + result.stderr


def test_go_race_step_is_uncached_and_guard_precedes_volume_removal() -> None:
    text = SCRIPT.read_text()
    race = [line for line in text.splitlines() if "step go-race" in line]
    assert len(race) == 1 and "-count=1" in race[0]
    assert text.count("down -v") == 1
    assert text.index("down -v") > text.index("project-guard") > text.index("exit 3")
    assert "project-only" in text
