"""Container-level behaviour of the running `devrag-stack` project (needs `make up` first)."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import urllib.request
from pathlib import Path

import pytest

from test.conftest import REPO_ROOT, stack_env
from test.helpers.wait import wait_until

pytestmark = pytest.mark.integration

PROJECT = stack_env().get("COMPOSE_PROJECT_NAME", "devrag-stack")
WEB_PORT = stack_env().get("SVR_WEB_HTTP_PORT", "8080")
BASE = f"http://127.0.0.1:{WEB_PORT}"
COMPOSE_FILES = ["-f", "docker/docker-compose.yml", "-f", "docker/docker-compose.dev.yml"]
DOCKER = shutil.which("docker") or "docker"


def _run(args: list[str], env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, capture_output=True, text=True, check=False, timeout=120, cwd=REPO_ROOT, env=env)  # noqa: S603


def _compose(*args: str) -> subprocess.CompletedProcess[str]:
    return _run([DOCKER, "compose", "-p", PROJECT, "--env-file", "docker/.env", *COMPOSE_FILES, "--profile", "cpu", *args])


def _container_id(service: str) -> str:
    out = _run([DOCKER, "ps", "-aq", "--filter", f"label=com.docker.compose.project={PROJECT}",
                "--filter", f"label=com.docker.compose.service={service}"]).stdout.split()
    assert out, f"no container for service {service}"
    return out[0]


def _inspect(cid: str, fmt: str) -> str:
    return _run([DOCKER, "inspect", "--format", fmt, cid]).stdout.strip()


def _get(path: str) -> tuple[int, dict[str, str], str]:
    with urllib.request.urlopen(BASE + path, timeout=10) as resp:  # noqa: S310 - fixed http://127.0.0.1 base
        return resp.status, {k.lower(): v for k, v in resp.headers.items()}, resp.read().decode("utf-8", "replace")


def test_init_exited_zero_with_schema_ok() -> None:
    cid = _container_id("init")
    assert _inspect(cid, "{{.State.ExitCode}}") == "0"
    logs = _run([DOCKER, "logs", cid])
    assert "schema OK: 38 tables" in logs.stdout + logs.stderr


def test_app_healthy_with_10s_interval() -> None:
    cid = _container_id("app")
    status = wait_until(lambda: _inspect(cid, "{{.State.Health.Status}}") == "healthy", timeout=120, interval=2)
    assert status
    interval_ns = int(_inspect(cid, "{{json .Config.Healthcheck.Interval}}"))
    assert interval_ns == 10_000_000_000


def test_spa_served_through_nginx() -> None:
    status, _, body = _get("/")
    assert status == 200
    assert '<div id="root">' in body


def test_go_and_python_routes_are_tagged() -> None:
    _, go_headers, _ = _get("/health")
    assert go_headers.get("x-api-source") == "go"
    _, py_headers, _ = _get("/api/v1/system/healthz")
    assert py_headers.get("x-api-source") == "python"


def test_logs_on_host_and_readable() -> None:
    logs = REPO_ROOT / "ragflow-logs"
    for name in ("ragflow_server.log", "ragflow_go.log"):
        path = logs / name
        assert wait_until(lambda p=path: p.is_file() and p.stat().st_size > 0, timeout=60, interval=1), name
        assert os.access(path, os.R_OK), name
        assert path.stat().st_uid == os.getuid(), f"{name} not owned by the invoking user"


def test_app_processes_run_unprivileged() -> None:
    cid = _container_id("app")
    out = _run([DOCKER, "top", cid, "-eo", "pid,uid,args"]).stdout
    rows = [line.split(None, 2)[1:] for line in out.splitlines()[1:] if line.strip()]
    uids = {}
    for uid, args in rows:
        if "ragflow_server --api" in args:
            uids["go"] = uid
        elif "api.ragflow_server" in args:
            uids["python"] = uid
    assert set(uids) == {"go", "python"}, out
    # `docker top` reports host UIDs; with no userns remap these equal the container UIDs.
    assert all(uid == str(os.getuid()) for uid in uids.values()), uids


def test_image_has_no_docs_or_env() -> None:
    cid = _container_id("app")
    proc = _run([DOCKER, "exec", cid, "sh", "-c", "test ! -e /ragflow/docs && test ! -e /ragflow/.env"])
    assert proc.returncode == 0, proc.stderr


def test_published_ports_are_loopback_only() -> None:
    cid = _container_id("app")
    ports = json.loads(_inspect(cid, "{{json .HostConfig.PortBindings}}"))
    published = {proto: [b["HostIp"] + ":" + b["HostPort"] for b in binds] for proto, binds in ports.items()}
    assert set(published) == {"80/tcp", "443/tcp"}
    assert all(addr.startswith("127.0.0.1:") for addrs in published.values() for addr in addrs)


def test_compose_fails_fast_naming_missing_secret() -> None:
    src = REPO_ROOT / "docker" / ".env"
    lines = [ln for ln in src.read_text(encoding="utf-8").splitlines() if not ln.startswith("MYSQL_PASSWORD=")]
    with tempfile.TemporaryDirectory() as tmp:
        env_file = Path(tmp) / "env"
        env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
        env = {k: v for k, v in os.environ.items() if k != "MYSQL_PASSWORD"}
        proc = _run([DOCKER, "compose", "-p", PROJECT, "--env-file", str(env_file), *COMPOSE_FILES,
                     "--profile", "cpu", "config", "-q"], env=env)
    assert proc.returncode != 0
    assert "MYSQL_PASSWORD" in proc.stderr
