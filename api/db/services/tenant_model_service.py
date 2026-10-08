"""Model structure rows, workspace defaults and the atomic provider save (LLM-29, TEN-12, LLM-15, D-17, D-18; plan 03-09).

``tenant_llm`` is the credential system of record (sealed envelope, address, usage counters). ``tenant_model_provider``,
``tenant_model_instance`` and ``tenant_model`` carry the structure, the ids and the recorded embedding dimension. One
``transaction()`` writes all four, so a failure leaves no partial provider. The instance row's ``api_key`` column holds
only a display mask and its ``extra`` holds ``last4``, address and API version. No function here returns or logs a key
or an envelope; ``InstanceInfo.has_key`` is derived from the stored envelope, never from ``last4``.
"""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import peewee

from api.db.database import DB, transaction
from api.db.models import Tenant, TenantLLM, TenantModel, TenantModelInstance, TenantModelProvider
from api.db.models.base import current_timestamp_ms, timestamp_to_date
from api.db.services.service_errors import Kind, ServiceError
from api.db.services.tenant_llm_service import seal_key
from api.utils import reasons
from common.model_ref import DEFAULT_INSTANCE, InvalidModelRef, ModelRef, format_model_ref
from common.security.secretbox import mask_last4
from common.settings import LlmSettings
from rag.llm import ProviderSpec, UnknownProvider, resolve_provider

logger = logging.getLogger(__name__)

TYPE_BITS = {"chat": 1, "embedding": 2}
_BIT_TYPES = {bit: name for name, bit in TYPE_BITS.items()}
MASK_PREFIX = "********"
MAX_DIMENSION = 65536
MAX_TOKENS = 2147483647
MAX_API_BASE = 255  # tenant_llm.api_base is VARCHAR(255)
MAX_API_VERSION = 64
MAX_EXTRA = 512  # tenant_model_instance.extra is VARCHAR(512)
_ENVELOPE_PREFIX = "v1:"
_ACTIVE_LLM = "1"
_ACTIVE = "active"
_DEFAULT_FIELDS = {"chat": ("llm_id", "tenant_llm_id"), "embedding": ("embd_id", "tenant_embd_id")}


@dataclass(frozen=True)
class NewModel:
    name: str
    model_type: str
    dimension: int | None
    max_tokens: int


@dataclass(frozen=True)
class InstanceInfo:
    provider: str
    instance: str
    configured: bool
    last4: str
    has_key: bool
    api_base: str | None
    api_version: str | None


@dataclass(frozen=True)
class ModelInfo:
    id: str
    model: str
    provider: str
    instance: str
    model_type: str
    dimension: int | None
    max_tokens: int
    used_tokens: int
    composite: str


@dataclass(frozen=True)
class ProviderInfo:
    provider: str
    instances: tuple[InstanceInfo, ...]
    models: tuple[ModelInfo, ...]


@dataclass(frozen=True)
class Defaults:
    chat: str
    embedding: str


class Unset:
    """Sentinel: leave this default as it is."""

    def __repr__(self) -> str:
        return "UNSET"


UNSET = Unset()


def _invalid(reason: str, message: str) -> ServiceError:
    return ServiceError(Kind.INVALID, reason, message)


def _spec(provider: str) -> ProviderSpec:
    try:
        return resolve_provider(provider)
    except UnknownProvider:
        raise _invalid(reasons.PROVIDER_UNKNOWN, "unknown provider") from None


def _loads(text: str | None) -> dict[str, Any]:
    try:
        value = json.loads(text or "{}")
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}


def _stamp() -> dict[str, Any]:
    now = current_timestamp_ms()
    return {"update_time": now, "update_date": timestamp_to_date(now)}


def _new_id() -> str:
    return uuid.uuid4().hex


# ----------------------------------------------------------------------------- validation


def _check_instance(provider: str, instance: str) -> None:
    try:
        format_model_ref("m", provider, instance)
    except InvalidModelRef:
        raise _invalid(reasons.INSTANCE_INVALID, "that instance name is not valid") from None
    if "|" in instance:
        raise _invalid(reasons.INSTANCE_INVALID, "that instance name is not valid")


