"""Model list and explicit workspace defaults for the models routes (plan 03-13; LLM-28, LLM-29, TEN-12, D-17, D-18).

This module is a thin policy layer over ``tenant_model_service``: it shapes the response dictionaries (every key is listed here, so no
credential field can ride along), validates what a client sends, and turns an invalid composite id into a typed ``model_unavailable``.
Nothing is ever chosen on the caller's behalf: a default that is not set stays empty until an owner or admin picks one. This module
imports nothing from quart.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from api.db.services import tenant_model_service
from api.db.services.service_errors import Kind, ServiceError
from api.db.services.tenant_model_service import ModelInfo, Unset
from api.utils import reasons
from common.model_ref import InvalidModelRef, ModelRef, parse_model_ref

MODEL_TYPES = frozenset(tenant_model_service.TYPE_BITS)
DEFAULT_SLOTS = ("chat", "embedding")


def model_dto(info: ModelInfo) -> dict[str, Any]:
    """One configured model. Keys are explicit: no key, envelope, address or last4 is reachable from here."""
    return {
        "id": info.composite,
        "name": info.model,
        "provider": info.provider,
        "instance": info.instance,
        "type": info.model_type,
        "dimension": info.dimension,
        "max_tokens": info.max_tokens,
        "used_tokens": info.used_tokens,
    }


def list_model_dtos(tenant_id: str, model_type: str | None) -> list[dict[str, Any]]:
    if model_type is not None and model_type not in MODEL_TYPES:
        raise ServiceError(Kind.INVALID, reasons.MODELS_INVALID, "type must be chat or embedding")
    return [model_dto(m) for m in tenant_model_service.list_models(tenant_id, model_type)]


def defaults_dto(tenant_id: str) -> dict[str, str]:
    """The workspace defaults as composite ids; an empty string means not set."""
    current = tenant_model_service.get_defaults(tenant_id)
    return {"chat": current.chat, "embedding": current.embedding}


def _ref(value: str) -> ModelRef:
    try:
        return parse_model_ref(value)
    except InvalidModelRef:
        # Covers a malformed id and one longer than the 128 characters of tenant.llm_id / tenant.embd_id: never a database error.
        raise ServiceError(Kind.INVALID, reasons.MODEL_UNAVAILABLE, "that model is not available in this workspace") from None


def update_defaults(tenant_id: str, changes: Mapping[str, str | None]) -> dict[str, str]:
    """Change only the slots present in ``changes``: a string chooses a configured model of the right type, ``None`` clears the slot."""
    if not changes:
        raise ServiceError(Kind.INVALID, reasons.MODELS_INVALID, "name at least one default to change")
    if not set(changes) <= set(DEFAULT_SLOTS):
        raise ServiceError(Kind.INVALID, reasons.MODELS_INVALID, "only chat and embedding defaults exist")
    resolved: dict[str, ModelRef | None | Unset] = {}
    for slot in DEFAULT_SLOTS:
        if slot not in changes:
            resolved[slot] = tenant_model_service.UNSET
            continue
        value = changes[slot]
        resolved[slot] = None if value is None else _ref(value)
    tenant_model_service.set_defaults(tenant_id, chat=resolved["chat"], embedding=resolved["embedding"])
    return defaults_dto(tenant_id)
