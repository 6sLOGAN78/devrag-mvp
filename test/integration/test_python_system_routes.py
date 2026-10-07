from __future__ import annotations

import asyncio
import json
import subprocess
from typing import Any

import pytest

from api.apps import create_app
from common.security import tokens
from common.settings import load_settings
from test.helpers.accounts import AccountRegistry
from test.helpers.wait import wait_until

pytestmark = pytest.mark.integration

PROJECT = "devrag-stack"
PATHS = ("/api/v1/system/healthz", "/system/healthz", "/api/v1/system/status", "/system/status")
HEALTHY = {"database": "ok", "redis": "ok", "storage": "ok", "doc_store": "ok"}


def fetch(path: str, token: str | None = None) -> tuple[int, str]:
    """GET ``path`` against a fresh in-process app wired to the live stack (real resolver, real MySQL)."""

    async def run() -> tuple[int, str]:
        headers = {"Authorization": f"Bearer {token}"} if token else None
        resp = await create_app(load_settings()).test_client().get(path, headers=headers)
        return resp.status_code, await resp.get_data(as_text=True)

    return asyncio.run(run())


@pytest.fixture(scope="module")
def session_token() -> Any:
    """A real registered account's token: the status routes need it since plan 02-14 (D-19)."""
    from test.testcases.conftest import BASE_URL

    registry = AccountRegistry(BASE_URL)
    try:
        yield registry.register(prefix="pysys").token
    finally:
        registry.cleanup()


@pytest.fixture(scope="module", autouse=True)
def _bound_database() -> Any:
    """The real resolver reads MySQL through the pooled ``DB``; bind it to the live stack for this module."""
    from api.db.database import DB, init_database

    init_database(load_settings().mysql)
    yield
    DB.close()


def _compose(*args: str) -> None:
    subprocess.run(["docker", "compose", "-p", PROJECT, *args], check=True, capture_output=True, timeout=120)  # noqa: S603,S607


@pytest.mark.parametrize("path", ("/api/v1/system/status", "/system/status"))
def test_status_urls_are_401_without_credentials(path):
    status, text = fetch(path)
    assert status == 401
    assert json.loads(text) == {"code": 401, "message": "unauthorized", "data": None}


def test_status_url_rejects_a_forged_token(session_token):
    forged = tokens.dump("0123456789abcdef0123456789abcdef", "a-different-fake-secret-0123456789abcdef")
    assert fetch("/api/v1/system/status", forged)[0] == 401


@pytest.mark.parametrize("path", PATHS)
def test_all_four_urls_healthy(path, session_token):
    status, text = fetch(path, session_token)
    body: dict[str, Any] = json.loads(text)
    assert status == 200 and body["code"] == 0
    assert body["data"]["engine"] == "python" and body["data"]["status"] == "ok"
    assert {k: v["status"] for k, v in body["data"]["checks"].items()} == HEALTHY


@pytest.mark.serial
def test_redis_down_gives_503_without_hostname_then_recovers():
    _compose("stop", "redis")
    try:
        status, text = wait_until(lambda: (lambda r: r if r[0] == 503 else None)(fetch("/api/v1/system/healthz")), timeout=30, interval=0.25)  # public: no token
        body = json.loads(text)
        assert status == 503 and body["code"] == 503
        assert body["data"]["checks"]["redis"]["status"] == "down"
        assert body["data"]["checks"]["database"]["status"] == "ok"
        assert "127.0.0.1" not in text and "localhost" not in text
    finally:
        _compose("start", "redis")
    wait_until(lambda: fetch("/api/v1/system/healthz")[0] == 200, timeout=60, interval=1)