def _check_models(provider: str, instance: str, models: Sequence[NewModel]) -> None:
    """Refuse bad types, sizes and names (including a composite id over 128 characters) before any write."""
    seen: set[str] = set()
    for model in models:
        bad = model.model_type not in TYPE_BITS or model.name in seen
        bad = bad or not isinstance(model.max_tokens, int) or not 1 <= model.max_tokens <= MAX_TOKENS
        if model.model_type == "embedding":
            bad = bad or not isinstance(model.dimension, int) or not 1 <= model.dimension <= MAX_DIMENSION
        elif model.dimension is not None:
            bad = True
        if not bad:
            try:
                format_model_ref(model.name, provider, instance)
            except InvalidModelRef:
                raise _invalid(reasons.MODELS_INVALID, "that model name is too long for this provider") from None
        if bad:
            raise _invalid(reasons.MODELS_INVALID, "the model list is not valid")
        seen.add(model.name)


def _extra_json(last4: str, api_base: str | None, api_version: str | None) -> str:
    text = json.dumps({"last4": last4, "api_base": api_base, "api_version": api_version})
    if len(text) > MAX_EXTRA:
        raise _invalid(reasons.BASE_URL_INVALID, "the address is too long")
    return text


def _clean_address(api_base: str | None, api_version: str | None) -> tuple[str | None, str | None]:
    base, version = (api_base or "").strip() or None, (api_version or "").strip() or None
    if (base and len(base) > MAX_API_BASE) or (version and len(version) > MAX_API_VERSION):
        raise _invalid(reasons.BASE_URL_INVALID, "the address is too long")
    return base, version


# ----------------------------------------------------------------------------- writes


def _conflict() -> ServiceError:
    return ServiceError(Kind.CONFLICT, reasons.MODEL_EXISTS, "that model is already added")


def _insert_model(tenant_id: str, provider: str, provider_id: str, instance_id: str, model: NewModel, envelope: str, api_base: str | None) -> None:
    TenantModel.create(
        id=_new_id(),
        model_name=model.name,
        provider_id=provider_id,
        instance_id=instance_id,
        model_type=TYPE_BITS[model.model_type],
        status=_ACTIVE,
        extra=json.dumps({"dimension": model.dimension, "max_tokens": model.max_tokens}),
    )
    TenantLLM.create(
        tenant_id=tenant_id,
        llm_factory=provider,
        model_type=model.model_type,
        llm_name=model.name,
        api_key=envelope,
        api_base=api_base,
        max_tokens=model.max_tokens,
        used_tokens=0,
        status=_ACTIVE_LLM,
    )


def _provider_models(provider_id: str) -> dict[str, TenantModel]:
    return {m.model_name: m for m in TenantModel.select().where(TenantModel.provider_id == provider_id)}


def _check_existing(requested: Sequence[NewModel], owned: dict[str, TenantModel], instance_id: str | None, orphans: set[str], *, upsert: bool) -> set[str]:
    """Names to keep as they are. Raises model_exists / dimension_mismatch; nothing has been written yet."""
    keep: set[str] = set()
    for model in requested:
        row = owned.get(model.name)
        if row is None:
            if model.name in orphans:
                raise _conflict()
            continue
        if not upsert or row.instance_id != instance_id or _BIT_TYPES.get(row.model_type) != model.model_type:
            raise _conflict()
        if model.model_type == "embedding" and _loads(row.extra).get("dimension") != model.dimension:
            raise _invalid(reasons.DIMENSION_MISMATCH, "the model's vector size changed")
        keep.add(model.name)
    return keep


def _stored_envelope(tenant_id: str, provider: str, names: Sequence[str]) -> str:
    if not names:
        return ""
    row = TenantLLM.select(TenantLLM.api_key).where(TenantLLM.tenant_id == tenant_id, TenantLLM.llm_factory == provider, TenantLLM.llm_name << list(names), TenantLLM.api_key != "").dicts().first()
    return (row or {}).get("api_key") or ""


