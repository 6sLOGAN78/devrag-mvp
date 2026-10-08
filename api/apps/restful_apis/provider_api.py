"""Model provider credential routes (plan 03-12; LLM-23..27, SEC-02, D-07, D-16, D-17, D-19, D-20, D-26).

Six handlers, all thin: resolve the acting workspace (a foreign or malformed one is the single not-found body), check the permission
matrix, run the blocking provider-service call in a bounded executor, and map ``ServiceError`` to the envelope. Order is always scope
(404), permission (403), then existence (404), so a caller who may not write learns nothing about what exists.

The key-writing rows (PUT, DELETE, POST, instance detail) are ``auth: jwt`` in the registry, so an API token never reaches them; the
list and model routes accept a token, and their views show the address and ``last4`` only to the ``owner`` and ``admin`` subjects.
A request body is never logged and a key lives only in a ``SecretStr`` until the service has used it.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr
from quart import Blueprint, Response, current_app, request
from quart_schema import document_response, validate_request

from api.apps.handler_support import acting_scope, credentials_visible, forbid_unless
from api.apps.service_errors import not_found_response, service_error_response
from api.db.services import provider_service, tenant_model_service
from api.db.services.provider_service import ModelRequest, SaveRequest
from api.db.services.service_errors import Kind, ServiceError
from api.db.services.tenant_scope import ActingScope
from api.utils import reasons
from api.utils.api_utils import json_result
from api.utils.blocking import DB_EXECUTOR, PROVIDER_EXECUTOR, run_blocking
from api.utils.validation import SafeIdentifier
from common.model_ref import DEFAULT_INSTANCE
from common.settings import Settings
from rag.llm import ProviderSpec, UnknownProvider, resolve_provider

provider_bp = Blueprint("provider", __name__)

# Identical to the endpoint rows in conf/routes.yaml (Quart spells a path parameter <name>, the registry {name}).
PROVIDERS = "/api/v1/providers"
PROVIDER = "/api/v1/providers/{provider}"
PROVIDER_MODELS = "/api/v1/providers/{provider}/models"
PROVIDER_INSTANCES = "/api/v1/providers/{provider}/instances"
PROVIDER_INSTANCE = "/api/v1/providers/{provider}/instances/{instance}"

AREA = "tenant_settings"
VIEW = "view_models"
WRITE = "update_llm_keys"
LOOKUP_TIMEOUT_SECONDS = 10.0
# The service tests at most two models, 20 s each; the handler waits longer so the service's own typed timeout wins (T-03-12-06).
PROVIDER_TIMEOUT_SECONDS = 50.0
_TENANT_ID_PATTERN = r"^[0-9a-f]{32}$"


# ----------------------------------------------------------------------------- request models (no unknown fields, ever)


class ModelBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(pattern=r"^[^\s@]{1,128}$")
    type: Literal["chat", "embedding"]


class SaveProviderBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str = Field(min_length=1, max_length=64)
    instance_name: SafeIdentifier = DEFAULT_INSTANCE
    api_key: SecretStr | None = Field(default=None, max_length=2048)
    base_url: str | None = Field(default=None, max_length=255)
    api_version: str | None = Field(default=None, max_length=64)
    models: list[ModelBody] = Field(min_length=1, max_length=2)
    tenant_id: str | None = Field(default=None, pattern=_TENANT_ID_PATTERN)


class AddInstanceBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    instance_name: SafeIdentifier = DEFAULT_INSTANCE
    api_key: SecretStr | None = Field(default=None, max_length=2048)
    base_url: str | None = Field(default=None, max_length=255)
    api_version: str | None = Field(default=None, max_length=64)
    models: list[ModelBody] = Field(min_length=1, max_length=2)
    tenant_id: str | None = Field(default=None, pattern=_TENANT_ID_PATTERN)


# ----------------------------------------------------------------------------- response models (documentation for the OpenAPI export)


class ModelView(BaseModel):
    id: str
    name: str
    type: str
    dimension: int | None
    max_tokens: int
    instance: str
    used_tokens: int


class InstanceView(BaseModel):
    name: str
    configured: bool
    models: list[str]
    last4: str | None = None  # owner and admin only
    base_url: str | None = None  # owner and admin only
    api_version: str | None = None  # owner and admin only


class ProviderView(BaseModel):
    name: str
    slug: str
    configured: bool
    instances: list[InstanceView]
    models: list[ModelView]


class ProviderEnvelope(BaseModel):
    code: int
    message: str
    data: ProviderView


class ProviderListEnvelope(BaseModel):
    code: int
    message: str
    data: list[ProviderView]


class ModelListEnvelope(BaseModel):
    code: int
    message: str
    data: list[ModelView]


class InstanceEnvelope(BaseModel):
    code: int
    message: str
    data: InstanceView


class DeletedView(BaseModel):
    deleted: bool


class DeletedEnvelope(BaseModel):
    code: int
    message: str
    data: DeletedView


# ----------------------------------------------------------------------------- helpers


def _settings() -> Settings:
    return current_app.extensions["ragflow_settings"]


def _spec(provider: str) -> ProviderSpec | None:
    try:
        return resolve_provider(provider)
    except UnknownProvider:
        return None


def _secret(value: SecretStr | None) -> str | None:
    return value.get_secret_value() if value is not None else None


def _models(items: list[ModelBody]) -> tuple[ModelRequest, ...]:
    return tuple(ModelRequest(item.name, item.type) for item in items)


async def _guard(tenant_id: str | None, action: str) -> ActingScope | Response:
    """The acting scope, or the answer to return instead: 404 when there is no such workspace for the caller, 403 without the permission."""
    scope = await acting_scope(tenant_id)
    if scope is None:
        return not_found_response()
    denied = forbid_unless(scope, AREA, action)
    return denied if denied is not None else scope


def _provider_view(spec: ProviderSpec, info: tenant_model_service.ProviderInfo | None, scope: ActingScope) -> dict[str, Any]:
    return provider_service.provider_dto(spec, info, include_credentials=credentials_visible(scope))


# ----------------------------------------------------------------------------- GET /providers


@document_response(ProviderListEnvelope, 200)
async def list_providers() -> Response:
    try:
        scope = await _guard(request.args.get("tenant_id"), VIEW)
        if isinstance(scope, Response):
            return scope
        views = await run_blocking(
            DB_EXECUTOR, lambda: provider_service.list_provider_dtos(scope.tenant_id, include_credentials=credentials_visible(scope)), timeout=LOOKUP_TIMEOUT_SECONDS
        )
        return json_result(views)
    except ServiceError as exc:
        return service_error_response(exc)


# ----------------------------------------------------------------------------- PUT /providers


@validate_request(SaveProviderBody)
@document_response(ProviderEnvelope, 200)
async def save_provider(data: SaveProviderBody) -> Response:
    """Add a provider, or change the key and/or address of a configured one: the body's models are re-tested, the rest are kept."""
    try:
        scope = await _guard(data.tenant_id, WRITE)
        if isinstance(scope, Response):
            return scope
        request_ = SaveRequest(
            tenant_id=scope.tenant_id,
            provider=data.provider,
            models=_models(data.models),
            instance=data.instance_name,
            api_key=_secret(data.api_key),
            base_url=data.base_url,
            api_version=data.api_version,
        )
        settings = _settings()  # read on the loop: the worker thread has no application context
        saved = await run_blocking(PROVIDER_EXECUTOR, lambda: provider_service.save_provider(settings, request_), timeout=PROVIDER_TIMEOUT_SECONDS)
        return json_result(_provider_view(resolve_provider(saved.provider), saved, scope))
    except ServiceError as exc:
        return service_error_response(exc)


