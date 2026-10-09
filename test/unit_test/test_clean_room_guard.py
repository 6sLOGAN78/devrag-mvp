"""scripts/clean_room.sh refuses any compose project except devrag-stack before touching Docker (T-15-01, B-05)."""
from __future__ import annotations

import os
import subprocess
import sys
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


# --- Phase 2 exit gate (plan 02-26): mail profile, dev overlay, test environment --------------------------------

R94_DEFAULTS = {
    "RATE_LIMIT_REGISTER_PER_IP": "10",
    "RATE_LIMIT_REGISTER_WINDOW_SECONDS": "3600",
    "RATE_LIMIT_LOGIN_FAILURES_PER_EMAIL": "5",
    "RATE_LIMIT_LOGIN_PER_IP": "30",
    "RATE_LIMIT_LOGIN_WINDOW_SECONDS": "900",
    "RATE_LIMIT_OTP_EMAIL_INTERVAL_SECONDS": "60",
    "RATE_LIMIT_OTP_PER_EMAIL_PER_HOUR": "5",
    "RATE_LIMIT_OTP_PER_IP_PER_HOUR": "20",
    "RATE_LIMIT_OTP_WINDOW_SECONDS": "3600",
}


def _compose_line() -> str:
    lines = [line for line in SCRIPT.read_text().splitlines() if line.startswith("COMPOSE=(")]
    assert len(lines) == 1
    return lines[0]


def test_gate_stack_uses_the_mail_profile_and_the_dev_overlay() -> None:
    line = _compose_line()
    assert "--profile mail" in line, "password-reset e2e and live tests need the dev mail catcher"
    assert "-f docker/docker-compose.dev.yml" in line, "the per-IP rate-limit overlay lives in the dev file"
    assert "--profile cpu" in line and "--profile elasticsearch" in line


def test_gate_exports_the_environment_host_run_tiers_need_without_printing_it() -> None:
    text = SCRIPT.read_text()
    # Without these the Go scratch-database tests skip and the fixture tests fail; a gate must run them for real.
    assert 'export SERVICE_CONF="${SERVICE_CONF:-$ROOT/conf/service_conf.yaml}"' in text
    assert "export MYSQL_ROOT_PASSWORD" in text
    code = [line for line in text.splitlines() if not line.lstrip().startswith("#")]
    assert not [line for line in code if "echo" in line and "MYSQL_ROOT_PASSWORD" in line and "missing" not in line]


def test_production_compose_has_no_mail_service_and_r94_rate_limit_defaults() -> None:
    import yaml

    prod_text = (ROOT / "docker" / "docker-compose.yml").read_text()
    for name in ("docker-compose.yml", "docker-compose-base.yml"):
        services = yaml.safe_load((ROOT / "docker" / name).read_text()).get("services") or {}
        assert "mailpit" not in services, name
        assert not [svc for svc, body in services.items() if "mail" in (body.get("profiles") or [])], name
    for key, default in R94_DEFAULTS.items():
        assert f"{key}: ${{{key}:-{default}}}" in prod_text, key


# --- Plan 03-27: the live_model gate step (D-02, D-04, D-29) ----------------------------------------------------

def test_live_model_step_sits_between_e2e_serial_and_go_race() -> None:
    names = [line.strip().split()[1] for line in SCRIPT.read_text().splitlines() if line.strip().startswith("step ") and len(line.strip().split()) > 2]
    assert "live-model" in names
    assert names.index("live-model") == names.index("e2e-serial") + 1
    assert names.index("live-model") == names.index("go-race") - 1


def test_live_model_step_command_is_exactly_the_marker_run() -> None:
    lines = [line.strip() for line in SCRIPT.read_text().splitlines() if line.strip().startswith("step live-model ")]
    assert lines == ["step live-model uv run python run_tests.py -m live_model"]


def test_gate_script_never_names_or_exports_the_provider_key() -> None:
    code = [line for line in SCRIPT.read_text().splitlines() if not line.lstrip().startswith("#")]
    assert not [line for line in code if "OPENROUTER" in line]
    assert not [line for line in code if line.lstrip().startswith("export") and "KEY" in line.upper()]


def test_gate_preflight_requires_the_live_key() -> None:
    lines = [line.strip() for line in SCRIPT.read_text().splitlines() if line.strip().startswith("step preflight ")]
    assert lines == ["step preflight env PREFLIGHT_REQUIRE_LIVE_KEY=1 scripts/preflight.sh"]



def test_live_test_file_carries_the_fixed_failure_message_and_no_skip() -> None:
    text = (ROOT / "test" / "testcases" / "test_live_models.py").read_text()
    assert "OPENROUTER_API_KEY is missing from docker/.env" in text
    assert "pytest.fail(" in text
    assert "skip" not in text and "xfail" not in text
    assert "pytestmark = pytest.mark.live_model" in text
    assert "pytest.mark.e2e" not in text and "pytest.mark.integration" not in text


def test_without_the_key_the_live_tier_fails_and_does_not_skip(tmp_path: Path) -> None:
    """The fixture's lookup is pointed at an empty environment; no network and no provider call is involved."""
    (tmp_path / "no_key_plugin.py").write_text(
        "def pytest_configure(config):\n"
        "    import test.testcases.test_live_models as live\n"
        "    live.stack_env = lambda: {}\n"
    )
    env = {**os.environ, "PYTHONPATH": f"{tmp_path}{os.pathsep}{ROOT}"}
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-p", "no_key_plugin", "-m", "live_model", "-q", "-k", "test_provider_saves", "test/testcases/test_live_models.py"],
        capture_output=True, text=True, env=env, check=False, cwd=ROOT,
    )
    output = result.stdout + result.stderr
    assert result.returncode != 0, output
    assert "OPENROUTER_API_KEY is missing from docker/.env" in output
    assert "skipped" not in output.lower()