def _write_save(llm: LlmSettings, tenant_id: str, spec: ProviderSpec, instance: str, key: str, base: str | None, version: str | None, models: Sequence[NewModel], replace_key: bool) -> int:
    name = spec.name
    provider = TenantModelProvider.get_or_none(TenantModelProvider.tenant_id == tenant_id, TenantModelProvider.provider_name == name)
    row = None
    if provider is not None:
        row = TenantModelInstance.get_or_none(TenantModelInstance.provider_id == provider.id, TenantModelInstance.instance_name == instance)
    owned = _provider_models(provider.id) if provider is not None else {}
    orphans = {r.llm_name for r in TenantLLM.select(TenantLLM.llm_name).where(TenantLLM.tenant_id == tenant_id, TenantLLM.llm_factory == name)}
    _check_existing(models, owned, row.id if row is not None else None, orphans, upsert=True)

    own_names = [n for n, m in owned.items() if row is not None and m.instance_id == row.id]
    reseal = replace_key or row is None
    if reseal:
        envelope, last4 = (seal_key(llm, tenant_id, name, instance, key), mask_last4(key)) if key else ("", "")
        mask = f"{MASK_PREFIX}{last4}" if envelope else ""
    else:
        envelope, last4, mask = _stored_envelope(tenant_id, name, own_names), str(_loads(row.extra).get("last4") or ""), row.api_key
    extra = _extra_json(last4, base, version)

    if provider is None:
        provider = TenantModelProvider.create(id=_new_id(), provider_name=name, tenant_id=tenant_id)
    if row is None:
        row = TenantModelInstance.create(id=_new_id(), instance_name=instance, provider_id=provider.id, api_key=mask, status=_ACTIVE, extra=extra)
    else:
        fields: dict[str, Any] = {"extra": extra, **_stamp()}
        if reseal:
            fields["api_key"] = mask
        TenantModelInstance.update(**fields).where(TenantModelInstance.id == row.id).execute()
    if own_names:
        updates: dict[str, Any] = {"api_base": base, **_stamp()}
        if reseal:
            updates["api_key"] = envelope
        TenantLLM.update(**updates).where(TenantLLM.tenant_id == tenant_id, TenantLLM.llm_factory == name, TenantLLM.llm_name << own_names).execute()
    added = [m for m in models if m.name not in owned]
    for model in added:
        _insert_model(tenant_id, name, provider.id, row.id, model, envelope, base)
    return len(added)


def save_instance(
    llm: LlmSettings,
    tenant_id: str,
    provider: str,
    instance: str,
    *,
    api_key: str | None,
    api_base: str | None,
    api_version: str | None,
    models: Sequence[NewModel],
    replace_key: bool,
) -> ProviderInfo:
    """Create or update one provider instance and its models in one transaction (an upsert).

    A new instance always takes ``api_key``. For an existing one, ``replace_key=False`` keeps every stored envelope and the
    mask and only replaces the address fields; ``replace_key=True`` re-seals EVERY ``tenant_llm`` row of the instance (listed
    or not) with the new key, and an empty key then clears it. Models already present keep their ids and usage; new names
    are added; a name owned by another instance is ``model_exists``; a changed embedding dimension is ``dimension_mismatch``.
    The address is stored exactly as given (the caller decides whether to resend the stored one).
    """
    spec = _spec(provider)
    _check_instance(spec.name, instance)
    _check_models(spec.name, instance, models)
    base, version = _clean_address(api_base, api_version)
    with DB.connection_context():
        for attempt in (1, 2):
            try:
                with transaction():
                    added = _write_save(llm, tenant_id, spec, instance, api_key or "", base, version, models, replace_key)
                break
            except peewee.IntegrityError:
                if attempt == 2:
                    raise _conflict() from None
        logger.info("provider saved tenant=%s provider=%s instance=%s listed=%d added=%d", tenant_id, spec.name, instance, len(models), added)
        return _load(tenant_id, spec.name)[0]


def add_models(llm: LlmSettings, tenant_id: str, provider: str, instance: str, models: Sequence[NewModel]) -> ProviderInfo:
    """Append models to a configured instance, reusing its stored envelope (same binding, no decryption)."""
    spec = _spec(provider)
    _check_instance(spec.name, instance)
    _check_models(spec.name, instance, models)
    with DB.connection_context():
        try:
            with transaction():
                prow = TenantModelProvider.get_or_none(TenantModelProvider.tenant_id == tenant_id, TenantModelProvider.provider_name == spec.name)
                irow = prow and TenantModelInstance.get_or_none(TenantModelInstance.provider_id == prow.id, TenantModelInstance.instance_name == instance)
                if not irow:
                    raise ServiceError(Kind.NOT_FOUND, reasons.PROVIDER_NOT_CONFIGURED, "that provider is not configured")
                owned = _provider_models(prow.id)
                orphans = {r.llm_name for r in TenantLLM.select(TenantLLM.llm_name).where(TenantLLM.tenant_id == tenant_id, TenantLLM.llm_factory == spec.name)}
                _check_existing(models, owned, irow.id, orphans, upsert=False)
                names = [n for n, m in owned.items() if m.instance_id == irow.id]
                envelope = _stored_envelope(tenant_id, spec.name, names)
                base = _loads(irow.extra).get("api_base")
                for model in models:
                    _insert_model(tenant_id, spec.name, prow.id, irow.id, model, envelope, base)
        except peewee.IntegrityError:
            raise _conflict() from None
        logger.info("models added tenant=%s provider=%s instance=%s added=%d", tenant_id, spec.name, instance, len(models))
        return _load(tenant_id, spec.name)[0]


