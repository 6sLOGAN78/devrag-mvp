"""Provider policy, save-time test calls, atomic save and masked views (LLM-16, LLM-19, LLM-24, LLM-25, LLM-27, SEC-02; plan 03-10).

A provider is stored only after one tiny real call per submitted model has passed (D-16). Policy checks are pure
(``check_request``); the flow in ``save_provider`` and ``add_models`` is: key store ready, address guard, per-workspace
rate window, test calls (retries off, short timeout), then the transactional ``tenant_model_service.save_instance`` /
``add_models``. Every blocking call here is synchronous and meant to run in the handler's bounded executor.

Safety rules: no key, envelope, address text or provider body is placed in an exception message or a log line; provider
text reaches a message only as ``ModelException.safe_message`` with the submitted key scrubbed out again. The views are plain
dicts whose address and ``last4`` appear only when the caller passes ``include_credentials=True``. This module imports no web
framework and decides nothing from a role.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field

from api.db.services.service_errors import Kind, ServiceError
from api.db.services.tenant_model_service import InstanceInfo
from api.utils import reasons
from common.model_ref import DEFAULT_INSTANCE, InvalidModelRef, format_model_ref
from rag.llm import ProviderSpec, validate_base_url_shape

MAX_MODELS_PER_SAVE = 2
MODEL_TYPES = ("chat", "embedding")
_MODEL_NAME = re.compile(r"^[^\s@]{1,128}$")


@dataclass(frozen=True)
class ModelRequest:
    name: str
    model_type: str


@dataclass(frozen=True, kw_only=True)
class SaveRequest:
    tenant_id: str
    provider: str
    models: tuple[ModelRequest, ...]
    instance: str = DEFAULT_INSTANCE
    api_key: str | None = field(default=None, repr=False)
    base_url: str | None = None
    api_version: str | None = None


def _invalid(reason: str, message: str) -> ServiceError:
    return ServiceError(Kind.INVALID, reason, message)


# ----------------------------------------------------------------------------- pure policy


def check_model_names(spec: ProviderSpec, instance: str, models: Sequence[ModelRequest]) -> None:
    """Each id is 1..128 characters without whitespace or ``@``, and its composite id fits the 128-character columns."""
    for model in models:
        if not isinstance(model.name, str) or not _MODEL_NAME.match(model.name):
            raise _invalid(reasons.MODELS_INVALID, "that model name is not valid")
        try:
            format_model_ref(model.name, spec.name, instance)
        except InvalidModelRef:
            raise _invalid(reasons.MODELS_INVALID, "that model name is too long for this provider") from None


def _check_model_list(spec: ProviderSpec, instance: str, models: Sequence[ModelRequest]) -> None:
    types = [m.model_type for m in models]
    if not 1 <= len(models) <= MAX_MODELS_PER_SAVE or any(t not in MODEL_TYPES for t in types) or len(set(types)) != len(types):
        raise _invalid(reasons.MODELS_INVALID, "add one chat model, one embedding model, or both")
    check_model_names(spec, instance, models)


def _address(value: str | None, default: str | None = None) -> str:
    return ((value or "").strip() or (default or "")).rstrip("/")


def _address_changed(spec: ProviderSpec, req: SaveRequest, existing: InstanceInfo) -> bool:
    old_base, new_base = _address(existing.api_base, spec.default_base_url), _address(req.base_url, spec.default_base_url)
    return old_base != new_base or _address(existing.api_version) != _address(req.api_version)


def check_request(spec: ProviderSpec, req: SaveRequest, existing: InstanceInfo | None) -> None:
    """The pure rules of a save. ``existing`` is the stored instance, if any. Raises ``ServiceError`` (INVALID)."""
    _check_model_list(spec, req.instance, req.models)
    has_new_key = bool((req.api_key or "").strip())
    keyed = existing is not None and existing.has_key  # the sealed envelope, never the possibly empty last4
    if spec.key == "required" and not has_new_key and not keyed:
        raise _invalid(reasons.KEY_REQUIRED, "an API key is required for this provider")
    shape = validate_base_url_shape(spec, req.base_url)
    if shape == "base_url_required":
        raise _invalid(reasons.BASE_URL_REQUIRED, "a base URL is required for this provider")
    if shape is not None:
        raise _invalid(reasons.BASE_URL_INVALID, "that base URL is not valid for this provider")
    if spec.requires_api_version and not (req.api_version or "").strip():
        raise _invalid(reasons.API_VERSION_REQUIRED, "an API version is required for this provider")
    if keyed and not has_new_key and _address_changed(spec, req, existing):
        raise _invalid(reasons.KEY_REQUIRED_FOR_NEW_ADDRESS, "enter the key again to use a different address")
