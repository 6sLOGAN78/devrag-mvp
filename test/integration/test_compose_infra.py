"""Live checks of the infrastructure services under compose project devrag-stack (run `make infra-up` first)."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from test.conftest import REPO_ROOT, stack_env
from test.helpers.wait import wait_until

pytestmark = pytest.mark.integration

PROJECT = "devrag-stack"
SERVICES = ["mysql", "redis", "minio", "es01"]
COMPOSE_BASE = ["docker", "compose", "-p", PROJECT, "--env-file", "docker/.env", "-f", "docker/docker-compose-base.yml", "-f", "docker/docker-compose.dev.yml"]


def sh(args: list[str], env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, capture_output=True, text=True, check=False, cwd=REPO_ROOT, env=env)


def container_id(service: str) -> str:
    out = sh(["docker", "ps", "-q", "--filter", f"label=com.docker.compose.project={PROJECT}", "--filter", f"label=com.docker.compose.service={service}"])
    return out.stdout.strip().splitlines()[0] if out.stdout.strip() else ""


@pytest.fixture(scope="module")
def env() -> dict[str, str]:
    values = stack_env()
    if not values:
        pytest.fail("docker/.env is missing: run `make init-env && make infra-up` first")
    return values


@pytest.mark.parametrize("service", SERVICES)
def test_service_is_healthy(service: str) -> None:
    cid = wait_until(lambda: container_id(service), timeout=30, describe=lambda: f"{service} not running; run `make infra-up`")
    status = wait_until(
        lambda: sh(["docker", "inspect", "--format", "{{.State.Health.Status}}", cid]).stdout.strip() == "healthy",
        timeout=300,
        interval=3,
        describe=lambda: sh(["docker", "inspect", "--format", "{{.State.Health.Status}}", cid]).stdout.strip(),
    )
    assert status is True


def mysql_exec(env: dict[str, str], user: str, password: str, sql: str) -> subprocess.CompletedProcess[str]:
    cid = container_id("mysql")
    return sh(
        ["docker", "exec", "-e", "MYSQL_PWD", cid, "mysql", f"-u{user}", "-N", "-B", "-e", sql],
        env={**os.environ, "MYSQL_PWD": password},
    )


def test_database_is_utf8mb4(env: dict[str, str]) -> None:
    out = mysql_exec(env, "root", env["MYSQL_ROOT_PASSWORD"], "SELECT DEFAULT_CHARACTER_SET_NAME FROM information_schema.SCHEMATA WHERE SCHEMA_NAME='rag_flow'")
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "utf8mb4"


def test_app_user_is_least_privilege(env: dict[str, str]) -> None:
    ok = mysql_exec(env, env["MYSQL_USER"], env["MYSQL_PASSWORD"], "USE rag_flow; SELECT 1")
    assert ok.returncode == 0, ok.stderr
    denied = mysql_exec(env, env["MYSQL_USER"], env["MYSQL_PASSWORD"], "CREATE DATABASE should_not_exist")
    assert denied.returncode != 0
    assert "denied" in denied.stderr.lower()


EXPECTED_PORTS = {"mysql": {3306}, "redis": {6379}, "minio": {9000, 9001}, "es01": {9200}}


@pytest.mark.parametrize("service", SERVICES)
def test_ports_bind_loopback_only(service: str) -> None:
    out = sh(["docker", "port", container_id(service)])
    assert out.returncode == 0, out.stderr
    published = set()
    for line in out.stdout.strip().splitlines():
        container_side, _, host_side = line.partition(" -> ")
        assert host_side.startswith("127.0.0.1:"), f"{service}: {line}"
        published.add(int(container_side.split("/")[0]))
    assert published == EXPECTED_PORTS[service]


def test_profiles_and_infinity_never_pulled() -> None:
    out = sh([*COMPOSE_BASE, "config", "--profiles"])
    assert out.returncode == 0, out.stderr
    assert {"elasticsearch", "infinity"} <= set(out.stdout.split())
    images = sh(["docker", "images", "-q", "infiniflow/infinity:v0.7.2-x64-v3"])
    assert images.stdout.strip() == ""


def es_get(env: dict[str, str], path: str) -> dict[str, object]:
    out = sh(["docker", "exec", container_id("es01"), "curl", "-fsS", "-u", f"elastic:{env['ELASTIC_PASSWORD']}", f"http://localhost:9200/{path}"])
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_elasticsearch_cluster_and_watermarks(env: dict[str, str]) -> None:
    health = es_get(env, "_cluster/health")
    assert health["status"] in {"yellow", "green"}
    settings = es_get(env, "_cluster/settings?include_defaults=true&flat_settings=true")
    merged = {**settings["defaults"], **settings["persistent"], **settings["transient"]}  # type: ignore[dict-item]
    assert merged["cluster.routing.allocation.disk.watermark.low"] == "1gb"
    assert merged["cluster.routing.allocation.disk.watermark.flood_stage"] == "500mb"


def test_env_file_is_not_tracked() -> None:
    assert Path(REPO_ROOT / "docker" / ".env").is_file()
    assert sh(["git", "check-ignore", "-q", "docker/.env"]).returncode == 0
