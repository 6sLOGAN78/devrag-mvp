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
    (root / "scripts" / "lib").mkdir()
    helper = SCRIPTS_SRC / "lib" / "compose_project.sh"
    if helper.exists():
        (root / "scripts" / "lib" / helper.name).write_text(helper.read_text())
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


# --- WR-16: one resolver for clean_room.sh and preflight.sh --------------------------------------------------------

# (docker/.env line or None, COMPOSE_PROJECT_NAME in the environment or None, expected resolved name)
RESOLVE_CASES = [
    ("COMPOSE_PROJECT_NAME=fromfile", None, "fromfile"),
    ('COMPOSE_PROJECT_NAME="quoted"  # note', None, "quoted"),
    ("# COMPOSE_PROJECT_NAME=commented", None, "devrag-stack"),
    (None, "fromenv", "fromenv"),
    (None, None, "devrag-stack"),
    ("COMPOSE_PROJECT_NAME=fromfile", "fromenv", "fromenv"),
]


def _resolve_env(tmp_path: Path, dotenv: str | None, envval: str | None) -> tuple[Path, dict[str, str], Path]:
    root = _checkout(tmp_path)
    (root / "docker").mkdir()
    if dotenv is not None:
        (root / "docker" / ".env").write_text(dotenv + "\n")
    log = tmp_path / "calls.log"
    fake = tmp_path / "bin"
    fake.mkdir()
    docker = fake / "docker"
    docker.write_text(FAKE_DOCKER)
    docker.chmod(0o755)
    env = {key: value for key, value in os.environ.items() if not key.startswith(("PREFLIGHT_", "COMPOSE_"))}
    env.update(PATH=f"{fake}:{os.environ['PATH']}", FAKE_DOCKER_LOG=str(log), FAKE_IDS="", FAKE_LABELS="")
    if envval is not None:
        env["COMPOSE_PROJECT_NAME"] = envval
    return root, env, log


@pytest.mark.parametrize(("dotenv", "envval", "expected"), RESOLVE_CASES)
def test_helper_resolves_project_name(tmp_path: Path, dotenv: str | None, envval: str | None, expected: str) -> None:
    root, env, _ = _resolve_env(tmp_path, dotenv, envval)
    result = subprocess.run(
        ["bash", "-c", f'. "{root}/scripts/lib/compose_project.sh"; resolve_compose_project "{root}"'],
        capture_output=True, text=True, env=env, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == expected


@pytest.mark.parametrize(("dotenv", "envval", "expected"), RESOLVE_CASES)
def test_preflight_and_clean_room_resolve_the_same_project(tmp_path: Path, dotenv: str | None, envval: str | None, expected: str) -> None:
    root, env, _ = _resolve_env(tmp_path, dotenv, envval)
    pre = subprocess.run([str(root / "scripts" / "preflight.sh"), "--project-only"], capture_output=True, text=True, env=env, check=False, cwd=root)
    assert f"'{expected}'" in pre.stdout, pre.stdout
    clean = subprocess.run([str(root / "scripts" / "clean_room.sh"), "--runs", "1"], capture_output=True, text=True, env=env, check=False, cwd=root)
    if expected == "devrag-stack":
        assert "REFUSED" not in clean.stderr
    else:
        assert clean.returncode == 3
        assert f"got '{expected}'" in clean.stderr


def test_guard_inspects_the_project_that_is_torn_down(tmp_path: Path) -> None:
    root, env, log = _resolve_env(tmp_path, "COMPOSE_PROJECT_NAME=myfork", None)
    result = subprocess.run([str(root / "scripts" / "clean_room.sh"), "--runs", "1"], capture_output=True, text=True, env=env, check=False, cwd=root)
    assert result.returncode == 3
    assert "down -v" not in "\n".join(_calls(log))
    assert not any("-p devrag-stack" in call for call in _calls(log))
