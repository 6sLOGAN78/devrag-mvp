"""scripts/preflight.sh reports each host check with an actionable message (D-29, R-62)."""
from __future__ import annotations

import os
import re
import socket
import subprocess
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "preflight.sh"
LOG = ROOT / "ragflow-logs" / "preflight-overrides.log"

# Defaults that make every check except the one under test pass on any host.
LOOSE = {
    "PREFLIGHT_MIN_DISK_GB": "0",
    "PREFLIGHT_MIN_RAM_MB": "1",
    "PREFLIGHT_MIN_MAP_COUNT": "1",
    "PREFLIGHT_PORTS": "",
}


def run(**overrides: str) -> subprocess.CompletedProcess[str]:
    # Drop PREFLIGHT_* inherited from the caller: the exit gate runs this suite with override variables
    # exported, and an inherited override would mask the failure a test is asserting.
    inherited = {key: value for key, value in os.environ.items() if not key.startswith("PREFLIGHT_")}
    env = {**inherited, **LOOSE, **overrides}
    return subprocess.run([str(SCRIPT)], capture_output=True, text=True, env=env, check=False, cwd=ROOT)


@contextmanager
def listener() -> Iterator[int]:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    sock.listen(1)
    try:
        yield sock.getsockname()[1]
    finally:
        sock.close()


def test_low_disk_fails_with_action() -> None:
    result = run(PREFLIGHT_MIN_DISK_GB="9999")
    assert result.returncode == 1
    assert "FAIL disk" in result.stdout
    assert "ACTION:" in result.stdout and "never pruned automatically" in result.stdout


def test_low_ram_fails() -> None:
    result = run(PREFLIGHT_MIN_RAM_MB="999999")
    assert result.returncode == 1
    assert "FAIL RAM" in result.stdout


def test_low_map_count_fails_and_names_sysctl() -> None:
    result = run(PREFLIGHT_MIN_MAP_COUNT="999999999")
    assert result.returncode == 1
    assert "sudo sysctl -w vm.max_map_count=262144" in result.stdout


def test_map_count_override_is_recorded() -> None:
    result = run(PREFLIGHT_MIN_MAP_COUNT="999999999", PREFLIGHT_ALLOW_LOW_MAP_COUNT="1")
    assert result.returncode == 0, result.stdout
    assert "OVERRIDE recorded" in result.stdout
    assert "PREFLIGHT_ALLOW_LOW_MAP_COUNT" in LOG.read_text(encoding="utf-8")


def test_port_conflict_names_the_port() -> None:
    with listener() as port:
        result = run(PREFLIGHT_PORTS=str(port))
    assert result.returncode == 1
    assert f"FAIL port {port}" in result.stdout
    assert "ACTION:" in result.stdout


def test_disk_override_logs_measured_value_and_still_fails_without_it() -> None:
    result = run(PREFLIGHT_MIN_DISK_GB="9999", PREFLIGHT_ALLOW_LOW_DISK="1")
    assert result.returncode == 0, result.stdout
    assert "OVERRIDE recorded" in result.stdout
    assert re.search(r"WARNING disk: only [0-9.]+ GB free", result.stdout)
    last = LOG.read_text(encoding="utf-8").strip().splitlines()[-1]
    assert re.match(r"\d{4}-\d\d-\d\dT.* PREFLIGHT_ALLOW_LOW_DISK measured=[0-9.]+GB threshold=9999GB", last)
    assert run(PREFLIGHT_MIN_DISK_GB="9999").returncode == 1


