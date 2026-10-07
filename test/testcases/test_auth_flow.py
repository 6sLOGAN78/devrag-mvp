"""Cross-stack auth flow through Nginx: a Go-issued token is accepted by Python, logout kills it on both (D-09, D-17, SC2)."""
from __future__ import annotations

import secrets
from collections.abc import Iterator

import httpx
import pytest

from test.helpers.accounts import Account, AccountRegistry
from test.helpers.db import root_connection
from test.testcases.conftest import BASE_URL

pytestmark = pytest.mark.e2e

UNAUTHORIZED = {"code": 401, "message": "unauthorized", "data": None}
PYTHON_PROTECTED = "/api/v1/system/status"
GO_PROTECTED = "/v1/user/info"


@pytest.fixture
def fresh_account(ingress: httpx.Client) -> Iterator[Account]:
    registry = AccountRegistry(BASE_URL)
    try:
        yield registry.register(prefix="authflow")
    finally:
        registry.cleanup()


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_go_token_is_accepted_by_python_and_logout_kills_it_on_both(ingress: httpx.Client, fresh_account: Account) -> None:
    token = fresh_account.token
    py = ingress.get(PYTHON_PROTECTED, headers=_bearer(token))
    assert py.status_code == 200, "a token issued by Go at login is accepted by a protected Python route"
    assert py.headers["x-api-source"] == "python"
    go = ingress.get(GO_PROTECTED, headers=_bearer(token))
    assert go.status_code == 200
    assert go.headers["x-api-source"] == "go"

    logout = ingress.post("/api/v1/auth/logout", headers=_bearer(token))
    assert logout.status_code == 200

    for path in (PYTHON_PROTECTED, GO_PROTECTED):
        resp = ingress.get(path, headers=_bearer(token))
        assert resp.status_code == 401, f"{path} must reject the token after logout"
        assert resp.json() == UNAUTHORIZED


def test_python_accepts_the_go_issued_cookie_for_safe_requests(ingress: httpx.Client, fresh_account: Account) -> None:
    resp = ingress.get(PYTHON_PROTECTED, headers={"Cookie": f"ragflow_auth={fresh_account.token}"})
    assert resp.status_code == 200


def test_python_cookie_only_unsafe_request_needs_a_matching_origin(ingress: httpx.Client, fresh_account: Account) -> None:
    cookie = {"Cookie": f"ragflow_auth={fresh_account.token}"}
    # POST on a known protected Python path: the CSRF check answers 403 before routing decides the method.
    refused = ingress.post(PYTHON_PROTECTED, headers={**cookie, "Origin": "http://evil.test"})
    assert refused.status_code == 403
    assert refused.json() == {"code": 403, "message": "forbidden", "data": None}
    allowed = ingress.post(PYTHON_PROTECTED, headers={**cookie, "Origin": BASE_URL})
    assert allowed.status_code == 405, "the matching origin passes the gate; the route then rejects the method"


def test_tampered_and_foreign_tokens_are_401_on_python(ingress: httpx.Client, fresh_account: Account) -> None:
    token = fresh_account.token
    head, _, tail = token.rpartition(".")
    tampered = f"{head}.{tail[:-1]}{'A' if tail[-1] != 'A' else 'B'}"
    for bad in (tampered, "garbage", "INVALID_" + "0" * 32):
        resp = ingress.get(PYTHON_PROTECTED, headers=_bearer(bad))
        assert resp.status_code == 401 and resp.json() == UNAUTHORIZED


@pytest.fixture
def api_token(fresh_account: Account) -> Iterator[str]:
    """A real api_token row inserted directly: the token CRUD endpoints land in plan 02-20."""
    value = "ragflow-" + secrets.token_urlsafe(32)
    conn = root_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("USE `rag_flow`")
            cur.execute("INSERT INTO `api_token` (`tenant_id`, `token`, `source`) VALUES (%s, %s, 'none')", (fresh_account.tenant_id, value))
        yield value
    finally:
        try:
            with conn.cursor() as cur:
                cur.execute("USE `rag_flow`")
                cur.execute("DELETE FROM `api_token` WHERE `tenant_id` = %s AND `token` = %s", (fresh_account.tenant_id, value))
        finally:
            conn.close()


def test_api_token_is_accepted_on_api_routes_and_refused_on_jwt_only_routes(ingress: httpx.Client, api_token: str) -> None:
    ok = ingress.get("/api/v1/openapi.json", headers=_bearer(api_token))
    assert ok.status_code == 200, "api credential type accepts an api token"
    assert ok.json()["openapi"].startswith("3.")
    refused = ingress.get(PYTHON_PROTECTED, headers=_bearer(api_token))
    assert refused.status_code == 401, "management and status routes are jwt only (T-02-61)"
    assert refused.json() == UNAUTHORIZED
    go_refused = ingress.get(GO_PROTECTED, headers=_bearer(api_token))
    assert go_refused.status_code == 401


def test_unknown_path_is_401_unauthenticated_and_404_with_a_token(ingress: httpx.Client, fresh_account: Account) -> None:
    path = f"/api/v1/auth-flow-probe-{secrets.token_hex(4)}"
    assert ingress.get(path).status_code == 401
    assert ingress.get(path, headers=_bearer(fresh_account.token)).status_code == 404