# ----------------------------------------------------------------------------- DELETE /providers/{provider}


@document_response(DeletedEnvelope, 200)
async def delete_provider(provider: str) -> Response:
    try:
        scope = await _guard(request.args.get("tenant_id"), WRITE)
        if isinstance(scope, Response):
            return scope
        removed = await run_blocking(DB_EXECUTOR, provider_service.delete_provider, scope.tenant_id, provider, timeout=LOOKUP_TIMEOUT_SECONDS)
        return json_result({"deleted": True}) if removed else not_found_response()
    except ServiceError as exc:
        return service_error_response(exc)


# ----------------------------------------------------------------------------- GET /providers/{provider}/models


@document_response(ModelListEnvelope, 200)
async def list_provider_models(provider: str) -> Response:
    try:
        scope = await _guard(request.args.get("tenant_id"), VIEW)
        if isinstance(scope, Response):
            return scope
        spec = _spec(provider)
        if spec is None:
            return not_found_response()
        info = await run_blocking(DB_EXECUTOR, tenant_model_service.get_provider, scope.tenant_id, spec.name, timeout=LOOKUP_TIMEOUT_SECONDS)
        if info is None:
            return not_found_response()
        return json_result([provider_service.model_dto(model) for model in info.models])
    except ServiceError as exc:
        return service_error_response(exc)