# ----------------------------------------------------------------------------- reads


def _key_required(provider: str) -> bool:
    try:
        return resolve_provider(provider).key == "required"
    except UnknownProvider:
        return False


def _composite(model: str, provider: str, instance: str) -> str:
    try:
        return format_model_ref(model, provider, instance)
    except InvalidModelRef:  # a legacy row that this service would not have written
        return f"{model}@{provider}" if instance == DEFAULT_INSTANCE else f"{model}@{instance}@{provider}"


def _load(tenant_id: str, provider: str | None = None) -> list[ProviderInfo]:
    """Structure only: the stored envelope is reduced to a boolean inside SQL and never leaves the database."""
    query = TenantModelProvider.select().where(TenantModelProvider.tenant_id == tenant_id).order_by(TenantModelProvider.provider_name)
    if provider is not None:
        query = query.where(TenantModelProvider.provider_name == provider)
    providers = list(query)
    if not providers:
        return []
    ids = [p.id for p in providers]
    instances = list(TenantModelInstance.select().where(TenantModelInstance.provider_id << ids).order_by(TenantModelInstance.instance_name))
    rows = list(TenantModel.select().where(TenantModel.provider_id << ids).order_by(TenantModel.model_name))
    sealed = TenantLLM.api_key.startswith(_ENVELOPE_PREFIX).alias("sealed")
    llm_rows = {
        (r["llm_factory"], r["llm_name"]): r
        for r in TenantLLM.select(TenantLLM.llm_factory, TenantLLM.llm_name, TenantLLM.max_tokens, TenantLLM.used_tokens, sealed).where(TenantLLM.tenant_id == tenant_id).dicts()
    }
    inst_names = {i.id: i.instance_name for i in instances}
    out: list[ProviderInfo] = []
    for prov in providers:
        models = []
        has_key: dict[str, bool] = {}
        for m in (r for r in rows if r.provider_id == prov.id):
            llm_row = llm_rows.get((prov.provider_name, m.model_name), {})
            instance = inst_names.get(m.instance_id, DEFAULT_INSTANCE)
            has_key[m.instance_id] = has_key.get(m.instance_id, False) or bool(llm_row.get("sealed"))
            extra = _loads(m.extra)
            models.append(
                ModelInfo(
                    id=m.id,
                    model=m.model_name,
                    provider=prov.provider_name,
                    instance=instance,
                    model_type=_BIT_TYPES.get(m.model_type, "other"),
                    dimension=extra.get("dimension") if isinstance(extra.get("dimension"), int) else None,
                    max_tokens=int(llm_row.get("max_tokens") or extra.get("max_tokens") or 0),
                    used_tokens=int(llm_row.get("used_tokens") or 0),
                    composite=_composite(m.model_name, prov.provider_name, instance),
                )
            )
        required = _key_required(prov.provider_name)
        infos = []
        for inst in (i for i in instances if i.provider_id == prov.id):
            extra = _loads(inst.extra)
            keyed = has_key.get(inst.id, False)
            has_models = any(m.instance_id == inst.id for m in rows)
            configured = has_models and (keyed or not required)
            last4 = str(extra.get("last4") or "")
            infos.append(InstanceInfo(prov.provider_name, inst.instance_name, configured, last4, keyed, extra.get("api_base") or None, extra.get("api_version") or None))
        out.append(ProviderInfo(prov.provider_name, tuple(infos), tuple(models)))
    return out


def list_providers(tenant_id: str) -> list[ProviderInfo]:
    with DB.connection_context():
        return _load(tenant_id)


def get_provider(tenant_id: str, provider: str) -> ProviderInfo | None:
    try:
        name = resolve_provider(provider).name
    except UnknownProvider:
        return None
    with DB.connection_context():
        found = _load(tenant_id, name)
    return found[0] if found else None


