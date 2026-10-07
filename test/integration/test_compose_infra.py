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


# --- Mail catcher is dev-only (D-05, D-20, R-95, R-96); config-only checks, nothing is started ---

MAILPIT_IMAGE = "axllent/mailpit:v1.31.4"
FAKE_ENV_KEYS = ("MYSQL_PASSWORD", "REDIS_PASSWORD", "MINIO_PASSWORD", "ELASTIC_PASSWORD", "MYSQL_ROOT_PASSWORD")


def compose_config(files: list[str], profiles: list[str]) -> dict[str, object]:
    """Resolved compose model with fake secrets and no env file, so it does not depend on docker/.env."""
    env = {**os.environ, **{key: "x" * 32 for key in FAKE_ENV_KEYS}, "SECRET_KEY": "x" * 40}
    cmd = ["docker", "compose", "-p", PROJECT, "--env-file", os.devnull]
    for name in files:
        cmd += ["-f", f"docker/{name}"]
    for name in profiles:
        cmd += ["--profile", name]
    out = sh([*cmd, "config", "--format", "json"], env=env)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_mailpit_exists_only_in_dev_config_under_profile_mail() -> None:
    files = ["docker-compose.yml", "docker-compose.dev.yml"]
    active = compose_config(files, ["mail"])["services"]
    assert "mailpit" in active
    assert active["mailpit"]["image"] == MAILPIT_IMAGE
    assert active["mailpit"]["profiles"] == ["mail"]
    assert "mailpit" not in compose_config(files, ["cpu", "elasticsearch"])["services"]


def test_production_config_has_no_mail_service_with_every_profile_enabled() -> None:
    services = compose_config(["docker-compose.yml"], ["*"])["services"]
    assert services, "profile-expanded production config must list services"
    assert {"app", "es01"} <= set(services), "wildcard profile did not expand"
    for name, service in services.items():
        image = str(service.get("image", ""))
        assert "mailpit" not in name and "mail" not in service.get("profiles", []), name
        assert "mailpit" not in image and "axllent" not in image, f"{name}: {image}"


def test_mailpit_http_port_is_loopback_only() -> None:
    mailpit = compose_config(["docker-compose.yml", "docker-compose.dev.yml"], ["mail"])["services"]["mailpit"]
    ports = mailpit.get("ports", [])
    assert ports, "HTTP API must be published for tests"
    assert all(p.get("host_ip") == "127.0.0.1" for p in ports), ports
    assert {int(p["target"]) for p in ports} == {8025}, "SMTP (1025) must stay inside the network"


def test_mail_helpers_round_trip_through_mailpit() -> None:
    """Live: send one message over SMTP and read it back through the HTTP API (needs `--profile mail`)."""
    import smtplib
    import uuid
    from email.message import EmailMessage

    from test.helpers.mail import base_url, extract_code, wait_for_mail

    smtp_port = int(os.environ.get("MAILPIT_SMTP_PORT", "1025"))
    recipient = f"{uuid.uuid4().hex}@devrag.test"
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = "no-reply@devrag.local", recipient, "devRag verification code"
    msg.set_content("Your code is 123456 and expires soon.")
    container = wait_until(lambda: container_id("mailpit"), timeout=30, describe=lambda: "mailpit not running; start the mail profile")
    ip = sh(["docker", "inspect", "--format", "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}", container]).stdout.strip()
    assert ip, "mailpit has no network address"
    with smtplib.SMTP(ip, smtp_port, timeout=10) as smtp:
        smtp.send_message(msg)
    got = wait_for_mail(recipient)
    assert got["Subject"] == "devRag verification code"
    assert extract_code(got) == "123456"
    assert base_url().startswith("http://127.0.0.1")
