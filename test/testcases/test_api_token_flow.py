"""API tokens end to end through Nginx: Go creates them, both engines resolve them (AUTH-19..23, SC3).

``/api/v1/probe-<uuid>`` is a path no Python handler serves: it lands in the Python catch-all, which
carries the ``api`` policy, so 404 proves the gate accepted the credential and 401 proves it refused it.
"""
from __future__ import annotations

import json
import re
import uuid
from collections.abc import Iterator
from typing import Any

import httpx
import pytest

from test.helpers.accounts import Account, AccountRegistry
from test.helpers.wait import wait_until
from test.testcases.conftest import BASE_URL, LOG_DIR

pytestmark = pytest.mark.e2e

UNAUTHORIZED = {"code": 401, "message": "unauthorized", "data": None}
NOT_FOUND_TOKEN = {"code": 404, "message": "token not found", "data": None}
API_TOKEN = re.compile(r"^ragflow-[A-Za-z0-9_-]{43}$")
BETA_TOKEN = re.compile(r"^[0-9a-f]{32}$")
TOKENS = "/api/v1/system/tokens"


@pytest.fixture
def accounts() -> Iterator[tuple[Account, Account]]:
    registry = AccountRegistry(BASE_URL)
    try:
        yield registry.two_accounts()
    finally:
        registry.cleanup()


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _probe() -> str:
    return f"/api/v1/probe-{uuid.uuid4().hex}"


def _create(ingress: httpx.Client, account: Account) -> dict[str, Any]:
    resp = ingress.post(TOKENS, headers=_bearer(account.token))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["code"] == 0
    return body["data"]


def test_api_token_flow_create_list_and_use_on_python_api_route(ingress: httpx.Client, accounts: tuple[Account, Account]) -> None:
    alice, bob = accounts
    created = _create(ingress, alice)
    assert API_TOKEN.match(created["token"]) and BETA_TOKEN.match(created["beta"])
    assert "dialog_id" not in created and "tenant_id" not in created
    second = _create(ingress, alice)
    assert second["token"] != created["token"]

    listed = ingress.get(TOKENS, headers=_bearer(alice.token))
    assert listed.status_code == 200 and listed.headers["x-api-source"] == "go"
    assert {t["token"] for t in listed.json()["data"]} == {created["token"], second["token"]}
    assert ingress.get(TOKENS, headers=_bearer(bob.token)).json()["data"] == [], "another tenant sees none of them"

    probe = _probe()
    ok = ingress.get(probe, headers=_bearer(created["token"]))
    assert ok.status_code == 404 and ok.headers["x-api-source"] == "python", "an API token alone passes the Python gate"
    bad = ingress.get(probe, headers=_bearer("ragflow-" + "A" * 43))
    assert bad.status_code == 401 and bad.json() == UNAUTHORIZED


def test_api_token_flow_token_cannot_reach_jwt_only_routes_or_manage_tokens(ingress: httpx.Client, accounts: tuple[Account, Account]) -> None:
    alice, _ = accounts
    created = _create(ingress, alice)
    for method, path in [("GET", TOKENS), ("POST", TOKENS), ("DELETE", f"{TOKENS}/{created['token']}"), ("GET", "/v1/user/info"), ("GET", "/api/v1/system/status")]:
        for credential in (created["token"], created["beta"]):
            resp = ingress.request(method, path, headers=_bearer(credential))
            assert resp.status_code == 401, f"{method} {path}"
            assert resp.json() == UNAUTHORIZED
    assert len(ingress.get(TOKENS, headers=_bearer(alice.token)).json()["data"]) == 1, "nothing was minted or removed"


def test_api_token_flow_other_tenant_cannot_delete_and_owner_delete_revokes_on_both_engines(ingress: httpx.Client, accounts: tuple[Account, Account]) -> None:
    alice, bob = accounts
    created = _create(ingress, alice)
    token = created["token"]

    foreign = ingress.delete(f"{TOKENS}/{token}", headers=_bearer(bob.token))
    missing = ingress.delete(f"{TOKENS}/ragflow-{'B' * 43}", headers=_bearer(bob.token))
    assert foreign.status_code == missing.status_code == 404
    assert foreign.json() == missing.json() == NOT_FOUND_TOKEN
    assert ingress.get(_probe(), headers=_bearer(token)).status_code == 404, "the foreign delete changed nothing"

    gone = ingress.delete(f"{TOKENS}/{token}", headers=_bearer(alice.token))
    assert gone.status_code == 200 and gone.json()["code"] == 0
    after = ingress.get(_probe(), headers=_bearer(token))
    assert after.status_code == 401 and after.json() == UNAUTHORIZED
    assert ingress.get("/api/v1/searchbots/probe", headers=_bearer(created["beta"])).status_code == 401, "the Go gate refuses it too"
    assert ingress.get(TOKENS, headers=_bearer(alice.token)).json()["data"] == []


def test_api_token_flow_beta_value_is_refused_by_python_api_routes_and_go_beta_routes_need_a_row(ingress: httpx.Client, accounts: tuple[Account, Account]) -> None:
    alice, _ = accounts
    created = _create(ingress, alice)
    assert ingress.get(_probe(), headers=_bearer(created["beta"])).status_code == 401, "api routes do not accept the beta value"
    # /api/v1/searchbots/ is a Go beta family; no handler exists until Phase 8, so a valid beta gets 404 (gate passed).
    passed = ingress.get(f"/api/v1/searchbots/probe-{uuid.uuid4().hex}", headers=_bearer(created["beta"]))
    assert passed.status_code == 404 and passed.headers["x-api-source"] == "go"
    for headers in (_bearer("0" * 32), _bearer("short"), {"Authorization": "x"}, {}):  # wrong, malformed, junk, absent
        resp = ingress.get("/api/v1/searchbots/probe", headers=headers)
        assert resp.status_code == 401 and resp.json() == UNAUTHORIZED


def _log_records(logfile: str) -> list[dict[str, Any]]:
    path = LOG_DIR / logfile
    if not path.is_file():
        return []
    out = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def test_api_token_flow_token_never_appears_in_the_go_log(ingress: httpx.Client, accounts: tuple[Account, Account]) -> None:
    alice, _ = accounts
    created = _create(ingress, alice)
    token, beta = created["token"], created["beta"]
    ingress.get(_probe(), headers=_bearer(token))
    ingress.get(f"/api/v1/searchbots/probe-{uuid.uuid4().hex}", headers=_bearer(beta))
    assert ingress.delete(f"{TOKENS}/{token}", headers=_bearer(alice.token)).status_code == 200
    ingress.delete(f"{TOKENS}/{token}", headers=_bearer(alice.token))  # second delete is 404 and logs the same template

    def delete_logged() -> list[dict[str, Any]] | None:
        recs = [r for r in _log_records("ragflow_go.log") if r.get("method") == "DELETE" and str(r.get("path", "")).startswith(TOKENS)]
        return recs if len(recs) >= 2 else None

    records = wait_until(delete_logged, timeout=30, interval=0.5)
    assert {r["path"] for r in records} == {f"{TOKENS}/:token"}
    for logfile in ("ragflow_go.log", "ragflow_server.log"):
        text = (LOG_DIR / logfile).read_text(encoding="utf-8", errors="replace") if (LOG_DIR / logfile).is_file() else ""
        for secret in (token, beta, alice.token):
            assert secret not in text, f"{logfile} contains a credential"
