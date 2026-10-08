"""Input policy of the model defaults service (plan 03-13): everything here is decided before any database access."""
from __future__ import annotations

import pytest

from api.db.services import model_defaults_service
from api.db.services.service_errors import Kind, ServiceError
from api.db.services.tenant_model_service import ModelInfo

pytestmark = pytest.mark.unit

TENANT = "0" * 32


def _error(**changes: str | None) -> ServiceError:
    with pytest.raises(ServiceError) as caught:
        model_defaults_service.update_defaults(TENANT, changes)
    return caught.value


def test_an_empty_change_set_is_invalid() -> None:
    err = _error()
    assert err.kind is Kind.INVALID and err.reason == "models_invalid"


def test_an_unknown_slot_is_invalid() -> None:
    err = _error(rerank="x@y")
    assert err.kind is Kind.INVALID and err.reason == "models_invalid"


@pytest.mark.parametrize("value", ["", "plain", "a@b@c@d", "has space@openai", "@openai", "model@", "x" * 129 + "@openai", "m@" + "p" * 200])
def test_a_malformed_or_over_long_composite_id_is_model_unavailable_not_a_database_error(value: str) -> None:
    err = _error(chat=value)
    assert err.kind is Kind.INVALID and err.reason == "model_unavailable"
    assert not value or value not in err.message, "the input is never echoed"


def test_a_129_character_composite_is_refused_before_the_database() -> None:
    value = "x" * (129 - len("@OpenAI-API-Compatible")) + "@OpenAI-API-Compatible"
    assert len(value) == 129
    assert _error(embedding=value).reason == "model_unavailable"


def test_an_unknown_type_filter_is_invalid() -> None:
    with pytest.raises(ServiceError) as caught:
        model_defaults_service.list_model_dtos(TENANT, "image")
    assert caught.value.reason == "models_invalid"


def test_the_model_dto_lists_exactly_the_documented_keys() -> None:
    info = ModelInfo(id="i", model="m", provider="OpenAI", instance="default", model_type="chat", dimension=None, max_tokens=8, used_tokens=3, composite="m@OpenAI")
    assert model_defaults_service.model_dto(info) == {
        "id": "m@OpenAI",
        "name": "m",
        "provider": "OpenAI",
        "instance": "default",
        "type": "chat",
        "dimension": None,
        "max_tokens": 8,
        "used_tokens": 3,
    }
