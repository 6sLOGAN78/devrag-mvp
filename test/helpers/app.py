"""Test-only app builder and routes. Nothing here may be imported from ``api/``."""
from __future__ import annotations

import dataclasses
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel
from quart import Blueprint, Quart
from quart_schema import validate_request

from api.apps import create_app
from api.utils.api_utils import json_result
from api.utils.validation import SafeIdentifier
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
        security=SecuritySettings(secret_key="fake-test-secret-key-0123456789abcdef-ZZ"),
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


def make_test_app(service: Callable[[str], None] | None = None, allowed_origins: tuple[str, ...] = (), **sections: Any) -> Quart:
    return create_app(memory_settings(allowed_origins, **sections), extra_blueprints=(build_blueprint(service),))
