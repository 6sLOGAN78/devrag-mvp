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

import dataclasses
import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from api.db.services import tenant_llm_service, tenant_model_service
from api.db.services.service_errors import Kind, ServiceError
from api.db.services.tenant_model_service import InstanceInfo, ModelInfo, NewModel, ProviderInfo
from api.utils import reasons
from common.model_ref import DEFAULT_INSTANCE, InvalidModelRef, ModelRef, format_model_ref
from common.net.url_guard import UnsafeBaseUrl, validate_base_url
from common.ratelimit import FixedWindowLimiter, RateLimited, RateLimitUnavailable
from common.security import secretbox
from common.settings import LlmSettings, Settings
from rag.llm import PROVIDER_SPECS, ProviderSpec, UnknownProvider, resolve_provider, validate_base_url_shape
from rag.llm.chat_model import LiteLLMBase
from rag.llm.embedding_model import build_embedder
from rag.llm.errors import LLMErrorCode, ModelException
from rag.llm.model_meta import lookup

logger = logging.getLogger(__name__)

MAX_MODELS_PER_SAVE = 2
MODEL_TYPES = ("chat", "embedding")
_MODEL_NAME = re.compile(r"^[^\s@]{1,128}$")
MAX_DIMENSION = 4096
_TEST_MAX_COMPLETION_TOKENS = 16
_TEST_PROMPT = "Reply with the single word: ok"
_TEST_INPUT = "ping"
_LIMIT_KEY = "provider-test:{tenant_id}"
_REFUSAL_CODES = frozenset(
    {
        LLMErrorCode.ERROR_AUTHENTICATION,
        LLMErrorCode.ERROR_INVALID_REQUEST,
        LLMErrorCode.ERROR_QUOTA,
        LLMErrorCode.ERROR_CONTENT_FILTER,
        LLMErrorCode.ERROR_MODEL,
    }
)
_RATE_LIMIT_STATUSES = frozenset({429, 503})
_SCRUBBED = "***"
_FALLBACK_REFUSAL = "the provider rejected the request"


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


# ----------------------------------------------------------------------------- guards


def _spec(provider: str) -> ProviderSpec:
    try:
        return resolve_provider(provider)
    except UnknownProvider:
        raise _invalid(reasons.PROVIDER_UNKNOWN, "unknown provider") from None


def _ensure_key_store(llm: LlmSettings) -> None:
    try:
        secretbox.keyring_from_settings(llm)
    except secretbox.SecretBoxError:
        raise ServiceError(Kind.UNAVAILABLE, reasons.KEY_STORE_UNAVAILABLE, "model provider storage is not configured") from None


def _guard_address(settings: Settings, spec: ProviderSpec, base_url: str | None) -> None:
    """SSRF guard: the project's own hosts are denied and private ranges need ``llm.allow_private_base_urls`` (D-15)."""
    url = _address(base_url, spec.default_base_url)
    if not url or url == spec.default_base_url:
        return  # the documented public host, or nothing to call (check_request refused a missing required address)
    try:
        validate_base_url(url, allow_private=settings.llm.allow_private_base_urls, deny_hosts=tenant_llm_service.internal_hosts(settings))
    except UnsafeBaseUrl:
        raise _invalid(reasons.BASE_URL_REFUSED, "that address can't be used") from None


def _spend_test_ticket(settings: Settings, tenant_id: str, limiter: FixedWindowLimiter | None) -> None:
    """One provider-test ticket per save, per workspace; an unreachable counter store refuses (fail closed)."""
    window = limiter or FixedWindowLimiter(settings.redis)
    try:
        window.hit(_LIMIT_KEY.format(tenant_id=tenant_id), settings.ratelimit.provider_test_per_tenant, settings.ratelimit.provider_test_window_seconds)
    except RateLimited as limited:
        raise ServiceError(Kind.RATE_LIMITED, reasons.PROVIDER_TEST_RATE_LIMITED, "too many provider tests, try again shortly", retry_after=limited.retry_after) from None
    except RateLimitUnavailable:
        raise ServiceError(Kind.UNAVAILABLE, reasons.RATE_LIMIT_UNAVAILABLE, "provider tests are unavailable right now") from None


def _stored_key(settings: Settings, tenant_id: str, spec: ProviderSpec, info: ProviderInfo | None, instance: str) -> str | None:
    """The opened key of an existing instance (in memory only), or None when it has none."""
    for model in (m for m in (info.models if info else ()) if m.instance == instance):
        credential = tenant_llm_service.get_credential(settings.llm, tenant_id, ModelRef(model.model, instance, spec.name))
        if credential is not None and credential.api_key:
            return credential.api_key
    return None


