"""Isolated account fixtures for live tests (plan 02-07).

``register_account`` calls the real ``POST /api/v1/users`` and ``POST /api/v1/auth/login``
endpoints; nothing is faked. Those endpoints are built in plan 02-09, so until then the
registration helpers return a clear error from the server (404 or 405) and only the pure
helpers (``unique_email``, ``unique_name``) are usable.

Cleanup is by recorded ids only: ``AccountRegistry.cleanup`` deletes the user, tenant,
user_tenant and tenant_llm rows of accounts this registry created and nothing else. Since plan 03-14
it also removes what an account's datasets left behind: knowledgebase, document, file and file2document
rows, the tenant's Elasticsearch index (by its exact name) and its MinIO objects (by exact key prefix).
"""
from __future__ import annotations

import secrets
from dataclasses import dataclass
from typing import Any

import httpx

from test.helpers.db import root_connection

TEST_PASSWORD = "test-only-pass-0001"
_DB_NAME = "rag_flow"
_STORAGE_BUCKET = "ragflow"


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
                # Model structure rows are reached through the tenant's provider ids (plan 03-09).
                cur.execute("SELECT `id` FROM `tenant_model_provider` WHERE `tenant_id` = %s", (acc.tenant_id,))
                for (provider_id,) in cur.fetchall():
                    cur.execute("DELETE FROM `tenant_model` WHERE `provider_id` = %s", (provider_id,))
                    cur.execute("DELETE FROM `tenant_model_instance` WHERE `provider_id` = %s", (provider_id,))
                cur.execute("DELETE FROM `tenant_model_provider` WHERE `tenant_id` = %s", (acc.tenant_id,))
                cur.execute("DELETE FROM `tenant_llm` WHERE `tenant_id` = %s", (acc.tenant_id,))
                _delete_dataset_rows(cur, acc.tenant_id)
                cur.execute("DELETE FROM `user_tenant` WHERE `user_id` = %s", (acc.user_id,))
                cur.execute("DELETE FROM `tenant` WHERE `id` = %s", (acc.tenant_id,))
                cur.execute("DELETE FROM `user` WHERE `id` = %s", (acc.user_id,))
    finally:
        conn.close()
    for acc in accounts:
        delete_tenant_artifacts(acc.tenant_id)


def _delete_dataset_rows(cur: Any, tenant_id: str) -> None:
    """Delete the dataset rows of one recorded tenant. Every statement takes the id as a parameter."""
    cur.execute(
        "DELETE FROM `file2document` WHERE `document_id` IN "
        "(SELECT `id` FROM `document` WHERE `kb_id` IN (SELECT `id` FROM `knowledgebase` WHERE `tenant_id` = %s))",
        (tenant_id,),
    )
    cur.execute("DELETE FROM `file2document` WHERE `file_id` IN (SELECT `id` FROM `file` WHERE `tenant_id` = %s)", (tenant_id,))
    cur.execute("DELETE FROM `document` WHERE `kb_id` IN (SELECT `id` FROM `knowledgebase` WHERE `tenant_id` = %s)", (tenant_id,))
    cur.execute("DELETE FROM `file` WHERE `tenant_id` = %s", (tenant_id,))
    cur.execute("DELETE FROM `knowledgebase` WHERE `tenant_id` = %s", (tenant_id,))


def delete_tenant_artifacts(tenant_id: str) -> None:
    """Remove one recorded tenant's Elasticsearch index (exact name) and MinIO objects (exact ``{tenant_id}/`` prefix).

    Absent index or bucket is fine. The tenant id must be 32 lowercase hex characters, so no wildcard can ever be passed on.
    """
    if len(tenant_id) != 32 or any(ch not in "0123456789abcdef" for ch in tenant_id):
        raise ValueError("tenant id must be 32 lowercase hex characters")
    _delete_index(f"ragflow_{tenant_id}")
    _delete_objects(f"{tenant_id}/")


def _delete_index(index: str) -> None:
    from elasticsearch import Elasticsearch

    from common.settings import load_settings

    es = load_settings().es
    client = Elasticsearch(es.hosts, basic_auth=(es.username, es.password), request_timeout=30, max_retries=0)
    try:
        client.indices.delete(index=index, ignore_unavailable=True)
    finally:
        client.close()


def _delete_objects(prefix: str) -> None:
    from minio import Minio
    from minio.error import S3Error

    from test.conftest import stack_env

    env = stack_env()
    password = env.get("MINIO_PASSWORD")
    if not password:
        return
    client = Minio(f"127.0.0.1:{env.get('MINIO_PORT', '9000')}", access_key=env.get("MINIO_USER", "rag_flow"), secret_key=password, secure=False)
    try:
        if not client.bucket_exists(_STORAGE_BUCKET):
            return
        for item in client.list_objects(_STORAGE_BUCKET, prefix=prefix, recursive=True):
            client.remove_object(_STORAGE_BUCKET, item.object_name)
    except S3Error as exc:
        if exc.code != "NoSuchBucket":
            raise