def get_instance(tenant_id: str, provider: str, instance: str) -> InstanceInfo | None:
    info = get_provider(tenant_id, provider)
    return next((i for i in info.instances if i.instance == instance), None) if info else None


def _find(tenant_id: str, ref: ModelRef) -> ModelInfo | None:
    try:
        name = resolve_provider(ref.provider).name
    except UnknownProvider:
        return None
    for prov in _load(tenant_id, name):
        for model in prov.models:
            if model.model == ref.model and model.instance == ref.instance:
                return model
    return None


def find_model(tenant_id: str, ref: ModelRef) -> ModelInfo | None:
    with DB.connection_context():
        return _find(tenant_id, ref)


def list_models(tenant_id: str, model_type: str | None = None) -> list[ModelInfo]:
    with DB.connection_context():
        found = [m for p in _load(tenant_id) for m in p.models]
    return [m for m in found if model_type is None or m.model_type == model_type]


# ----------------------------------------------------------------------------- delete and defaults


def _provider_of(composite: str) -> str | None:
    try:
        return resolve_provider(composite.rsplit("@", 1)[-1]).name
    except UnknownProvider:
        return None


def delete_provider(tenant_id: str, provider: str) -> bool:
    """Remove a provider with its instances, models and credentials, and blank every default that pointed at it."""
    try:
        name = resolve_provider(provider).name
    except UnknownProvider:
        return False
    with DB.connection_context():
        with transaction():
            prow = TenantModelProvider.get_or_none(TenantModelProvider.tenant_id == tenant_id, TenantModelProvider.provider_name == name)
            if prow is None:
                return False
            model_ids = {m.id for m in TenantModel.select(TenantModel.id).where(TenantModel.provider_id == prow.id)}
            TenantModel.delete().where(TenantModel.provider_id == prow.id).execute()
            TenantModelInstance.delete().where(TenantModelInstance.provider_id == prow.id).execute()
            TenantModelProvider.delete().where(TenantModelProvider.id == prow.id).execute()
            TenantLLM.delete().where(TenantLLM.tenant_id == tenant_id, TenantLLM.llm_factory == name).execute()
            tenant = Tenant.get_or_none(Tenant.id == tenant_id)
            cleared: dict[str, Any] = {}
            for field, id_field in _DEFAULT_FIELDS.values():
                if tenant is not None and (getattr(tenant, id_field) in model_ids or _provider_of(getattr(tenant, field) or "") == name):
                    cleared.update({field: "", id_field: None})
            if cleared:
                Tenant.update(**cleared, **_stamp()).where(Tenant.id == tenant_id).execute()
        logger.info("provider deleted tenant=%s provider=%s models=%d defaults_cleared=%d", tenant_id, name, len(model_ids), len(cleared) // 2)
    return True


def get_defaults(tenant_id: str) -> Defaults:
    with DB.connection_context():
        tenant = Tenant.get_or_none(Tenant.id == tenant_id)
    return Defaults(chat=(tenant.llm_id or "") if tenant else "", embedding=(tenant.embd_id or "") if tenant else "")


def set_defaults(tenant_id: str, *, chat: ModelRef | None | Unset = UNSET, embedding: ModelRef | None | Unset = UNSET) -> Defaults:
    """Store workspace defaults as composite ids plus the ``tenant_model`` ids. ``UNSET`` keeps, ``None`` clears."""
    with DB.connection_context():
        if Tenant.get_or_none(Tenant.id == tenant_id) is None:
            raise ServiceError(Kind.NOT_FOUND, "workspace_not_found", "that workspace does not exist")
        updates: dict[str, Any] = {}
        for kind, ref in (("chat", chat), ("embedding", embedding)):
            if isinstance(ref, Unset):
                continue
            field, id_field = _DEFAULT_FIELDS[kind]
            if ref is None:
                updates.update({field: "", id_field: None})
                continue
            found = _find(tenant_id, ref)
            if found is None or found.model_type != kind:
                raise _invalid(reasons.MODEL_UNAVAILABLE, "that model is not available in this workspace")
            updates.update({field: found.composite, id_field: found.id})
        if updates:
            Tenant.update(**updates, **_stamp()).where(Tenant.id == tenant_id).execute()
    return get_defaults(tenant_id)