# ----------------------------------------------------------------------------- test calls


def _scrub(text: str, key: str | None) -> str:
    return text.replace(key, _SCRUBBED) if key else text


def _failure(exc: ModelException, key: str | None) -> ServiceError:
    """Map a driver failure to a typed, safe refusal. Only the sanitized provider message is ever shown."""
    code, status = exc.code, exc.provider_status
    limited = code == LLMErrorCode.ERROR_RATE_LIMIT or status in _RATE_LIMIT_STATUSES
    if limited:
        return ServiceError(Kind.UNAVAILABLE, reasons.PROVIDER_RATE_LIMITED, "the provider is limiting requests, try again shortly", retry_after=exc.retry_after)
    if code in _REFUSAL_CODES:
        return _invalid(reasons.PROVIDER_REFUSED, _scrub(exc.safe_message, key) or _FALLBACK_REFUSAL)
    if code == LLMErrorCode.ERROR_TIMEOUT or (code == LLMErrorCode.ERROR_MAX_RETRIES and status is None):
        return ServiceError(Kind.TIMEOUT, reasons.PROVIDER_TIMEOUT, "the provider did not answer in time")
    return ServiceError(Kind.BAD_GATEWAY, reasons.PROVIDER_UNREACHABLE, "the provider could not be reached")


def _test_model(settings: Settings, spec: ProviderSpec, model: ModelRequest, key: str | None, base_url: str | None, api_version: str | None) -> int | None:
    """One tiny real call. Chat returns None; embedding returns the length of the vector the provider sent back."""
    seconds = max(1, settings.llm.key_test_timeout_seconds)
    llm = dataclasses.replace(settings.llm, chat_timeout_seconds=seconds, embedding_timeout_seconds=seconds, max_retries=0)
    common: dict[str, Any] = {
        "llm_settings": llm,
        "allow_private": settings.llm.allow_private_base_urls,
        "deny_hosts": tenant_llm_service.internal_hosts(settings),
        "timeout": seconds,
    }
    try:
        if model.model_type == "chat":
            driver = LiteLLMBase(spec, model.name, key, base_url, api_version, **common)
            driver.chat("", [{"role": "user", "content": _TEST_PROMPT}], {"max_completion_tokens": _TEST_MAX_COMPLETION_TOKENS, "temperature": 0})
            return None
        vectors, _ = build_embedder(spec, model.name, key, base_url, api_version, **common).encode([_TEST_INPUT])
    except ModelException as failed:
        raise _failure(failed, key) from None
    dimension = len(vectors[0]) if vectors else 0
    if not 1 <= dimension <= MAX_DIMENSION:
        raise _invalid(reasons.DIMENSION_UNSUPPORTED, "that embedding model's vector size is not supported")
    return dimension


def _test_all(settings: Settings, spec: ProviderSpec, models: Sequence[ModelRequest], key: str | None, base_url: str | None, api_version: str | None) -> list[NewModel]:
    tested = []
    for model in models:
        dimension = _test_model(settings, spec, model, key, base_url, api_version)
        tested.append(NewModel(name=model.name, model_type=model.model_type, dimension=dimension, max_tokens=lookup(spec.name, model.name).max_tokens))
    return tested


# ----------------------------------------------------------------------------- writes


def _log(action: str, tenant_id: str, provider: str, count: int, outcome: str) -> None:
    logger.info("provider %s tenant=%s provider=%s models=%d outcome=%s", action, tenant_id, provider, count, outcome)


def _instance_of(info: ProviderInfo | None, instance: str) -> InstanceInfo | None:
    return next((i for i in (info.instances if info else ()) if i.instance == instance), None)


def _clean(value: str | None) -> str | None:
    return (value or "").strip() or None


