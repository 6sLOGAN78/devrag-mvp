"""Credential resolution for the Python gate (D-09, D-11, D-30, R-114).

Same contract as the Go service (internal/service/auth.go):

* ``jwt``: itsdangerous wrapper (30-day max age, shared with Go through ``common.security``), AUTH-08
  inner rules, then ``user.access_token`` equality and ``status == '1'`` on every request.
* ``api``: ``api_token.token`` (``ragflow-`` prefix), resolved to the owner of its OWN tenant only.
* ``beta``: ``api_token.beta`` (32 characters); beta routes also accept access and API tokens.

Every credential failure returns ``None``. A dependency failure raises ``AuthInfrastructureError`` so the
gate can answer 503 instead of 401 and never signs users out because MySQL is down (R-114). The cheap checks
(length, signature, max age, AUTH-08, prefix shape) run in :func:`precheck` before any database call (T-02-59).
Comparisons against stored secrets are re-done in constant time because MySQL equality is collation-based.
"""
from __future__ import annotations

import contextlib
import hmac
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from api.db.database import DB
from api.db.models import APIToken, User, UserTenant
from common.security import tokens

logger = logging.getLogger(__name__)

AUTH_JWT = "jwt"
AUTH_API = "api"
AUTH_BETA = "beta"

API_KEY_PREFIX = "ragflow-"
MAX_API_TOKEN_LENGTH = 255
_BETA_SHAPE = re.compile(r"\A[A-Za-z0-9]{32}\Z")
_ACTIVE = "1"
_OWNER = "owner"


class AuthInfrastructureError(Exception):
    """A dependency of credential resolution failed; the gate answers 503, never 401 (R-114)."""


@dataclass(frozen=True)
class Principal:
    user_id: str
    tenant_id: str
    role: str
    auth_type: str
    is_superuser: bool


@dataclass(frozen=True)
class UserRecord:
    id: str
    access_token: str | None
    status: str | None
    is_superuser: bool


@dataclass(frozen=True)
class MembershipRecord:
    tenant_id: str
    role: str


@dataclass(frozen=True)
class ApiTokenRecord:
    tenant_id: str
    token: str
    beta: str | None


class AuthStore(Protocol):
    """Persistence surface of credential resolution; ``PeeweeAuthStore`` is the real one."""

    def find_user_by_access_token(self, token: str) -> UserRecord | None: ...
    def find_user_by_id(self, user_id: str) -> UserRecord | None: ...
    def find_own_membership(self, user_id: str) -> MembershipRecord | None: ...
    def find_api_token(self, token: str) -> ApiTokenRecord | None: ...
    def find_beta_token(self, beta: str) -> ApiTokenRecord | None: ...


PrincipalResolver = Callable[[str, tuple[str, ...]], Principal | None]


def _same(stored: str | None, presented: str) -> bool:
    return stored is not None and hmac.compare_digest(stored.encode(), presented.encode())


def _verified_inner(credential: str, secret: str, now: int | None) -> str | None:
    inner = tokens.verify(credential, secret, now=now)
    return inner if inner is not None and tokens.valid_inner(inner) else None


def _looks_like_api_token(credential: str) -> bool:
    return credential.startswith(API_KEY_PREFIX) and len(credential) <= MAX_API_TOKEN_LENGTH


def precheck(credential: str, allowed_types: tuple[str, ...], secret: str, now: int | None = None) -> bool:
    """True when the credential could be valid for one of the allowed types. Never touches a database."""
    if not credential or len(credential) > tokens.MAX_TOKEN_LENGTH:
        return False
    if AUTH_BETA in allowed_types and _BETA_SHAPE.match(credential):
        return True
    if AUTH_JWT in allowed_types and _verified_inner(credential, secret, now) is not None:
        return True
    return AUTH_API in allowed_types and _looks_like_api_token(credential)


def _principal_for_user(store: AuthStore, user: UserRecord, auth_type: str) -> Principal:
    membership = store.find_own_membership(user.id)
    tenant_id, role = "", ""
    if membership is not None and membership.role == _OWNER:
        # An own workspace is the user's owner row; a pending invitation is no membership (D-14, D-15).
        tenant_id, role = membership.tenant_id, membership.role
    return Principal(user.id, tenant_id, role, auth_type, user.is_superuser)


