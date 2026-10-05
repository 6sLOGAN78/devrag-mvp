from __future__ import annotations

import asyncio
import json
import subprocess
from typing import Any

import pytest

from api.apps import create_app
from common.settings import load_settings
from test.helpers.wait import wait_until

pytestmark = pytest.mark.integration

PROJECT = "devrag-stack"
PATHS = ("/api/v1/system/healthz", "/system/healthz", "/api/v1/system/status", "/system/status")
HEALTHY = {"database": "ok", "redis": "ok", "storage": "ok", "doc_store": "ok"}


def fetch(path: str) -> tuple[int, str]:
    """GET ``path`` against a fresh in-process app wired to the live stack."""

    async def run() -> tuple[int, str]:
        resp = await create_app(load_settings()).test_client().get(path)
        return resp.status_code, await resp.get_data(as_text=True)

    return asyncio.run(run())


def _compose(*args: str) -> None:
    subprocess.run(["docker", "compose", "-p", PROJECT, *args], check=True, capture_output=True, timeout=120)  # noqa: S603,S607


@pytest.mark.parametrize("path", PATHS)
def test_all_four_urls_healthy(path):
    status, text = fetch(path)
    body: dict[str, Any] = json.loads(text)
    assert status == 200 and body["code"] == 0
    assert body["data"]["engine"] == "python" and body["data"]["status"] == "ok"
    assert {k: v["status"] for k, v in body["data"]["checks"].items()} == HEALTHY


@pytest.mark.serial
def test_redis_down_gives_503_without_hostname_then_recovers():
    _compose("stop", "redis")
    try:
        status, text = wait_until(lambda: (lambda r: r if r[0] == 503 else None)(fetch("/api/v1/system/healthz")), timeout=30, interval=0.25)
        body = json.loads(text)
        assert status == 503 and body["code"] == 503
        assert body["data"]["checks"]["redis"]["status"] == "down"
        assert body["data"]["checks"]["database"]["status"] == "ok"
        assert "127.0.0.1" not in text and "localhost" not in text
    finally:
        _compose("start", "redis")
    wait_until(lambda: fetch("/api/v1/system/healthz")[0] == 200, timeout=60, interval=1)