# ----------------------------------------------------------------------------- POST /providers/{provider}/instances


@validate_request(AddInstanceBody)
@document_response(ProviderEnvelope, 200)
async def add_instance(provider: str, data: AddInstanceBody) -> Response:
    """Models only: test and add them to an existing instance with its stored key. Credentials in the body: create that instance."""
    try:
        scope = await _guard(data.tenant_id, WRITE)
        if isinstance(scope, Response):
            return scope
        spec = _spec(provider)
        if spec is None:
            return not_found_response()
        tenant_id, instance, settings = scope.tenant_id, data.instance_name, _settings()  # settings are read on the loop, not in the worker
        key, models = _secret(data.api_key), _models(data.models)
        sends_credentials = any((value or "").strip() for value in (key, data.base_url, data.api_version))
        existing = await run_blocking(DB_EXECUTOR, tenant_model_service.get_instance, tenant_id, spec.name, instance, timeout=LOOKUP_TIMEOUT_SECONDS)
        if sends_credentials:
            if existing is not None:
                raise ServiceError(Kind.INVALID, reasons.INSTANCE_EXISTS, "that instance already exists; change its key or address instead")
            request_ = SaveRequest(
                tenant_id=tenant_id, provider=spec.name, models=models, instance=instance, api_key=key, base_url=data.base_url, api_version=data.api_version
            )
            saved = await run_blocking(PROVIDER_EXECUTOR, lambda: provider_service.save_provider(settings, request_), timeout=PROVIDER_TIMEOUT_SECONDS)
        else:
            if existing is None:
                return not_found_response()
            saved = await run_blocking(
                PROVIDER_EXECUTOR,
                lambda: provider_service.add_models(settings, tenant_id, spec.name, instance, models),
                timeout=PROVIDER_TIMEOUT_SECONDS,
            )
        return json_result(_provider_view(spec, saved, scope))
    except ServiceError as exc:
        return service_error_response(exc)


# ----------------------------------------------------------------------------- GET /providers/{provider}/instances/{instance}


@document_response(InstanceEnvelope, 200)
async def get_instance(provider: str, instance: str) -> Response:
    try:
        scope = await _guard(request.args.get("tenant_id"), WRITE)
        if isinstance(scope, Response):
            return scope
        spec = _spec(provider)
        if spec is None:
            return not_found_response()
        info = await run_blocking(DB_EXECUTOR, tenant_model_service.get_provider, scope.tenant_id, spec.name, timeout=LOOKUP_TIMEOUT_SECONDS)
        stored = next((i for i in (info.instances if info else ()) if i.instance == instance), None)
        if info is None or stored is None:
            return not_found_response()
        return json_result(provider_service.instance_dto(stored, info.models, include_credentials=credentials_visible(scope)))
    except ServiceError as exc:
        return service_error_response(exc)


def _rule(path: str) -> str:
    return path.replace("{", "<").replace("}", ">")


provider_bp.add_url_rule(PROVIDERS, endpoint="list_providers", view_func=list_providers, methods=["GET"])
provider_bp.add_url_rule(PROVIDERS, endpoint="save_provider", view_func=save_provider, methods=["PUT"])
provider_bp.add_url_rule(_rule(PROVIDER), endpoint="delete_provider", view_func=delete_provider, methods=["DELETE"])
provider_bp.add_url_rule(_rule(PROVIDER_MODELS), endpoint="list_provider_models", view_func=list_provider_models, methods=["GET"])
provider_bp.add_url_rule(_rule(PROVIDER_INSTANCES), endpoint="add_instance", view_func=add_instance, methods=["POST"])
provider_bp.add_url_rule(_rule(PROVIDER_INSTANCE), endpoint="get_instance", view_func=get_instance, methods=["GET"])
