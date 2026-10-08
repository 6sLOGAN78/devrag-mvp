"""Pure request policy of the provider service (plan 03-10; D-15, D-16, UI-SPEC choice 8, T-03-10-02, T-03-10-10).

``check_request`` is a pure function over the provider spec, the request and the existing instance: no database, no network.
The save-time test flow runs against the real MySQL, Valkey and the loopback provider in test/integration/test_provider_service.py.
"""

from __future__ import annotations

import pytest

from api.db.services.provider_service import ModelRequest, SaveRequest, check_model_names, check_request
from api.db.services.service_errors import Kind, ServiceError
from api.db.services.tenant_model_service import InstanceInfo
from api.utils import reasons
from common.model_ref import format_model_ref
from rag.llm import resolve_provider

pytestmark = pytest.mark.unit

KEY = "-".join(("sk", "fake", "unit", "0001"))
NEW_KEY = "-".join(("sk", "fake", "unit", "0002"))
CHAT = ModelRequest("chat-a", "chat")
EMBED = ModelRequest("embed-a", "embedding")


def request(provider: str = "OpenAI", **overrides) -> SaveRequest:
    fields = {"tenant_id": "t" * 32, "provider": provider, "instance": "default", "api_key": KEY, "base_url": None, "api_version": None, "models": (CHAT,)}
    fields.update(overrides)
    return SaveRequest(**fields)


def check(provider: str = "OpenAI", existing: InstanceInfo | None = None, **overrides) -> None:
    check_request(resolve_provider(provider), request(provider, **overrides), existing)


def refused(reason: str, provider: str = "OpenAI", existing: InstanceInfo | None = None, **overrides) -> None:
    with pytest.raises(ServiceError) as caught:
        check(provider, existing, **overrides)
    assert caught.value.reason == reason
    assert caught.value.kind == Kind.INVALID
    assert KEY not in caught.value.message and NEW_KEY not in caught.value.message


def instance(provider: str = "OpenAI", *, has_key: bool = True, last4: str = "0001", base: str | None = None, version: str | None = None) -> InstanceInfo:
    return InstanceInfo(provider, "default", True, last4, has_key, base, version)


def test_the_request_does_not_print_its_key() -> None:
    assert KEY not in repr(request()) and KEY not in str(request())


def test_openai_without_a_key_is_refused() -> None:
    refused(reasons.KEY_REQUIRED, api_key=None)
    refused(reasons.KEY_REQUIRED, api_key="   ")


def test_openai_with_a_key_is_accepted() -> None:
    check()


def test_a_keyed_instance_may_be_saved_again_without_a_key() -> None:
    check(existing=instance(), api_key=None)


def test_azure_needs_a_base_url_and_an_api_version() -> None:
    refused(reasons.BASE_URL_REQUIRED, "Azure-OpenAI", api_version="2024-06-01")
    refused(reasons.API_VERSION_REQUIRED, "Azure-OpenAI", base_url="https://res.example.test")
    check("Azure-OpenAI", base_url="https://res.example.test", api_version="2024-06-01")


def test_openai_compatible_does_not_need_a_key() -> None:
    check("OpenAI-API-Compatible", api_key=None, base_url="http://models.example.test/v1")


def test_openai_compatible_needs_a_base_url() -> None:
    refused(reasons.BASE_URL_REQUIRED, "OpenAI-API-Compatible", api_key=None)


def test_ollama_base_url_must_not_end_in_v1() -> None:
    refused(reasons.BASE_URL_INVALID, "Ollama", api_key=None, base_url="http://ollama.example.test:11434/v1")
    refused(reasons.BASE_URL_INVALID, "Ollama", api_key=None, base_url="http://ollama.example.test:11434/v1/")
    check("Ollama", api_key=None, base_url="http://ollama.example.test:11434")


@pytest.mark.parametrize(
    "models",
    [
        (),
        (CHAT, EMBED, ModelRequest("chat-b", "chat")),
        (CHAT, ModelRequest("chat-b", "chat")),
        (ModelRequest("has space", "chat"),),
        (ModelRequest("has@sign", "chat"),),
        (ModelRequest("x" * 129, "chat"),),
        (ModelRequest("", "chat"),),
        (ModelRequest("chat-a", "rerank"),),
    ],
)
def test_the_model_list_is_bounded(models: tuple[ModelRequest, ...]) -> None:
    refused(reasons.MODELS_INVALID, models=models)