def save_provider(settings: Settings, req: SaveRequest, *, limiter: FixedWindowLimiter | None = None) -> ProviderInfo:
    """Test every submitted model with one real call, then store the provider (or rotate/move an existing instance).

    Nothing is stored unless every test passes. A submitted key replaces the key of every row of the instance; without one
    the stored key is kept and used for the tests, and a keyed instance may not move to a new address (see ``check_request``).
    """
    spec = _spec(req.provider)
    try:
        _ensure_key_store(settings.llm)
        info = tenant_model_service.get_provider(req.tenant_id, spec.name)
        check_request(spec, req, _instance_of(info, req.instance))
        key, base_url, api_version = (req.api_key or "").strip(), _clean(req.base_url), _clean(req.api_version)
        _guard_address(settings, spec, base_url)
        _spend_test_ticket(settings, req.tenant_id, limiter)
        test_key = key or _stored_key(settings, req.tenant_id, spec, info, req.instance)
        tested = _test_all(settings, spec, req.models, test_key or None, base_url, api_version)
        saved = tenant_model_service.save_instance(
            settings.llm,
            req.tenant_id,
            spec.name,
            req.instance,
            api_key=key or None,
            api_base=base_url,
            api_version=api_version,
            models=tested,
            replace_key=bool(key),
        )
    except ServiceError as refused:
        _log("save", req.tenant_id, spec.name, len(req.models), refused.reason)
        raise
    _log("save", req.tenant_id, spec.name, len(req.models), "ok")
    return saved


def add_models(
    settings: Settings,
    tenant_id: str,
    provider: str,
    instance: str,
    models: Sequence[ModelRequest],
    *,
    limiter: FixedWindowLimiter | None = None,
) -> ProviderInfo:
    """Test new models with the instance's stored key and address, then append them."""
    spec = _spec(provider)
    try:
        if not 1 <= len(models) <= MAX_MODELS_PER_SAVE or any(m.model_type not in MODEL_TYPES for m in models) or len({m.name for m in models}) != len(models):
            raise _invalid(reasons.MODELS_INVALID, "add one or two models")
        check_model_names(spec, instance, models)
        info = tenant_model_service.get_provider(tenant_id, spec.name)
        stored = _instance_of(info, instance)
        if stored is None:
            raise ServiceError(Kind.NOT_FOUND, reasons.PROVIDER_NOT_CONFIGURED, "that provider is not configured")
        if {m.name for m in models} & {m.model for m in (info.models if info else ())}:
            raise ServiceError(Kind.CONFLICT, reasons.MODEL_EXISTS, "that model is already added")
        _ensure_key_store(settings.llm)
        _guard_address(settings, spec, stored.api_base)
        _spend_test_ticket(settings, tenant_id, limiter)
        key = _stored_key(settings, tenant_id, spec, info, instance)
        tested = _test_all(settings, spec, models, key, stored.api_base, stored.api_version)
        saved = tenant_model_service.add_models(settings.llm, tenant_id, spec.name, instance, tested)
    except ServiceError as refused:
        _log("add_models", tenant_id, spec.name, len(models), refused.reason)
        raise
    _log("add_models", tenant_id, spec.name, len(models), "ok")
    return saved


def delete_provider(tenant_id: str, provider: str) -> bool:
    """Remove a provider with its instances, models and keys. ``False`` when it was not configured."""
    try:
        spec = resolve_provider(provider)
    except UnknownProvider:
        return False
    removed = tenant_model_service.delete_provider(tenant_id, spec.name)
    _log("delete", tenant_id, spec.name, 0, "ok" if removed else "absent")
    return removed


# ----------------------------------------------------------------------------- views


def model_dto(model: ModelInfo) -> dict[str, Any]:
    return {
        "id": model.composite,
        "name": model.model,
        "type": model.model_type,
        "dimension": model.dimension,
        "max_tokens": model.max_tokens,
        "instance": model.instance,
        "used_tokens": model.used_tokens,
    }


def instance_dto(info: InstanceInfo, models: Sequence[ModelInfo] = (), *, include_credentials: bool = False) -> dict[str, Any]:
    """Name and configured flag; ``last4`` and the address only when the caller is allowed to see them (D-07, D-26)."""
    out: dict[str, Any] = {"name": info.instance, "configured": info.configured, "models": [m.composite for m in models if m.instance == info.instance]}
    if include_credentials:
        out.update({"last4": info.last4, "base_url": info.api_base, "api_version": info.api_version})
    return out


def provider_dto(spec: ProviderSpec, info: ProviderInfo | None, *, include_credentials: bool) -> dict[str, Any]:
    instances = info.instances if info else ()
    models = info.models if info else ()
    return {
        "name": spec.name,
        "slug": spec.slug,
        "configured": any(i.configured for i in instances),
        "instances": [instance_dto(i, models, include_credentials=include_credentials) for i in instances],
        "models": [model_dto(m) for m in models],
    }


def list_provider_dtos(tenant_id: str, *, include_credentials: bool) -> list[dict[str, Any]]:
    """One entry per supported provider in registry order, configured or not."""
    found = {p.provider: p for p in tenant_model_service.list_providers(tenant_id)}
    return [provider_dto(spec, found.get(spec.name), include_credentials=include_credentials) for spec in PROVIDER_SPECS]
