"""Team membership end to end through Nginx (TEN-04, TEN-05, TEN-11, success criterion 4).

Go owns every route used here. The whole cycle is driven with real accounts: invite, accept, promote,
refusals, demote, remove, re-invite, decline, accept again, leave.
"""
from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import httpx
import pytest

from test.helpers.accounts import Account, AccountRegistry
from test.testcases.conftest import BASE_URL

pytestmark = pytest.mark.e2e

NOT_FOUND = {"code": 404, "message": "not found", "data": None}


@pytest.fixture
def team() -> Iterator[tuple[Account, Account, Account]]:
    registry = AccountRegistry(BASE_URL)
    try:
        yield registry.register(prefix="owner"), registry.register(prefix="bee"), registry.register(prefix="cee")
    finally:
        registry.cleanup()


def _h(account: Account) -> dict[str, str]:
    return {"Authorization": f"Bearer {account.token}"}


def _users(owner: Account) -> str:
    return f"/api/v1/tenants/{owner.tenant_id}/users"


def _roles(ingress: httpx.Client, owner: Account, viewer: Account) -> dict[str, str]:
    resp = ingress.get(_users(owner), headers=_h(viewer))
    assert resp.status_code == 200, resp.text
    return {m["id"]: m["role"] for m in resp.json()["data"]}


def _invite(ingress: httpx.Client, owner: Account, target: Account) -> httpx.Response:
    return ingress.post(_users(owner), headers=_h(owner), json={"email": target.email})


def _respond(ingress: httpx.Client, owner: Account, target: Account, action: str) -> httpx.Response:
    return ingress.patch(f"/api/v1/tenants/{owner.tenant_id}", headers=_h(target), json={"action": action})


def _remove(ingress: httpx.Client, owner: Account, caller: Account, user_id: str) -> httpx.Response:
    return ingress.request("DELETE", _users(owner), headers=_h(caller), json={"user_id": user_id})


def _set_role(ingress: httpx.Client, owner: Account, caller: Account, user_id: str, role: Any) -> httpx.Response:
    return ingress.patch(f"{_users(owner)}/{user_id}", headers=_h(caller), json={"role": role})


def test_tenant_membership_full_cycle(ingress: httpx.Client, team: tuple[Account, Account, Account]) -> None:
    owner, bee, cee = team

    assert _invite(ingress, owner, bee).status_code == 200
    assert _roles(ingress, owner, owner)[bee.user_id] == "invite"
    assert ingress.get(_users(owner), headers=_h(bee)).status_code == 404, "an invitee is not a member yet"
    assert _respond(ingress, owner, bee, "accept").status_code == 200
    assert _roles(ingress, owner, bee)[bee.user_id] == "normal"

    promoted = _set_role(ingress, owner, owner, bee.user_id, "admin")
    assert promoted.status_code == 200 and promoted.json()["code"] == 0
    assert _roles(ingress, owner, owner)[bee.user_id] == "admin"
    assert ingress.post(_users(owner), headers=_h(bee), json={"email": cee.email}).status_code == 403, "an admin cannot invite (owner only)"
    assert _set_role(ingress, owner, bee, bee.user_id, "owner").status_code == 403

    assert _set_role(ingress, owner, owner, bee.user_id, "normal").status_code == 200
    assert _remove(ingress, owner, owner, bee.user_id).status_code == 200
    assert ingress.get(_users(owner), headers=_h(bee)).status_code == 404, "a removed member is a non-member on the very next request"
    assert ingress.get("/v1/user/tenant_info", headers=_h(bee)).json()["data"]["tenant_id"] == bee.tenant_id

    assert _invite(ingress, owner, bee).status_code == 200
    assert _respond(ingress, owner, bee, "decline").status_code == 200
    assert bee.user_id not in _roles(ingress, owner, owner)
    assert _invite(ingress, owner, bee).status_code == 200
    assert _respond(ingress, owner, bee, "accept").status_code == 200
    assert _roles(ingress, owner, bee)[bee.user_id] == "normal"

    assert _remove(ingress, owner, bee, bee.user_id).status_code == 200, "a member leaves"
    assert ingress.get(_users(owner), headers=_h(bee)).status_code == 404
    assert _roles(ingress, owner, owner) == {owner.user_id: "owner"}


def test_tenant_membership_owner_row_is_protected_and_refusals_change_nothing(
    ingress: httpx.Client, team: tuple[Account, Account, Account]
) -> None:
    owner, bee, cee = team
    assert _invite(ingress, owner, bee).status_code == 200
    assert _respond(ingress, owner, bee, "accept").status_code == 200
    assert _invite(ingress, owner, cee).status_code == 200

    for role in ("owner", "invite", "superuser", ""):
        assert _set_role(ingress, owner, owner, bee.user_id, role).status_code == 400, role
    assert _set_role(ingress, owner, owner, owner.user_id, "normal").status_code == 400, "no self-demotion"
    assert _set_role(ingress, owner, owner, cee.user_id, "admin").status_code == 400, "a pending invitation has no role to change"
    assert _remove(ingress, owner, owner, owner.user_id).status_code == 400, "the owner cannot leave"
    assert _remove(ingress, owner, bee, owner.user_id).status_code == 403, "naming the owner is forbidden"
    assert _remove(ingress, owner, bee, cee.user_id).status_code == 403
    assert _roles(ingress, owner, owner) == {owner.user_id: "owner", bee.user_id: "normal", cee.user_id: "invite"}

    # the invitee withdrawn by the owner can no longer accept
    assert _remove(ingress, owner, owner, cee.user_id).status_code == 200
    assert _respond(ingress, owner, cee, "accept").status_code == 404
    assert cee.user_id not in _roles(ingress, owner, owner)


def test_tenant_membership_non_members_get_the_shared_404(ingress: httpx.Client, team: tuple[Account, Account, Account]) -> None:
    owner, bee, cee = team
    assert _invite(ingress, owner, bee).status_code == 200
    random_tenant = "f" * 32
    for caller in (bee, cee):  # a pending invitee and a stranger
        for resp in (
            ingress.patch(f"/api/v1/tenants/{owner.tenant_id}/users/{owner.user_id}", headers=_h(caller), json={"role": "admin"}),
            ingress.request("DELETE", _users(owner), headers=_h(caller), json={"user_id": owner.user_id}),
            ingress.patch(f"/api/v1/tenants/{random_tenant}/users/{owner.user_id}", headers=_h(caller), json={"role": "admin"}),
            ingress.request("DELETE", f"/api/v1/tenants/{random_tenant}/users", headers=_h(caller), json={"user_id": owner.user_id}),
        ):
            assert resp.status_code == 404 and resp.json() == NOT_FOUND
    assert _roles(ingress, owner, owner) == {owner.user_id: "owner", bee.user_id: "invite"}


def test_tenant_membership_requires_a_session(ingress: httpx.Client, team: tuple[Account, Account, Account]) -> None:
    owner, bee, _ = team
    assert ingress.patch(f"{_users(owner)}/{bee.user_id}", json={"role": "admin"}).status_code == 401
    assert ingress.request("DELETE", _users(owner), json={"user_id": bee.user_id}).status_code == 401