def test_one_chat_and_one_embedding_model_are_accepted() -> None:
    check(models=(CHAT, EMBED))


def test_a_changed_base_url_needs_a_new_key_on_a_keyed_instance() -> None:
    existing = instance(base="https://models.example.test/v1")
    refused(reasons.KEY_REQUIRED_FOR_NEW_ADDRESS, "OpenAI-API-Compatible", existing, api_key=None, base_url="https://other.example.test/v1")
    check("OpenAI-API-Compatible", existing, api_key=NEW_KEY, base_url="https://other.example.test/v1")


def test_a_changed_api_version_needs_a_new_key_on_a_keyed_instance() -> None:
    existing = instance("Azure-OpenAI", base="https://res.example.test", version="2024-06-01")
    refused(reasons.KEY_REQUIRED_FOR_NEW_ADDRESS, "Azure-OpenAI", existing, api_key=None, base_url="https://res.example.test", api_version="2025-01-01")
    check("Azure-OpenAI", existing, api_key=None, base_url="https://res.example.test", api_version="2024-06-01")


def test_an_unchanged_address_is_accepted_without_a_key_even_with_a_trailing_slash() -> None:
    existing = instance("OpenAI-API-Compatible", base="https://models.example.test/v1")
    check("OpenAI-API-Compatible", existing, api_key=None, base_url="https://models.example.test/v1/")


def test_the_default_address_equals_no_address() -> None:
    existing = instance("OpenAI", base=None)
    check("OpenAI", existing, api_key=None, base_url="https://api.openai.com/v1")


def test_a_keyless_instance_may_change_its_address_without_a_key() -> None:
    existing = instance("Ollama", has_key=False, last4="", base="http://old.example.test:11434")
    check("Ollama", existing, api_key=None, base_url="http://new.example.test:11434")


def test_a_short_key_leaves_an_empty_last4_but_still_counts_as_a_key() -> None:
    short = instance("OpenAI-API-Compatible", has_key=True, last4="", base="https://models.example.test/v1", version=None)
    refused(reasons.KEY_REQUIRED_FOR_NEW_ADDRESS, "OpenAI-API-Compatible", short, api_key=None, base_url="https://other.example.test/v1")
    short_azure = instance("Azure-OpenAI", has_key=True, last4="", base="https://res.example.test", version="2024-06-01")
    refused(reasons.KEY_REQUIRED_FOR_NEW_ADDRESS, "Azure-OpenAI", short_azure, api_key=None, base_url="https://res.example.test", api_version="2025-01-01")
    check("OpenAI-API-Compatible", short, api_key=NEW_KEY, base_url="https://other.example.test/v1")


def _name_for_composite_length(spec_name: str, total: int) -> str:
    return "m" * (total - len(f"@{spec_name}"))


def test_the_composite_id_is_bounded_at_128_characters() -> None:
    spec = resolve_provider("OpenAI-API-Compatible")
    exact = _name_for_composite_length(spec.name, 128)
    assert len(format_model_ref(exact, spec.name, "default")) == 128
    check("OpenAI-API-Compatible", api_key=None, base_url="https://models.example.test/v1", models=(ModelRequest(exact, "chat"),))
    over = _name_for_composite_length(spec.name, 129)
    assert len(over) <= 128  # valid on its own
    refused(reasons.MODELS_INVALID, "OpenAI-API-Compatible", api_key=None, base_url="https://models.example.test/v1", models=(ModelRequest(over, "chat"),))


def test_a_long_instance_name_counts_toward_the_composite_bound() -> None:
    spec = resolve_provider("OpenAI")
    with pytest.raises(ServiceError) as caught:
        check_model_names(spec, "i" * 100, (ModelRequest("m" * 40, "chat"),))
    assert caught.value.reason == reasons.MODELS_INVALID


def test_check_model_names_accepts_a_short_composite() -> None:
    check_model_names(resolve_provider("OpenAI"), "default", (CHAT, EMBED))
