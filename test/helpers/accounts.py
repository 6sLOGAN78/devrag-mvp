"""Isolated account fixtures for live tests (plan 02-07).

``register_account`` calls the real ``POST /api/v1/users`` and ``POST /api/v1/auth/login``
endpoints; nothing is faked. Those endpoints are built in plan 02-09, so until then the
registration helpers return a clear error from the server (404 or 405) and only the pure
helpers (``unique_email``, ``unique_name``) are usable.

Cleanup is by recorded ids only: ``AccountRegistry.cleanup`` deletes the user, tenant,
user_tenant and tenant_llm rows of accounts this registry created and nothing else.
"""
from __future__ import annotations

import secrets
from dataclasses import dataclass
from typing import Any

import httpx

from test.helpers.db import root_connection

TEST_PASSWORD = "test-only-pass-0001"
_DB_NAME = "rag_flow"


@dataclass(frozen=True)
class Account:
    email: str
    password: str
    nickname: str
    user_id: str
    tenant_id: str
    token: str


class AccountFixtureError(RuntimeError):
    """A fixture call failed; the message names the endpoint and status, never a credential."""


def unique_email(prefix: str = "user") -> str:
    """Lowercase ``prefix-<random hex>@example.test`` address, unique per call."""
    return f"{prefix.lower()}-{secrets.token_hex(8)}@example.test"


def unique_name(prefix: str = "name") -> str:
    return f"{prefix}-{secrets.token_hex(6)}"


def _envelope(resp: httpx.Response, what: str) -> dict[str, Any]:
    if resp.status_code != 200:
        raise AccountFixtureError(f"{what} returned HTTP {resp.status_code}")
    body = resp.json()
    if body.get("code") != 0:
        raise AccountFixtureError(f"{what} returned envelope code {body.get('code')}: {body.get('message')}")
    data = body.get("data")
    return data if isinstance(data, dict) else {}


def register_account(base_url: str, *, password: str = TEST_PASSWORD, prefix: str = "user", client: httpx.Client | None = None) -> Account:
    """Register a fresh user (and thereby tenant), log in, and return the account."""
    email = unique_email(prefix)
    nickname = unique_name("nick")
    base = base_url.rstrip("/")
    own = client is None
    http = client or httpx.Client(timeout=10.0)
    try:
        reg = _envelope(http.post(f"{base}/api/v1/users", json={"email": email, "password": password, "nickname": nickname}), "register")
        login = _envelope(http.post(f"{base}/api/v1/auth/login", json={"email": email, "password": password}), "login")
    finally:
        if own:
            http.close()
    user = login.get("user") if isinstance(login.get("user"), dict) else {}
    user_id = str(reg.get("id") or user.get("id") or login.get("id") or "")
    tenant_id = str(reg.get("tenant_id") or login.get("tenant_id") or user.get("tenant_id") or user_id)
    token = str(login.get("token") or login.get("access_token") or "")
    if not user_id or not token:
        raise AccountFixtureError("register/login response lacked a user id or token")
    return Account(email=email, password=password, nickname=nickname, user_id=user_id, tenant_id=tenant_id, token=token)


class AccountRegistry:
    """Creates accounts and deletes exactly those rows afterwards."""

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url
        self.created: list[Account] = []

    def register(self, **kwargs: Any) -> Account:
        acc = register_account(self.base_url, **kwargs)
        self.created.append(acc)
        return acc

    def two_accounts(self) -> tuple[Account, Account]:
        return self.register(prefix="alice"), self.register(prefix="bob")

    def cleanup(self) -> None:
        delete_accounts(self.created)
        self.created.clear()


def two_accounts(base_url: str) -> tuple[Account, Account]:
    """Two independent users, each with their own tenant. Callers own cleanup (see AccountRegistry)."""
    return register_account(base_url, prefix="alice"), register_account(base_url, prefix="bob")


def delete_accounts(accounts: list[Account]) -> None:
    """Delete the recorded accounts' rows by id (T-02-26). Never deletes by pattern."""
    if not accounts:
        return
    conn = root_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(f"USE `{_DB_NAME}`")
            for acc in accounts:
                cur.execute("DELETE FROM `api_token` WHERE `tenant_id` = %s", (acc.tenant_id,))
                cur.execute("DELETE FROM `tenant_llm` WHERE `tenant_id` = %s", (acc.tenant_id,))
                cur.execute("DELETE FROM `user_tenant` WHERE `user_id` = %s", (acc.user_id,))
                cur.execute("DELETE FROM `tenant` WHERE `id` = %s", (acc.tenant_id,))
                cur.execute("DELETE FROM `user` WHERE `id` = %s", (acc.user_id,))
    finally:
        conn.close()
