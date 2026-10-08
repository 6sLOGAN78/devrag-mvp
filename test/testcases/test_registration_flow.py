"""E2E-01 / E2E-02: register and log in through Nginx against the real MySQL and Valkey (plan 02-09)."""
from __future__ import annotations

import httpx
import pymysql
import pytest

from common.security.tokens import valid_inner, verify
from test.conftest import stack_env
from test.helpers.accounts import TEST_PASSWORD, Account, delete_accounts, unique_email, unique_name
from test.helpers.db import root_connection

pytestmark = pytest.mark.e2e


def _secret() -> str:
    # Read when a test runs, not at import: machines without docker/.env (CI) must still collect this module.
    return stack_env()["SECRET_KEY"]


def _register(client: httpx.Client, email: str, password: str = TEST_PASSWORD) -> httpx.Response:
    return client.post("/api/v1/users", json={"email": email, "password": password, "nickname": unique_name("nick")})


def _rows(email: str) -> dict[str, list[dict]]:
    conn = root_connection()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cur:
            cur.execute("USE `rag_flow`")
            cur.execute("SELECT * FROM `user` WHERE `email` = %s", (email,))
            users = list(cur.fetchall())
            out: dict[str, list[dict]] = {"user": users, "tenant": [], "user_tenant": [], "tenant_llm": []}
            for u in users:
                cur.execute("SELECT * FROM `tenant` WHERE `id` = %s", (u["id"],))
                out["tenant"] += list(cur.fetchall())
                cur.execute("SELECT * FROM `user_tenant` WHERE `user_id` = %s", (u["id"],))
                out["user_tenant"] += list(cur.fetchall())
                cur.execute("SELECT * FROM `tenant_llm` WHERE `tenant_id` = %s", (u["id"],))
                out["tenant_llm"] += list(cur.fetchall())
            return out
    finally:
        conn.close()


@pytest.fixture
def cleanup():
    created: list[Account] = []
    yield created
    delete_accounts(created)


def _track(cleanup: list[Account], email: str) -> None:
    rows = _rows(email)
    for u in rows["user"]:
        cleanup.append(Account(email=email, password="", nickname="", user_id=u["id"], tenant_id=u["id"], token=""))


def test_registration_creates_user_tenant_and_owner_row(ingress: httpx.Client, cleanup: list[Account]) -> None:
    email = unique_email("reg")
    resp = _register(ingress, email)
    _track(cleanup, email)
    assert resp.status_code == 200, resp.text
    assert resp.headers["x-api-source"] == "go"
    body = resp.json()
    assert body["code"] == 0
    for banned in ("password", "access_token", "$"):
        assert banned not in resp.text
    rows = _rows(email)
    assert len(rows["user"]) == len(rows["tenant"]) == len(rows["user_tenant"]) == 1
    user, tenant, member = rows["user"][0], rows["tenant"][0], rows["user_tenant"][0]
    assert tenant["id"] == user["id"] == body["data"]["id"] == body["data"]["tenant_id"]
    assert member["role"] == "owner" and member["invited_by"] == user["id"] and member["tenant_id"] == tenant["id"]
    assert user["password"].startswith("pbkdf2:sha256:600000$")
    # E2E-02: default model ids are present (empty strings when nothing is configured), no tenant_llm rows.
    for col in ("llm_id", "embd_id", "rerank_id"):
        assert col in tenant and tenant[col] is not None
    assert rows["tenant_llm"] == []


def test_registration_rejects_short_password_and_duplicate(ingress: httpx.Client, cleanup: list[Account]) -> None:
    email = unique_email("regval")
    short = _register(ingress, email, "1234567")
    assert short.status_code == 400 and short.json()["code"] == 101
    assert _rows(email)["user"] == []
    assert _register(ingress, email).status_code == 200
    _track(cleanup, email)
    dup = _register(ingress, email)
    assert dup.status_code == 409


def test_registration_login_returns_token_python_verifies(ingress: httpx.Client, cleanup: list[Account]) -> None:
    email = unique_email("registration")
    assert _register(ingress, email).status_code == 200
    _track(cleanup, email)
    resp = ingress.post("/api/v1/auth/login", json={"email": email, "password": TEST_PASSWORD})
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    inner = verify(data["token"], _secret())
    assert inner is not None and valid_inner(inner)
    assert data["role"] == "owner" and data["tenant_id"] == data["user"]["id"]
    for col in ("llm_id", "embd_id", "rerank_id"):
        assert col in data
    cookie = resp.headers.get_list("set-cookie")
    assert any(c.startswith("ragflow_auth=") and "HttpOnly" in c and "SameSite=Lax" in c for c in cookie)
    again = ingress.post("/api/v1/auth/login", json={"email": email, "password": TEST_PASSWORD}).json()["data"]["token"]
    assert verify(again, _secret()) == inner  # D-10 shared token
    assert "access_token" not in resp.text and "pbkdf2" not in resp.text and "password" not in resp.text


def test_registration_login_failure_is_generic(ingress: httpx.Client, cleanup: list[Account]) -> None:
    email = unique_email("registration-gen")
    assert _register(ingress, email).status_code == 200
    _track(cleanup, email)
    wrong = ingress.post("/api/v1/auth/login", json={"email": email, "password": "wrong-password-1"})
    ghost = ingress.post("/api/v1/auth/login", json={"email": unique_email("ghost"), "password": "wrong-password-1"})
    assert wrong.status_code == ghost.status_code == 401
    assert wrong.text == ghost.text
    assert "Email or password is incorrect" in wrong.text


def test_registration_login_lockout_after_five_failures(ingress: httpx.Client, cleanup: list[Account]) -> None:
    email = unique_email("registration-lock")
    assert _register(ingress, email).status_code == 200
    _track(cleanup, email)
    for i in range(5):
        r = ingress.post("/api/v1/auth/login", json={"email": email, "password": "wrong-password-1"})
        assert r.status_code == 401, f"failure {i + 1}"
    locked = ingress.post("/api/v1/auth/login", json={"email": email, "password": "wrong-password-1"})
    assert locked.status_code == 429
    assert locked.json()["code"] == 400
    assert int(locked.headers["retry-after"]) > 0


def test_registration_switch_is_reported_by_config(ingress: httpx.Client) -> None:
    body = ingress.get("/api/v1/system/config").json()["data"]
    assert isinstance(body["register_enabled"], bool)