def test_project_collision_warns_for_foreign_working_dir() -> None:
    if subprocess.run(["docker", "info"], capture_output=True, check=False).returncode != 0:
        pytest.skip("docker daemon unavailable")
    existing = subprocess.run(
        ["docker", "ps", "-a", "--filter", "label=com.docker.compose.project=devrag", "--format", "{{.ID}}"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    if not existing:
        pytest.skip("no foreign compose project named devrag on this host")
    result = run(COMPOSE_PROJECT_NAME="devrag")
    assert "project name collision" in result.stdout and "B-05" in result.stdout


def test_script_never_executes_prune_or_sysctl() -> None:
    for line in SCRIPT.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        assert not stripped.startswith(("docker system prune", "sudo sysctl", "sysctl -w", "docker volume prune"))


def _fake_docker(tmp_path: Path, labels: list[str]) -> dict[str, str]:
    fake = tmp_path / "bin"
    fake.mkdir()
    docker = fake / "docker"
    docker.write_text(
        "#!/bin/sh\n"
        'case "$*" in\n'
        '  *"{{.ID}}"*) for _ in $FAKE_IDS; do echo id; done ;;\n'
        '  "ps "*) printf "%s" "$FAKE_LABELS" ;;\n'
        "esac\nexit 0\n"
    )
    docker.chmod(0o755)
    return {
        "PATH": f"{fake}:{os.environ['PATH']}",
        "FAKE_IDS": " ".join(str(i) for i in range(len(labels))),
        "FAKE_LABELS": "".join(f"{label}\n" for label in labels),
    }


def test_foreign_label_is_a_warning_by_default_and_a_failure_when_strict(tmp_path: Path) -> None:
    env = _fake_docker(tmp_path, [str(ROOT / "docker"), "/elsewhere/docker"])
    warn = run(**env)
    assert warn.returncode == 0, warn.stdout
    assert "WARNING project name collision" in warn.stdout and "/elsewhere/docker" in warn.stdout
    strict = run(PREFLIGHT_STRICT_PROJECT="1", **env)
    assert strict.returncode == 1
    assert "FAIL project name collision" in strict.stdout and "B-05" in strict.stdout


def test_project_only_skips_host_checks_and_accepts_own_label_with_space_and_at(tmp_path: Path) -> None:
    env = _fake_docker(tmp_path, [str(ROOT / "docker")])
    inherited = {key: value for key, value in os.environ.items() if not key.startswith("PREFLIGHT_")}
    # Impossible thresholds would fail the full run; --project-only must not evaluate them.
    result = subprocess.run(
        [str(SCRIPT), "--project-only"],
        capture_output=True,
        text=True,
        env={**inherited, **env, "PREFLIGHT_MIN_RAM_MB": "999999999", "PREFLIGHT_STRICT_PROJECT": "1"},
        check=False,
        cwd=ROOT,
    )
    assert result.returncode == 0, result.stdout
    assert "FAIL RAM" not in result.stdout and "OK RAM" not in result.stdout


def test_project_only_strict_rejects_foreign_label_and_unknown_argument_exits_2(tmp_path: Path) -> None:
    env = _fake_docker(tmp_path, ["/elsewhere/docker"])
    inherited = {key: value for key, value in os.environ.items() if not key.startswith("PREFLIGHT_")}
    strict = subprocess.run([str(SCRIPT), "--project-only"], capture_output=True, text=True, env={**inherited, **env, "PREFLIGHT_STRICT_PROJECT": "1"}, check=False, cwd=ROOT)
    assert strict.returncode == 1
    assert subprocess.run([str(SCRIPT), "--bogus"], capture_output=True, text=True, check=False, cwd=ROOT).returncode == 2


# --- Plan 03-27: provider key presence check (D-04, D-29) --------------------------------------------------------

FAKE_KEY_TEXT = "marker-value-not-a-real-credential-0123456789"


def _key_checkout(tmp_path: Path, dotenv: str | None) -> tuple[Path, dict[str, str]]:
    root = tmp_path / "desktop x" / "devRag_@"
    (root / "scripts" / "lib").mkdir(parents=True)
    (root / "docker").mkdir()
    (root / "scripts" / "preflight.sh").write_text(SCRIPT.read_text())
    (root / "scripts" / "preflight.sh").chmod(0o755)
    helper = ROOT / "scripts" / "lib" / "compose_project.sh"
    (root / "scripts" / "lib" / helper.name).write_text(helper.read_text())
    if dotenv is not None:
        (root / "docker" / ".env").write_text(dotenv + "\n")
    env = _fake_docker(tmp_path, [])
    return root, env


def _key_run(root: Path, env: dict[str, str], **extra: str) -> subprocess.CompletedProcess[str]:
    inherited = {key: value for key, value in os.environ.items() if not key.startswith(("PREFLIGHT_", "OPENROUTER_"))}
    return subprocess.run([str(root / "scripts" / "preflight.sh")], capture_output=True, text=True, env={**inherited, **LOOSE, **env, **extra}, check=False, cwd=root)


@pytest.mark.parametrize("dotenv", [None, "OPENROUTER_API_KEY=", "SOMETHING_ELSE=1"])
def test_required_missing_key_fails_with_an_action_naming_variable_and_file(tmp_path: Path, dotenv: str | None) -> None:
    root, env = _key_checkout(tmp_path, dotenv)
    result = _key_run(root, env, PREFLIGHT_REQUIRE_LIVE_KEY="1")
    assert result.returncode == 1, result.stdout
    assert "FAIL openrouter key: missing" in result.stdout
    assert re.search(r"ACTION:.*OPENROUTER_API_KEY.*docker/\.env", result.stdout)


def test_required_present_key_passes_and_the_value_is_never_printed(tmp_path: Path) -> None:
    root, env = _key_checkout(tmp_path, f"OPENROUTER_API_KEY={FAKE_KEY_TEXT}")
    result = _key_run(root, env, PREFLIGHT_REQUIRE_LIVE_KEY="1")
    assert result.returncode == 0, result.stdout
    assert "OK openrouter key: present" in result.stdout
    assert FAKE_KEY_TEXT not in result.stdout + result.stderr
    assert FAKE_KEY_TEXT[8:20] not in result.stdout + result.stderr


def test_optional_missing_key_is_informational_and_does_not_fail(tmp_path: Path) -> None:
    root, env = _key_checkout(tmp_path, "OPENROUTER_API_KEY=")
    result = _key_run(root, env)
    assert result.returncode == 0, result.stdout
    assert "INFO openrouter key: missing" in result.stdout
    assert "FAIL openrouter" not in result.stdout


def test_key_check_does_not_store_or_echo_the_value() -> None:
    code = [line for line in SCRIPT.read_text().splitlines() if not line.lstrip().startswith("#") and "OPENROUTER" in line]
    assert code, "the presence check must exist"
    assert all("echo" not in line or "$(" not in line for line in code)
    assert not [line for line in code if re.search(r"^\s*\w+=.*OPENROUTER", line)]
