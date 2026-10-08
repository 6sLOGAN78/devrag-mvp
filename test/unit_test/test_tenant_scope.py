"""Pure rules of the acting-workspace service (plan 03-04; D-08, D-09, D-20, D-26, D-27).

Membership lookups run against the real MySQL in test/integration/test_tenant_scope.py.
"""

from __future__ import annotations

import pytest

from api.db.services.tenant_scope import (
    can_manage_dataset,
    can_remove_document,
    dataset_visible,
    is_elevated,
    subject_for,
)

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("auth_type", "role", "expected"),
    [("api", "owner", "api_token"), ("beta", "owner", "beta_token"), ("jwt", "owner", "owner"), ("jwt", "admin", "admin"), ("jwt", "normal", "normal")],
)
def test_subject_for_never_lends_the_owner_role_to_a_token(auth_type: str, role: str, expected: str) -> None:
    assert subject_for(auth_type, role) == expected


def test_is_elevated_is_owner_and_admin_only() -> None:
    assert is_elevated("owner") and is_elevated("admin")
    for role in ("normal", "invite", "", "superuser"):
        assert not is_elevated(role), role


def test_dataset_visibility_follows_the_permission_and_creator() -> None:
    assert dataset_visible("u1", "me", "u1", True) is True
    assert dataset_visible("u1", "team", "u2", True) is True
    assert dataset_visible("u1", "me", "u2", True) is False, "no owner or admin override of a private dataset (D-27)"
    assert dataset_visible("u1", "team", "u2", False) is False
    assert dataset_visible("u1", "me", "u1", False) is False, "a former member sees nothing"


def test_unknown_permission_value_is_not_visible_to_others() -> None:
    assert dataset_visible("u1", "", "u2", True) is False
    assert dataset_visible("u1", "other", "u2", True) is False


@pytest.mark.parametrize(
    ("creator", "caller", "role", "expected"),
    [("u1", "u1", "normal", True), ("u1", "u2", "owner", True), ("u1", "u2", "admin", True), ("u1", "u2", "normal", False), ("u1", "u2", "invite", False)],
)
def test_can_manage_dataset(creator: str, caller: str, role: str, expected: bool) -> None:
    assert can_manage_dataset(creator, caller, role) is expected


@pytest.mark.parametrize(
    ("doc_creator", "kb_creator", "caller", "role", "expected"),
    [
        ("u1", "u9", "u1", "normal", True),
        ("u1", "u9", "u2", "normal", False),
        ("u1", "u9", "u2", "admin", True),
        ("u1", "u9", "u2", "owner", True),
        ("u1", "u2", "u2", "normal", True),
        ("u1", "u9", "u2", "invite", False),
    ],
)
def test_can_remove_document(doc_creator: str, kb_creator: str, caller: str, role: str, expected: bool) -> None:
    assert can_remove_document(doc_creator, kb_creator, caller, role) is expected
