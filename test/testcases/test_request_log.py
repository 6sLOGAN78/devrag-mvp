"""Each request is logged once with method, path, status, duration_ms and no credentials (API-11, T-14-03)."""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

import httpx
import pytest

from test.helpers.accounts import Account
from test.helpers.wait import wait_until
from test.testcases.conftest import LOG_DIR

pytestmark = pytest.mark.e2e


def _find(log: Path, path: str) -> dict[str, Any] | None:
    if not log.is_file():
        return None
    for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
        if path not in line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if rec.get("path") == path:
            return rec
    return None


# Both engines reject the made-up bearer value (401): Go since plan 02-10, Python since plan 02-14.
@pytest.mark.parametrize(("prefix", "logfile", "status"), [("/api/v1/logprobe-", "ragflow_server.log", 401), ("/v1/user/logprobe-", "ragflow_go.log", 401)])
def test_request_is_logged_without_credentials(ingress: httpx.Client, prefix: str, logfile: str, status: int) -> None:
    token = uuid.uuid4().hex
    path = f"{prefix}{token}"
    secret = f"secret-token-{token}"
    resp = ingress.get(path, headers={"Authorization": f"Bearer {secret}"})
    assert resp.status_code == status
    rec = wait_until(lambda: _find(LOG_DIR / logfile, path), timeout=30, interval=0.5)
    assert rec["method"] == "GET"
    assert rec["status"] == status
    assert isinstance(rec["duration_ms"], int | float)
    assert secret not in json.dumps(rec)
    assert secret not in (LOG_DIR / logfile).read_text(encoding="utf-8", errors="replace")


def test_authenticated_go_request_is_logged_without_the_token(ingress: httpx.Client, account: Account) -> None:
    path = f"/v1/user/logprobe-{uuid.uuid4().hex}"
    resp = ingress.get(path, headers={"Authorization": f"Bearer {account.token}", "Cookie": f"ragflow_auth={account.token}"})
    assert resp.status_code == 404
    rec = wait_until(lambda: _find(LOG_DIR / "ragflow_go.log", path), timeout=30, interval=0.5)
    assert rec["status"] == 404
    assert account.token not in json.dumps(rec)
    assert account.token not in (LOG_DIR / "ragflow_go.log").read_text(encoding="utf-8", errors="replace")


def test_unauthenticated_python_request_is_logged_as_401(ingress: httpx.Client) -> None:
    path = f"/api/v1/logprobe-{uuid.uuid4().hex}"
    resp = ingress.get(path)
    assert resp.status_code == 401
    rec = wait_until(lambda: _find(LOG_DIR / "ragflow_server.log", path), timeout=30, interval=0.5)
    assert rec["method"] == "GET" and rec["status"] == 401
    assert isinstance(rec["duration_ms"], int | float)


def test_authenticated_python_request_is_logged_without_the_token(ingress: httpx.Client, account: Account) -> None:
    path = f"/api/v1/logprobe-{uuid.uuid4().hex}"
    resp = ingress.get(path, headers={"Authorization": f"Bearer {account.token}", "Cookie": f"ragflow_auth={account.token}"})
    assert resp.status_code == 404
    rec = wait_until(lambda: _find(LOG_DIR / "ragflow_server.log", path), timeout=30, interval=0.5)
    assert rec["status"] == 404
    assert account.token not in json.dumps(rec)
    assert account.token not in (LOG_DIR / "ragflow_server.log").read_text(encoding="utf-8", errors="replace")


def test_python_cookie_credential_is_ignored_on_api_routes_and_never_logged(ingress: httpx.Client, account: Account) -> None:
    path = f"/api/v1/logprobe-{uuid.uuid4().hex}"
    resp = ingress.get(path, headers={"Cookie": f"ragflow_auth={account.token}"})
    assert resp.status_code == 401, "api routes never read the cookie (D-21)"
    rec = wait_until(lambda: _find(LOG_DIR / "ragflow_server.log", path), timeout=30, interval=0.5)
    assert rec["status"] == 401
    assert account.token not in json.dumps(rec)
    assert account.token not in (LOG_DIR / "ragflow_server.log").read_text(encoding="utf-8", errors="replace")
