"""Model list and default-model routes (plan 03-13; LLM-28, TEN-12, TEN-13, D-07, D-17, D-18, D-20, D-26).

Three thin handlers: resolve the acting workspace (a foreign or malformed one is the single not-found body), check the permission matrix,
run the blocking service call in the bounded database executor, map ``ServiceError`` to the envelope. Order is scope (404), then
permission (403). Reading is open to every member (and to an API token, which is ``auth: api``); changing a default is ``auth: jwt`` and
needs ``set_default_models``, so a token never reaches it and a normal member gets 403. A default is never chosen automatically: an
absent key leaves a slot alone (``model_fields_set``), ``null`` clears it, a composite id sets it.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field
from quart import Blueprint, Response, request
from quart_schema import document_response, validate_request

from api.apps.handler_support import acting_scope, forbid_unless
from api.apps.service_errors import not_found_response, service_error_response
from api.db.services import model_defaults_service
from api.db.services.service_errors import ServiceError
from api.db.services.tenant_scope import ActingScope
from api.utils.api_utils import json_result
from api.utils.blocking import DB_EXECUTOR, run_blocking

models_bp = Blueprint("models", __name__)

# Identical to the endpoint rows in conf/routes.yaml.
MODELS = "/api/v1/models"
MODELS_DEFAULT = "/api/v1/models/default"

AREA = "tenant_settings"
VIEW = "view_models"
SET_DEFAULT = "set_default_models"
LOOKUP_TIMEOUT_SECONDS = 10.0
_TENANT_ID_PATTERN = r"^[0-9a-f]{32}$"
_SLOTS = ("chat", "embedding")


class DefaultsBody(BaseModel):
    """No length bound on the ids on purpose: an over-long id is a typed ``model_unavailable`` from the service, like any other bad id."""

    model_config = ConfigDict(extra="forbid")

    chat: str | None = None
    embedding: str | None = None
    tenant_id: str | None = Field(default=None, pattern=_TENANT_ID_PATTERN)


class ModelDescription(BaseModel):
    id: str
    name: str
    provider: str
    instance: str
    type: str
    dimension: int | None
    max_tokens: int
    used_tokens: int


class ModelListEnvelope(BaseModel):
    code: int
    message: str
    data: list[ModelDescription]


class DefaultsView(BaseModel):
    chat: str
    embedding: str


class DefaultsEnvelope(BaseModel):
    code: int
    message: str
    data: DefaultsView


async def _guard(tenant_id: str | None, action: str) -> ActingScope | Response:
    """The acting scope, or the answer to return instead: 404 when there is no such workspace for the caller, 403 without the permission."""
    scope = await acting_scope(tenant_id)
    if scope is None:
        return not_found_response()
    denied = forbid_unless(scope, AREA, action)
    return denied if denied is not None else scope


@document_response(ModelListEnvelope, 200)
async def list_models() -> Response:
    try:
        scope = await _guard(request.args.get("tenant_id"), VIEW)
        if isinstance(scope, Response):
            return scope
        model_type = request.args.get("type")
        views = await run_blocking(DB_EXECUTOR, model_defaults_service.list_model_dtos, scope.tenant_id, model_type, timeout=LOOKUP_TIMEOUT_SECONDS)
        return json_result(views)
    except ServiceError as exc:
        return service_error_response(exc)


@document_response(DefaultsEnvelope, 200)
async def get_defaults() -> Response:
    try:
        scope = await _guard(request.args.get("tenant_id"), VIEW)
        if isinstance(scope, Response):
            return scope
        view = await run_blocking(DB_EXECUTOR, model_defaults_service.defaults_dto, scope.tenant_id, timeout=LOOKUP_TIMEOUT_SECONDS)
        return json_result(view)
    except ServiceError as exc:
        return service_error_response(exc)


@validate_request(DefaultsBody)
@document_response(DefaultsEnvelope, 200)
async def patch_defaults(data: DefaultsBody) -> Response:
    """Set or clear the default chat and embedding model. Only the slots named in the body change."""
    try:
        scope = await _guard(data.tenant_id, SET_DEFAULT)
        if isinstance(scope, Response):
            return scope
        changes = {slot: getattr(data, slot) for slot in _SLOTS if slot in data.model_fields_set}
        view = await run_blocking(DB_EXECUTOR, model_defaults_service.update_defaults, scope.tenant_id, changes, timeout=LOOKUP_TIMEOUT_SECONDS)
        return json_result(view)
    except ServiceError as exc:
        return service_error_response(exc)


models_bp.add_url_rule(MODELS, endpoint="list_models", view_func=list_models, methods=["GET"])
models_bp.add_url_rule(MODELS_DEFAULT, endpoint="get_defaults", view_func=get_defaults, methods=["GET"])
models_bp.add_url_rule(MODELS_DEFAULT, endpoint="patch_defaults", view_func=patch_defaults, methods=["PATCH"])
