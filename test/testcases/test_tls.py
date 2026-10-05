"""TLS variant with a self-signed certificate pinned as the trust anchor (DEPLOY-12, B-10)."""
from __future__ import annotations

import ssl
import subprocess

import httpx
import pytest

from test.conftest import REPO_ROOT
from test.helpers.wait import wait_until
from test.testcases.conftest import BASE_URL, HTTPS_PORT, compose, service_health

pytestmark = [pytest.mark.e2e, pytest.mark.serial]

CERT = REPO_ROOT / "docker" / "nginx" / "certs" / "server.crt"
TLS_FILE = "docker/docker-compose.tls.yml"
HTTPS = f"https://127.0.0.1:{HTTPS_PORT}"


def _https_ok(client: httpx.Client) -> bool:
    try:
        return client.get("/health").status_code == 200 and client.get("/api/v1/system/healthz").status_code == 200
    except httpx.HTTPError:
        return False


def _http_ok() -> bool:
    try:
        return httpx.get(f"{BASE_URL}/health", timeout=5.0).status_code == 200 and httpx.get(f"{BASE_URL}/api/v1/system/healthz", timeout=5.0).status_code == 200
    except httpx.HTTPError:
        return False


def test_tls_variant_routes_identically_and_restores() -> None:
    if not CERT.is_file():
        gen = subprocess.run(["scripts/gen_selfsigned.sh"], capture_output=True, text=True, check=False, cwd=REPO_ROOT, timeout=60)
        assert gen.returncode == 0, gen.stderr
    assert CERT.is_file()
    try:
        up = compose("up", "-d", "--no-deps", "--force-recreate", "app", extra_files=(TLS_FILE,))
        assert up.returncode == 0, up.stderr
        with httpx.Client(base_url=HTTPS, verify=ssl.create_default_context(cafile=str(CERT)), timeout=5.0, follow_redirects=False) as tls:
            wait_until(lambda: _https_ok(tls), timeout=120, interval=1)
            health = tls.get("/health")
            assert health.headers["x-api-source"] == "go"
            assert tls.get("/api/v1/system/healthz").headers["x-api-source"] == "python"
        redirect = httpx.get(f"{BASE_URL}/health", timeout=5.0, follow_redirects=False)
        assert redirect.status_code in (301, 308)
        assert redirect.headers["location"].startswith("https://")
    finally:
        down = compose("up", "-d", "--no-deps", "--force-recreate", "app")
        wait_until(_http_ok, timeout=180, interval=1)
        wait_until(lambda: service_health("app") == "healthy", timeout=180, interval=2)
        assert down.returncode == 0, down.stderr
    assert httpx.get(f"{BASE_URL}/api/v1/system/healthz", timeout=5.0).headers["x-api-source"] == "python"
