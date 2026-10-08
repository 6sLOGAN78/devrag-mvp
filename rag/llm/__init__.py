"""Model provider registry (plan 03-05, LLM-02, D-15).

One source of truth for the five supported providers: the display name used in the settings page and stored on a provider
row, a URL-safe slug used in routes, the LiteLLM model prefix, the documented default base URL, and what a workspace must
supply (key, base URL, API version). Routes, services and drivers read this table; none of them hard-codes a provider.

Nothing here imports litellm or any SDK: importing the registry must stay cheap.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal
from urllib.parse import urlsplit


class Provider(StrEnum):
    OPENAI = "OpenAI"
    AZURE_OPENAI = "Azure-OpenAI"
    OLLAMA = "Ollama"
    OPENROUTER = "OpenRouter"
    OPENAI_COMPATIBLE = "OpenAI-API-Compatible"


class UnknownProvider(ValueError):
    """The name or slug does not belong to a supported provider."""


@dataclass(frozen=True)
class ProviderSpec:
    name: str
    slug: str
    litellm_prefix: str
    default_base_url: str | None
    key: Literal["required", "optional", "none"]
    base_url: Literal["default", "required"]
    requires_api_version: bool
    ollama_style: bool


# Settings page order (D-15).
PROVIDER_SPECS: tuple[ProviderSpec, ...] = (
    ProviderSpec(Provider.OPENAI, "openai", "openai/", "https://api.openai.com/v1", "required", "default", False, False),
    ProviderSpec(Provider.AZURE_OPENAI, "azure-openai", "azure/", None, "required", "required", True, False),
    ProviderSpec(Provider.OLLAMA, "ollama", "ollama_chat/", None, "none", "required", False, True),
    ProviderSpec(Provider.OPENROUTER, "openrouter", "openai/", "https://openrouter.ai/api/v1", "required", "default", False, False),
    ProviderSpec(Provider.OPENAI_COMPATIBLE, "openai-compatible", "openai/", None, "optional", "required", False, False),
)

# Names kept after the reference implementation (rag/llm/__init__.py) so docs and code read alike.
FACTORY_DEFAULT_BASE_URL: dict[Provider, str] = {Provider(s.name): s.default_base_url for s in PROVIDER_SPECS if s.default_base_url}
LITELLM_PROVIDER_PREFIX: dict[Provider, str] = {Provider(s.name): s.litellm_prefix for s in PROVIDER_SPECS}

_INDEX: dict[str, ProviderSpec] = {}
for _spec in PROVIDER_SPECS:
    _INDEX[_spec.name.lower()] = _spec
    _INDEX[_spec.slug] = _spec


def resolve_provider(value: str) -> ProviderSpec:
    """Case-insensitive lookup over the display name and the slug."""
    found = _INDEX.get(value.strip().lower()) if isinstance(value, str) else None
    if found is None:
        raise UnknownProvider("unknown provider")
    return found


def validate_base_url_shape(spec: ProviderSpec, url: str | None) -> str | None:
    """Shape check only (the SSRF guard is common.net.url_guard). Returns an error code or ``None``.

    ``base_url_required``: the provider has no default and none was given.
    ``ollama_base_url_has_v1``: Ollama's native API lives at ``/api`` and a ``/v1`` suffix would break it (LLM-05).
    """
    text = (url or "").strip()
    if not text:
        return "base_url_required" if spec.base_url == "required" else None
    if spec.ollama_style and urlsplit(text).path.rstrip("/").endswith("/v1"):
        return "ollama_base_url_has_v1"
    return None
