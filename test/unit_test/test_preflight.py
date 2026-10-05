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
    env = {**os.environ, **LOOSE, **overrides}
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
