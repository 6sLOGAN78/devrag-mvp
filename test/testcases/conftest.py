"""Fixtures for tests that run against the live compose stack (`make up` first)."""
from __future__ import annotations

import shutil
import subprocess
from collections.abc import Iterator

import httpx
import pytest

from test.conftest import REPO_ROOT, stack_env
from test.helpers.wait import wait_until

ENV = stack_env()
PROJECT = ENV.get("COMPOSE_PROJECT_NAME", "devrag-stack")
HTTP_PORT = ENV.get("SVR_WEB_HTTP_PORT", "8080")
HTTPS_PORT = ENV.get("SVR_WEB_HTTPS_PORT", "8443")
BASE_URL = f"http://127.0.0.1:{HTTP_PORT}"
LOG_DIR = REPO_ROOT / "ragflow-logs"
DOCKER = shutil.which("docker") or "docker"
COMPOSE_BASE = [DOCKER, "compose", "-p", PROJECT, "--env-file", "docker/.env", "-f", "docker/docker-compose.yml", "-f", "docker/docker-compose.dev.yml", "--profile", "cpu"]


def compose(*args: str, extra_files: tuple[str, ...] = (), timeout: float = 180) -> subprocess.CompletedProcess[str]:
    """Run docker compose against project ``devrag-stack`` only."""
    files: list[str] = []
    for f in extra_files:
        files += ["-f", f]
    cmd = [*COMPOSE_BASE, *files, *args]
    return subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=timeout, cwd=REPO_ROOT)


def _ready(client: httpx.Client) -> bool:
    try:
        return client.get("/health").status_code == 200 and client.get("/api/v1/system/healthz").status_code == 200
    except httpx.HTTPError:
        return False


@pytest.fixture(scope="session")
def ingress() -> Iterator[httpx.Client]:
    with httpx.Client(base_url=BASE_URL, timeout=5.0, follow_redirects=False) as client:
        try:
            wait_until(lambda: _ready(client), timeout=120, interval=1)
        except TimeoutError as exc:
            pytest.fail(f"stack is not ready at {BASE_URL}; run `make up` first ({exc})")
        yield client


@pytest.fixture(scope="session")
def stack_ready(ingress: httpx.Client) -> httpx.Client:
    return ingress


def exec_app(*cmd: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([DOCKER, "compose", "-p", PROJECT, "exec", "-T", "app", *cmd], capture_output=True, text=True, check=False, timeout=60, cwd=REPO_ROOT)


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Destructive (serial) tests run last so an outage never overlaps ordinary live tests."""
    items.sort(key=lambda item: item.get_closest_marker("serial") is not None)  # stable sort


def service_health(service: str) -> str:
    """Docker health status of a ``devrag-stack`` service container ('' when absent)."""
    ids = subprocess.run(
        [DOCKER, "ps", "-aq", "--filter", f"label=com.docker.compose.project={PROJECT}", "--filter", f"label=com.docker.compose.service={service}"],
        capture_output=True, text=True, check=False, timeout=30,
    ).stdout.split()
    if not ids:
        return ""
    out = subprocess.run([DOCKER, "inspect", "--format", "{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}", ids[0]], capture_output=True, text=True, check=False, timeout=30)
    return out.stdout.strip()
