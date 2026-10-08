"""Acting-workspace resolution against the real MySQL (plan 03-04; D-20, D-26, T-03-04-02, T-03-04-05).

Accounts come from the real register endpoint; extra membership rows are inserted and removed by recorded id.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest

from api.db.services.auth_service import AUTH_API, AUTH_JWT, Principal
from api.db.services.tenant_scope import ActingScope, joined_tenants, resolve_scope, scope_for_tenant
from common.settings import load_settings
from test.helpers.accounts import Account, AccountRegistry
from test.helpers.db import root_connection

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module", autouse=True)
def _bound_database() -> Iterator[None]:
    from api.db.database import DB, init_database

    init_database(load_settings().mysql)
    yield
    DB.close()


@pytest.fixture(scope="module")
def accounts() -> Iterator[tuple[Account, Account, Account, Account]]:
    from test.testcases.conftest import BASE_URL

    registry = AccountRegistry(BASE_URL)
    try:
        yield (registry.register(prefix="scope-me"), registry.register(prefix="scope-a"), registry.register(prefix="scope-b"), registry.register(prefix="scope-c"))
    finally:
        registry.cleanup()


def _membership(user_id: str, tenant_id: str, role: str, status: str) -> str:
    row_id = uuid.uuid4().hex
    conn = root_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("USE `rag_flow`")
            cur.execute(
                "INSERT INTO `user_tenant` (`id`, `user_id`, `tenant_id`, `role`, `invited_by`, `status`) VALUES (%s, %s, %s, %s, %s, %s)",
                (row_id, user_id, tenant_id, role, tenant_id, status),
            )
    finally:
        conn.close()
    return row_id


def _drop(row_ids: list[str]) -> None:
    conn = root_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("USE `rag_flow`")
            for row_id in row_ids:
                cur.execute("DELETE FROM `user_tenant` WHERE `id` = %s", (row_id,))
    finally:
        conn.close()


@pytest.fixture
def memberships(accounts: tuple[Account, Account, Account, Account]) -> Iterator[None]:
    me, a, b, c = accounts
    ids = [
        _membership(me.user_id, a.tenant_id, "admin", "1"),
        _membership(me.user_id, b.tenant_id, "invite", "1"),
        _membership(me.user_id, c.tenant_id, "normal", "0"),
    ]
    try:
        yield
    finally:
        _drop(ids)


def _jwt(account: Account) -> Principal:
    return Principal(account.user_id, account.tenant_id, "owner", AUTH_JWT, False)


def test_joined_tenants_lists_own_and_active_member_workspaces_only(accounts: tuple[Account, Account, Account, Account], memberships: None) -> None:
    me, a, b, c = accounts
    got = joined_tenants(me.user_id)
    assert got[me.tenant_id] == "owner"
    assert got[a.tenant_id] == "admin"
    assert b.tenant_id not in got, "a pending invitation is not membership"
    assert c.tenant_id not in got, "an inactive row is not membership"


def test_resolve_scope_defaults_to_the_own_workspace(accounts: tuple[Account, Account, Account, Account]) -> None:
    me = accounts[0]
    assert resolve_scope(_jwt(me), None) == ActingScope(me.tenant_id, "owner", "owner")
    assert resolve_scope(_jwt(me), me.tenant_id) == ActingScope(me.tenant_id, "owner", "owner")


def test_resolve_scope_honours_a_joined_workspace_with_the_callers_role(accounts: tuple[Account, Account, Account, Account], memberships: None) -> None:
    me, a, _, _ = accounts
    assert resolve_scope(_jwt(me), a.tenant_id) == ActingScope(a.tenant_id, "admin", "admin")
    assert scope_for_tenant(_jwt(me), a.tenant_id) == ActingScope(a.tenant_id, "admin", "admin")


def test_resolve_scope_refuses_workspaces_the_user_is_not_in(accounts: tuple[Account, Account, Account, Account], memberships: None) -> None:
    me, _, b, c = accounts
    assert resolve_scope(_jwt(me), b.tenant_id) is None
    assert resolve_scope(_jwt(me), c.tenant_id) is None
    assert resolve_scope(_jwt(me), uuid.uuid4().hex) is None


def test_api_token_principal_is_pinned_to_its_own_tenant(accounts: tuple[Account, Account, Account, Account], memberships: None) -> None:
    me, a, _, _ = accounts
    token_principal = Principal(me.user_id, me.tenant_id, "owner", AUTH_API, False)
    assert resolve_scope(token_principal, None) == ActingScope(me.tenant_id, "owner", "api_token")
    assert resolve_scope(token_principal, a.tenant_id) is None
    assert scope_for_tenant(token_principal, a.tenant_id) is None


def test_principal_without_a_workspace_resolves_to_nothing(accounts: tuple[Account, Account, Account, Account]) -> None:
    me = accounts[0]
    assert resolve_scope(Principal(me.user_id, "", "", AUTH_JWT, False), None) is None
