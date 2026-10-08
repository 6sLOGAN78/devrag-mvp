"""Provider registry and model metadata (plan 03-05, LLM-02, LLM-22, D-15)."""
from __future__ import annotations

import pytest
from rag.llm import (
    FACTORY_DEFAULT_BASE_URL,
    LITELLM_PROVIDER_PREFIX,
    PROVIDER_SPECS,
    Provider,
    UnknownProvider,
    resolve_provider,
    validate_base_url_shape,
)
from rag.llm.model_meta import REASONING_MODEL, ModelMeta, lookup

pytestmark = pytest.mark.unit

EXPECTED = [
    # name, slug, prefix, default base url, key, base_url, requires_api_version, ollama_style
    ("OpenAI", "openai", "openai/", "https://api.openai.com/v1", "required", "default", False, False),
    ("Azure-OpenAI", "azure-openai", "azure/", None, "required", "required", True, False),
    ("Ollama", "ollama", "ollama_chat/", None, "none", "required", False, True),
    ("OpenRouter", "openrouter", "openai/", "https://openrouter.ai/api/v1", "required", "default", False, False),
    ("OpenAI-API-Compatible", "openai-compatible", "openai/", None, "optional", "required", False, False),
]


def test_five_providers_in_settings_page_order():
    assert [s.name for s in PROVIDER_SPECS] == [row[0] for row in EXPECTED]
    assert [p.value for p in Provider] == [row[0] for row in EXPECTED]


@pytest.mark.parametrize("name,slug,prefix,default,key,base,api_version,ollama", EXPECTED)
def test_spec_fields(name, slug, prefix, default, key, base, api_version, ollama):
    spec = resolve_provider(name)
    assert (spec.name, spec.slug, spec.litellm_prefix, spec.default_base_url) == (name, slug, prefix, default)
    assert (spec.key, spec.base_url, spec.requires_api_version, spec.ollama_style) == (key, base, api_version, ollama)
    assert LITELLM_PROVIDER_PREFIX[Provider(name)] == prefix
    assert FACTORY_DEFAULT_BASE_URL.get(Provider(name)) == default


def test_spec_is_frozen():
    with pytest.raises(AttributeError):
        resolve_provider("OpenAI").slug = "x"  # type: ignore[misc]


@pytest.mark.parametrize("variant", ["OpenRouter", "openrouter", "OPENROUTER", " openrouter "])
def test_resolve_is_case_insensitive_over_name_and_slug(variant):
    assert resolve_provider(variant) is resolve_provider("OpenRouter")


def test_resolve_by_slug_and_name_agree():
    for spec in PROVIDER_SPECS:
        assert resolve_provider(spec.slug) is spec
        assert resolve_provider(spec.name.lower()) is spec


@pytest.mark.parametrize("bad", ["", "anthropic", "openai/", "Open AI", "azure"])
def test_unknown_provider_raises(bad):
    with pytest.raises(UnknownProvider):
        resolve_provider(bad)
    assert issubclass(UnknownProvider, ValueError)


def test_ollama_base_url_must_not_end_in_v1():
    spec = resolve_provider("Ollama")
    assert validate_base_url_shape(spec, "http://host:11434/v1") is not None
    assert validate_base_url_shape(spec, "http://host:11434/v1/") is not None
    assert validate_base_url_shape(spec, "http://host:11434") is None


def test_required_base_url_is_enforced_and_defaults_are_not():
    assert validate_base_url_shape(resolve_provider("Azure-OpenAI"), "") is not None
    assert validate_base_url_shape(resolve_provider("OpenAI-API-Compatible"), None) is not None
    assert validate_base_url_shape(resolve_provider("OpenAI"), "") is None
    assert validate_base_url_shape(resolve_provider("OpenRouter"), None) is None
    assert validate_base_url_shape(resolve_provider("OpenAI-API-Compatible"), "https://gw.example.test/v1") is None


def test_seeded_metadata():
    llama = lookup("OpenRouter", "meta-llama/llama-3.1-8b-instruct")
    assert isinstance(llama, ModelMeta) and llama.max_tokens == 131072
    assert (llama.input_price, llama.output_price) == (0.05, 0.08)
    assert lookup("OpenRouter", "baai/bge-m3").max_tokens == 8194
    assert lookup("OpenRouter", "openai/text-embedding-3-small").max_tokens == 8192
    assert lookup("OpenAI", "gpt-4o-mini").max_tokens > 8192
    assert lookup("OpenRouter", "mistralai/mistral-nemo").max_tokens > 0


def test_unknown_model_gets_the_conservative_default():
    meta = lookup("OpenAI-API-Compatible", "some-local-model")
    assert (meta.max_tokens, meta.max_completion_tokens, meta.is_vision, meta.input_price, meta.output_price) == (8192, 4096, False, 0.0, 0.0)


@pytest.mark.parametrize("name", ["o1", "o1-mini", "o3-mini", "o4-mini", "openai/o3", "azure/o1-preview"])
def test_reasoning_pattern_matches_the_o_families(name):
    assert REASONING_MODEL.match(name)


@pytest.mark.parametrize("name", ["gpt-4o", "o10", "oss-model", "llama-o1x", "gpt-o3"])
def test_reasoning_pattern_does_not_overmatch(name):
    assert not REASONING_MODEL.match(name)
