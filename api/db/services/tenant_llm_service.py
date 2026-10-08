"""Sealed provider credentials and usage counting (SEC-03, LLM-16, LLM-21; plan 03-09).

``tenant_llm`` is the credential system of record: ``api_key`` holds only the AES-256-GCM envelope bound to
``tenant_id|provider|instance`` (see ``common.security.secretbox``). This module seals on the way in, opens in memory on
the way out and never logs, formats or returns a key anywhere else. ``ModelCredential`` hides the key from ``repr``/``str``.
Failures are ``ServiceError`` with fixed messages; no message holds a key, an envelope or a url.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from api.db.database import DB
from api.db.models import TenantLLM, TenantModel, TenantModelInstance, TenantModelProvider
from api.db.services.service_errors import Kind, ServiceError
from api.utils import reasons
from common.model_ref import ModelRef
from common.security import secretbox
from common.settings import LlmSettings, Settings
from rag.llm import UnknownProvider, resolve_provider

USED_TOKENS_CAP = 2147483647  # tenant_llm.used_tokens is a signed 32-bit INT
_ACTIVE = "1"
_UNUSABLE_STORE = "model provider storage is not configured"
_UNREADABLE = "the stored provider key cannot be read"
_INVALID_INSTANCE = "that instance name is not valid"


@dataclass(frozen=True)
class ModelCredential:
    provider: str
    instance: str
    model: str
    model_type: str
    api_key: str | None = field(repr=False)
    api_base: str | None
    api_version: str | None
    max_tokens: int

    def __repr__(self) -> str:
        return (
            f"ModelCredential(provider={self.provider!r}, instance={self.instance!r}, model={self.model!r}, "
            f"model_type={self.model_type!r}, api_key=<hidden>, max_tokens={self.max_tokens})"
        )

    __str__ = __repr__


def _aad(tenant_id: str, provider: str, instance: str) -> str:
    try:
        return secretbox.aad_for(tenant_id, provider, instance)
    except secretbox.SecretBoxError:
        raise ServiceError(Kind.INVALID, reasons.INSTANCE_INVALID, _INVALID_INSTANCE) from None


def _keyring(llm: LlmSettings) -> tuple[str, dict[str, bytes]]:
    try:
        return secretbox.keyring_from_settings(llm)
    except secretbox.SecretBoxError:
        raise ServiceError(Kind.UNAVAILABLE, reasons.KEY_STORE_UNAVAILABLE, _UNUSABLE_STORE) from None


def seal_key(llm: LlmSettings, tenant_id: str, provider: str, instance: str, plaintext: str) -> str:
    """Encrypt a provider key into an envelope bound to its owner row. Never returns or logs the plaintext."""
    aad = _aad(tenant_id, provider, instance)
    kid, keys = _keyring(llm)
    try:
        return secretbox.seal(keys[kid], kid, plaintext, aad)
    except secretbox.SecretBoxError:
        raise ServiceError(Kind.UNAVAILABLE, reasons.KEY_STORE_UNAVAILABLE, _UNUSABLE_STORE) from None


def open_key(llm: LlmSettings, tenant_id: str, provider: str, instance: str, envelope: str) -> str:
    """Decrypt an envelope for exactly this owner row; a copied or tampered envelope raises ``key_unreadable``."""
    aad = _aad(tenant_id, provider, instance)
    _, keys = _keyring(llm)
    try:
        return secretbox.open_(keys, envelope, aad)
    except secretbox.SecretBoxError:
        raise ServiceError(Kind.UNAVAILABLE, reasons.KEY_UNREADABLE, _UNREADABLE) from None


def _loads(text: str | None) -> dict:
    try:
        value = json.loads(text or "{}")
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}


def get_credential(llm: LlmSettings, tenant_id: str, ref: ModelRef, model_type: str | None = None) -> ModelCredential | None:
    """The opened credential of one model, or None when this tenant has no such model on that provider instance."""
    try:
        provider = resolve_provider(ref.provider).name
    except UnknownProvider:
        return None
    query = (
        TenantLLM.select(TenantLLM.model_type, TenantLLM.api_key, TenantLLM.api_base, TenantLLM.max_tokens, TenantModelInstance.extra)
        .join(TenantModelProvider, on=(TenantModelProvider.tenant_id == TenantLLM.tenant_id) & (TenantModelProvider.provider_name == TenantLLM.llm_factory))
        .join(TenantModelInstance, on=TenantModelInstance.provider_id == TenantModelProvider.id)
        .join(TenantModel, on=(TenantModel.instance_id == TenantModelInstance.id) & (TenantModel.model_name == TenantLLM.llm_name))
        .where(
            TenantLLM.tenant_id == tenant_id,
            TenantLLM.llm_factory == provider,
            TenantLLM.llm_name == ref.model,
            TenantLLM.status == _ACTIVE,
            TenantModelInstance.instance_name == ref.instance,
        )
    )
    if model_type is not None:
        query = query.where(TenantLLM.model_type == model_type)
    with DB.connection_context():
        row = query.dicts().first()
    if row is None:
        return None
    envelope = row["api_key"] or ""
    return ModelCredential(
        provider=provider,
        instance=ref.instance,
        model=ref.model,
        model_type=row["model_type"] or "",
        api_key=open_key(llm, tenant_id, provider, ref.instance, envelope) if envelope else None,
        api_base=row["api_base"] or None,
        api_version=_loads(row["extra"]).get("api_version") or None,
        max_tokens=int(row["max_tokens"] or 0),
    )


_ADD_USED_TOKENS = "UPDATE tenant_llm SET used_tokens = LEAST(used_tokens + %s, 2147483647) WHERE tenant_id = %s AND llm_factory = %s AND llm_name = %s"


def add_used_tokens(tenant_id: str, provider: str, model: str, tokens: int) -> None:
    """Add to the usage counter with one atomic statement, capped at the 32-bit column limit."""
    if not isinstance(tokens, int) or tokens <= 0:
        return
    with DB.connection_context():
        DB.execute_sql(_ADD_USED_TOKENS, (min(tokens, USED_TOKENS_CAP), tenant_id, provider, model))


def _host(value: str) -> str | None:
    text = value.strip()
    if not text:
        return None
    host = urlsplit(text if "://" in text else f"//{text}").hostname
    return host.lower() if host else None


def internal_hosts(settings: Settings) -> frozenset[str]:
    """Host names of the backing services, lower-cased, for the URL guard's ``deny_hosts`` (SSRF)."""
    candidates = [settings.mysql.host, settings.redis.host, settings.minio.host, *settings.es.hosts.split(",")]
    return frozenset(h for h in (_host(c) for c in candidates) if h)
