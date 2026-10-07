"""Credential resolution for the Python gate (plan 02-14). Skeleton: types only, behaviour lands with the gate."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

AUTH_JWT = "jwt"
AUTH_API = "api"
AUTH_BETA = "beta"


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
class ApiTokenRecord:
    tenant_id: str
    token: str
    beta: str | None


class AuthStore(Protocol):
    def find_user_by_access_token(self, token: str) -> UserRecord | None: ...
    def find_user_by_id(self, user_id: str) -> UserRecord | None: ...
    def find_own_role(self, user_id: str) -> str | None: ...
    def find_api_token(self, token: str) -> ApiTokenRecord | None: ...
    def find_beta_token(self, beta: str) -> ApiTokenRecord | None: ...


PrincipalResolver = Callable[[str, tuple[str, ...]], Principal | None]


def precheck(credential: str, allowed_types: tuple[str, ...], secret: str) -> bool:
    raise NotImplementedError


def resolve_credential(credential: str, allowed_types: tuple[str, ...], *, secret: str, store: AuthStore, now: int | None = None) -> Principal | None:
    raise NotImplementedError


def make_resolver(secret: str, store: AuthStore | None = None) -> PrincipalResolver:
    raise NotImplementedError
