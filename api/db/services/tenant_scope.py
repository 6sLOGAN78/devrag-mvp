"""Acting-workspace resolution, dataset visibility and object rules (plan 03-04; D-08, D-09, D-20, D-26, D-27).

A signed-in user acts in their own workspace by default, or in another workspace they have joined when the
request names it. Handlers call :func:`resolve_scope` (workspace from a parameter) or :func:`scope_for_tenant`
(workspace derived from the addressed resource) and answer the one 404 envelope when the result is ``None``:
an absent id, a foreign workspace and a pending invitation are indistinguishable to the caller (D-20).

API and beta tokens are pinned to the workspace that issued them and are authorised as ``api_token`` or
``beta_token``, never with the role of the owner they happen to resolve to (D-26, Pitfall 6). Superuser status
grants nothing here.

The object rules below are layered on top of the coarse permission matrix (``permissions_gen.allowed``), which
cannot express "own": a ``me`` dataset belongs to its creator alone, with no owner or admin override (D-27).
"""
from __future__ import annotations

from dataclasses import dataclass

from api.db.database import DB
from api.db.models import UserTenant
from api.db.services.auth_service import AUTH_API, AUTH_BETA, AUTH_JWT, Principal

_ACTIVE = "1"
_OWNER = "owner"
_ADMIN = "admin"
_NORMAL = "normal"
_MEMBER_ROLES = (_OWNER, _ADMIN, _NORMAL)
_ELEVATED_ROLES = frozenset({_OWNER, _ADMIN})

PERMISSION_ME = "me"
PERMISSION_TEAM = "team"


@dataclass(frozen=True)
class ActingScope:
    """The workspace a request acts in, the caller's role there and the subject used for the permission matrix."""

    tenant_id: str
    role: str
    subject: str


def joined_tenants(user_id: str) -> dict[str, str]:
    """Workspaces the user is an active member of, as ``{tenant_id: role}``.

    The user's own workspace appears with role ``owner``. A pending invitation (role ``invite``) and an inactive
    row (status other than ``1``) are never membership (D-14, D-15, D-26).
    """
    if not user_id:
        return {}
    with DB.connection_context():
        rows = list(
            UserTenant.select(UserTenant.tenant_id, UserTenant.role).where(
                (UserTenant.user_id == user_id) & (UserTenant.status == _ACTIVE) & (UserTenant.role.in_(_MEMBER_ROLES))
            )
        )
    return {row.tenant_id: row.role for row in rows}


def subject_for(auth_type: str, role: str) -> str:
    """The permission-matrix subject: the credential class for tokens, the workspace role for a session."""
    if auth_type == AUTH_API:
        return "api_token"
    if auth_type == AUTH_BETA:
        return "beta_token"
    return role


def is_elevated(role: str) -> bool:
    """True for owner and admin."""
    return role in _ELEVATED_ROLES


def resolve_scope(principal: Principal, requested_tenant_id: str | None) -> ActingScope | None:
    """The workspace to act in, or ``None`` when the caller may not act in the requested one.

    No request, or the caller's own workspace id, resolves to the principal's own workspace. Another workspace is
    honoured only for a session (``jwt``) principal who is an active member of it. API and beta principals are
    pinned to their token's workspace: any different id is refused.
    """
    if not principal.tenant_id:
        return None
    if not requested_tenant_id or requested_tenant_id == principal.tenant_id:
        return ActingScope(principal.tenant_id, principal.role, subject_for(principal.auth_type, principal.role))
    if principal.auth_type != AUTH_JWT:
        return None
    role = joined_tenants(principal.user_id).get(requested_tenant_id)
    if role is None:
        return None
    return ActingScope(requested_tenant_id, role, subject_for(principal.auth_type, role))


def scope_for_tenant(principal: Principal, tenant_id: str) -> ActingScope | None:
    """Same rule as :func:`resolve_scope` for id-addressed routes, where the workspace comes from the resource."""
    if not tenant_id:
        return None
    return resolve_scope(principal, tenant_id)


def dataset_visible(creator_id: str, permission: str, caller_id: str, caller_in_tenant: bool) -> bool:
    """Whether the caller may see a dataset of the workspace.

    A non-member sees nothing. A ``me`` dataset is visible to its creator only, with no owner or admin override
    (D-08, D-27); a ``team`` dataset is visible to every member. Any other permission value hides the dataset
    from everyone but its creator.
    """
    if not caller_in_tenant or not caller_id:
        return False
    if creator_id == caller_id:
        return True
    return permission == PERMISSION_TEAM


def can_manage_dataset(creator_id: str, caller_id: str, role: str) -> bool:
    """Edit, re-share or delete a dataset: its creator, or an owner or admin of its workspace (D-09)."""
    if not caller_id:
        return False
    return creator_id == caller_id or is_elevated(role)


def can_remove_document(document_creator_id: str, dataset_creator_id: str, caller_id: str, role: str) -> bool:
    """Remove a document: its uploader, or anyone who may manage its dataset (D-09)."""
    if not caller_id:
        return False
    return document_creator_id == caller_id or can_manage_dataset(dataset_creator_id, caller_id, role)
