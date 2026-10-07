"""Test-only app builder and routes. Nothing here may be imported from ``api/``."""
from __future__ import annotations

import dataclasses
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel
from quart import Blueprint, Quart
from quart.testing import QuartClient
from quart_schema import validate_request
from werkzeug.datastructures import Headers

from api.apps import create_app
from api.db.services.auth_service import Principal
from api.utils.api_utils import json_result
from api.utils.validation import SafeIdentifier
from common.security import tokens
from common.settings import (
    CorsSettings,
    EsSettings,
    LoggingSettings,
    MinioSettings,
    MySQLSettings,
    RedisSettings,
    SecuritySettings,
    ServerSettings,
    Settings,
)

STUB_SECRET = "fake-test-secret-key-0123456789abcdef-ZZ"
STUB_INNER = "stub-inner-value-0123456789abcdef-0123"  # AUTH-08 compliant: 32 or more characters
STUB_USER_ID = "stubuser" + "0" * 24
STUB_PRINCIPAL = Principal(user_id=STUB_USER_ID, tenant_id=STUB_USER_ID, role="owner", auth_type="jwt", is_superuser=False)


def stub_token() -> str:
    """A validly signed access token (fresh timestamp) that only the stub resolver accepts."""
    return tokens.dump(STUB_INNER, STUB_SECRET)


class StubPrincipalResolver:
    """Accepts exactly one credential and never touches a database (unit tier and offline export)."""

    def __init__(self, token: str | None = None, principal: Principal = STUB_PRINCIPAL) -> None:
        self.token = token or stub_token()
        self.principal = principal
        self.calls: list[tuple[str, tuple[str, ...]]] = []

    def __call__(self, credential: str, allowed_types: tuple[str, ...]) -> Principal | None:
        self.calls.append((credential, allowed_types))
        return self.principal if credential == self.token else None


def _authed_client_class(token: str) -> type[QuartClient]:
    class AuthedClient(QuartClient):
        """Sends the stub token unless the caller supplies its own Authorization header."""

        async def open(self, path: str, *, headers: Any = None, **kwargs: Any) -> Any:
            merged = Headers(headers or {})
            if "Authorization" not in merged:
                merged["Authorization"] = f"Bearer {token}"
            return await super().open(path, headers=merged, **kwargs)

    return AuthedClient


class NameBody(BaseModel):
    name: SafeIdentifier


def memory_settings(allowed_origins: tuple[str, ...] = (), **sections: Any) -> Settings:
    """In-memory settings pointing at closed local ports (no live dependency is contacted)."""
    base = Settings(
        ragflow=ServerSettings("127.0.0.1", 9380),
        mysql=MySQLSettings("rag_flow", "u", "p", "127.0.0.1", 1, 2, 300),
        redis=RedisSettings("127.0.0.1", 1, "p", 0),
        minio=MinioSettings("u", "p", "127.0.0.1", 1),
        es=EsSettings("http://127.0.0.1:1", "u", "p"),
        cors=CorsSettings(allowed_origins=allowed_origins),
        logging=LoggingSettings("", "INFO"),
        security=SecuritySettings(secret_key=STUB_SECRET),
    )
    return dataclasses.replace(base, **sections)


def build_blueprint(service: Callable[[str], None] | None = None) -> Blueprint:
    """A blueprint with a raising route and a validated-body route; ``service`` is a spy hook."""
    bp = Blueprint("test_only", __name__)

    @bp.get("/test/boom")
    async def boom() -> Any:
        raise RuntimeError("secret detail")

    @bp.post("/test/named")
    @validate_request(NameBody)
    async def named(data: NameBody) -> Any:
        if service is not None:
            service(data.name)
        return json_result({"name": data.name})

    return bp


def make_test_app(
    service: Callable[[str], None] | None = None,
    allowed_origins: tuple[str, ...] = (),
    authenticated: bool = True,
    resolver: Callable[[str, tuple[str, ...]], Principal | None] | None = None,
    **sections: Any,
) -> Quart:
    """App built by the real factory with a stub principal resolver (no database).

    ``authenticated=True`` makes ``app.test_client()`` send the stub token by default;
    ``authenticated=False`` sends nothing so a test can supply its own credentials.
    """
    stub = resolver or StubPrincipalResolver()
    app = create_app(memory_settings(allowed_origins, **sections), extra_blueprints=(build_blueprint(service),), principal_resolver=stub)
    app.extensions["stub_resolver"] = stub
    return make_app_clients(app, authenticated)


def make_app_clients(app: Quart, authenticated: bool = True) -> Quart:
    token = getattr(app.extensions.get("stub_resolver"), "token", None) or stub_token()
    app.test_client_class = _authed_client_class(token) if authenticated else QuartClient
    return app


def make_client(app: Quart, authenticated: bool = True) -> QuartClient:
    """A test client that sends the stub token by default (or nothing when ``authenticated`` is False)."""
    make_app_clients(app, authenticated)
    return app.test_client()