def _principal_for_token(store: AuthStore, record: ApiTokenRecord, auth_type: str) -> Principal | None:
    """An API or beta token acts as the user whose id equals the token's tenant id, nothing wider."""
    owner = store.find_user_by_id(record.tenant_id)
    if owner is None or owner.status != _ACTIVE:
        return None
    principal = _principal_for_user(store, owner, auth_type)
    return Principal(principal.user_id, record.tenant_id, principal.role, auth_type, principal.is_superuser)


def resolve_credential(
    credential: str,
    allowed_types: tuple[str, ...],
    *,
    secret: str,
    store: AuthStore,
    now: int | None = None,
) -> Principal | None:
    """Resolve in the documented order: beta, jwt, api. ``None`` for every credential failure."""
    if not precheck(credential, allowed_types, secret, now):
        return None
    if AUTH_BETA in allowed_types and _BETA_SHAPE.match(credential):
        record = store.find_beta_token(credential)
        if record is not None and _same(record.beta, credential):
            return _principal_for_token(store, record, AUTH_BETA)
    inner = _verified_inner(credential, secret, now) if AUTH_JWT in allowed_types else None
    if inner is not None:
        user = store.find_user_by_access_token(inner)
        if user is None or not _same(user.access_token, inner) or user.status != _ACTIVE:
            return None
        return _principal_for_user(store, user, AUTH_JWT)
    if AUTH_API in allowed_types and _looks_like_api_token(credential):
        record = store.find_api_token(credential)
        if record is not None and _same(record.token, credential):
            return _principal_for_token(store, record, AUTH_API)
    return None


class PeeweeAuthStore:
    """The real store. Methods must run inside ``DB.connection_context()`` (see ``make_resolver``)."""

    def find_user_by_access_token(self, token: str) -> UserRecord | None:
        return _user(User.select().where(User.access_token == token).first())

    def find_user_by_id(self, user_id: str) -> UserRecord | None:
        return _user(User.select().where(User.id == user_id).first())

    def find_own_membership(self, user_id: str) -> MembershipRecord | None:
        row = UserTenant.select().where((UserTenant.user_id == user_id) & (UserTenant.role == _OWNER) & (UserTenant.status == _ACTIVE)).first()
        return MembershipRecord(tenant_id=row.tenant_id, role=row.role) if row is not None else None

    def find_api_token(self, token: str) -> ApiTokenRecord | None:
        return _api_token(APIToken.select().where(APIToken.token == token).first())

    def find_beta_token(self, beta: str) -> ApiTokenRecord | None:
        return _api_token(APIToken.select().where(APIToken.beta == beta).first())


def _user(row: object | None) -> UserRecord | None:
    if row is None:
        return None
    return UserRecord(id=row.id, access_token=row.access_token, status=row.status, is_superuser=bool(row.is_superuser))  # type: ignore[attr-defined]


def _api_token(row: object | None) -> ApiTokenRecord | None:
    if row is None:
        return None
    return ApiTokenRecord(tenant_id=row.tenant_id, token=row.token, beta=row.beta)  # type: ignore[attr-defined]


def make_resolver(secret: str, store: AuthStore | None = None) -> PrincipalResolver:
    """Build the synchronous resolver the gate runs through ``asyncio.to_thread``.

    With no ``store`` the Peewee store runs inside one per-call ``DB.connection_context()``. Any failure of
    the store (MySQL error, closed connection, timeout, an uninitialised pool) becomes ``AuthInfrastructureError``.
    """
    real = store is None
    backing: AuthStore = store if store is not None else PeeweeAuthStore()

    def resolve(credential: str, allowed_types: tuple[str, ...]) -> Principal | None:
        if not precheck(credential, allowed_types, secret):
            return None  # no connection is opened for a credential that cannot be valid
        try:
            if real:
                scope = DB.connection_context()
            else:
                scope = contextlib.nullcontext()
            with scope:
                return resolve_credential(credential, allowed_types, secret=secret, store=backing)
        except AuthInfrastructureError:
            raise
        except Exception as exc:
            # The exception text can carry hosts or SQL; only its class name travels on.
            raise AuthInfrastructureError(type(exc).__name__) from exc

    return resolve
