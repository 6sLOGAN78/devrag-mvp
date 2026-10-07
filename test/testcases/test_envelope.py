"""One error envelope on both route families, live (API-09)."""
from __future__ import annotations

import uuid

import httpx
import pytest

from test.helpers.accounts import Account

pytestmark = pytest.mark.e2e

LEAKS = ("Traceback", "panic", ".py", ".go", "goroutine")


def _assert_envelope(resp: httpx.Response, code: int) -> None:
    assert resp.status_code == code
    assert resp.headers["content-type"].startswith("application/json")
    body = resp.json()
    assert list(body) == ["code", "message", "data"]
    assert body["code"] == code
    assert body["data"] is None
    assert not [w for w in LEAKS if w in resp.text]


def test_python_unknown_path_is_401_without_token(ingress: httpx.Client) -> None:
    """Python default deny (plan 02-14): an unknown path under the catch-all is 401, not 404."""
    resp = ingress.get(f"/api/v1/does-not-exist-{uuid.uuid4().hex}")
    assert resp.headers["x-api-source"] == "python"
    _assert_envelope(resp, 401)
    assert resp.json()["message"] == "unauthorized"


def test_python_404_envelope(ingress: httpx.Client, account: Account) -> None:
    resp = ingress.get(f"/api/v1/does-not-exist-{uuid.uuid4().hex}", headers={"Authorization": f"Bearer {account.token}"})
    assert resp.headers["x-api-source"] == "python"
    _assert_envelope(resp, 404)


def test_go_405_envelope(ingress: httpx.Client) -> None:
    resp = ingress.post("/health")
    assert resp.headers["x-api-source"] == "go"
    _assert_envelope(resp, 405)


def test_python_405_envelope(ingress: httpx.Client) -> None:
    resp = ingress.post("/api/v1/system/healthz")  # healthz is a public row, so the method error surfaces
    assert resp.headers["x-api-source"] == "python"
    _assert_envelope(resp, 405)


def test_python_405_on_a_protected_route_needs_a_token(ingress: httpx.Client, account: Account) -> None:
    unauth = ingress.post("/api/v1/system/status")
    assert unauth.headers["x-api-source"] == "python"
    _assert_envelope(unauth, 401)
    authed = ingress.post("/api/v1/system/status", headers={"Authorization": f"Bearer {account.token}"})
    assert authed.headers["x-api-source"] == "python"
    _assert_envelope(authed, 405)


def test_go_unknown_protected_path_is_401_without_token(ingress: httpx.Client) -> None:
    """Go default deny (plan 02-10): an unknown path under a protected prefix is 401, not 404."""
    resp = ingress.get(f"/v1/user/probe-{uuid.uuid4().hex}")
    assert resp.headers["x-api-source"] == "go"
    _assert_envelope(resp, 401)


def test_go_404_envelope(ingress: httpx.Client, account: Account) -> None:
    resp = ingress.get(f"/v1/user/probe-{uuid.uuid4().hex}", headers={"Authorization": f"Bearer {account.token}"})
    assert resp.headers["x-api-source"] == "go"
    _assert_envelope(resp, 404)
