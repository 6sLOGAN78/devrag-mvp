"""Composite model ids ``model@instance@provider`` (LLM-15, plan 03-09; T-03-09-07)."""

from __future__ import annotations

import dataclasses

import pytest
from common.model_ref import (
    DEFAULT_INSTANCE,
    MAX_COMPOSITE_LENGTH,
    InvalidModelRef,
    ModelRef,
    format_model_ref,
    parse_model_ref,
)

pytestmark = pytest.mark.unit


def test_two_part_form_is_the_default_instance():
    ref = parse_model_ref("baai/bge-m3@OpenRouter")
    assert (ref.model, ref.instance, ref.provider) == ("baai/bge-m3", DEFAULT_INSTANCE, "OpenRouter")
    assert DEFAULT_INSTANCE == "default"


def test_three_part_form_names_the_instance():
    ref = parse_model_ref("m@prod@Azure-OpenAI")
    assert (ref.model, ref.instance, ref.provider) == ("m", "prod", "Azure-OpenAI")
    assert ref.composite == "m@prod@Azure-OpenAI"


def test_explicit_default_instance_normalises_to_the_two_part_form():
    ref = parse_model_ref("m@default@OpenAI")
    assert ref.instance == "default"
    assert ref.composite == "m@OpenAI"


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "m",
        "a@b@c@d",
        "@OpenAI",
        "m@",
        "m@@OpenAI",
        "m@prod@",
        "@prod@OpenAI",
        "m @OpenAI",
        "m@Open AI",
        "m\t@OpenAI",
        "m@OpenAI\n",
        "m\x00@OpenAI",
        "m\x7f@OpenAI",
        "m@pro d@OpenAI",
        "x" * 129 + "@OpenAI",
        "m@" + "x" * 129,
    ],
)
def test_parse_rejects_malformed_values(bad):
    with pytest.raises(InvalidModelRef):
        parse_model_ref(bad)


@pytest.mark.parametrize("bad", [None, 3, b"m@OpenAI", ["m", "OpenAI"]])
def test_parse_rejects_non_strings(bad):
    with pytest.raises(InvalidModelRef):
        parse_model_ref(bad)  # type: ignore[arg-type]


def test_format_default_instance_is_two_part():
    assert format_model_ref("m", "OpenAI") == "m@OpenAI"
    assert format_model_ref("m", "OpenAI", DEFAULT_INSTANCE) == "m@OpenAI"
    assert format_model_ref("m", "OpenAI", "prod") == "m@prod@OpenAI"


@pytest.mark.parametrize("name", ["gpt-4o", "baai/bge-m3", "qwen3:8b", "org/model:latest-q4", "a.b_c-d"])
def test_round_trip_keeps_slash_and_colon(name):
    for instance in (DEFAULT_INSTANCE, "prod"):
        ref = parse_model_ref(format_model_ref(name, "OpenAI", instance))
        assert ref == ModelRef(name, instance, "OpenAI")


@pytest.mark.parametrize(
    ("model", "provider", "instance"),
    [
        ("a@b", "OpenAI", "default"),
        ("m", "Open@AI", "default"),
        ("m", "OpenAI", "pr@od"),
        ("", "OpenAI", "default"),
        ("m", "", "default"),
        ("m", "OpenAI", ""),
        ("m n", "OpenAI", "default"),
        ("m", "Open\nAI", "default"),
    ],
)
def test_format_rejects_unsafe_or_empty_parts(model, provider, instance):
    with pytest.raises(InvalidModelRef):
        format_model_ref(model, provider, instance)


def test_two_part_id_of_exactly_128_characters_is_accepted():
    model = "m" * (MAX_COMPOSITE_LENGTH - len("@OpenAI"))
    composite = format_model_ref(model, "OpenAI")
    assert len(composite) == 128
    assert parse_model_ref(composite).model == model


def test_two_part_id_of_129_characters_is_rejected_by_both_functions():
    model = "m" * (MAX_COMPOSITE_LENGTH - len("@OpenAI") + 1)
    with pytest.raises(InvalidModelRef):
        format_model_ref(model, "OpenAI")
    with pytest.raises(InvalidModelRef):
        parse_model_ref(model + "@OpenAI")


def test_three_part_id_over_the_bound_is_rejected_even_when_every_part_is_valid():
    model, instance, provider = "m" * 100, "i" * 20, "p" * 20
    assert max(len(model), len(instance), len(provider)) <= 128
    assert len(f"{model}@{instance}@{provider}") > MAX_COMPOSITE_LENGTH
    with pytest.raises(InvalidModelRef):
        format_model_ref(model, provider, instance)
    with pytest.raises(InvalidModelRef):
        parse_model_ref(f"{model}@{instance}@{provider}")


def test_the_default_instance_does_not_count_towards_the_length():
    model = "m" * (MAX_COMPOSITE_LENGTH - len("@OpenAI"))
    assert format_model_ref(model, "OpenAI", DEFAULT_INSTANCE) == f"{model}@OpenAI"
    with pytest.raises(InvalidModelRef):
        format_model_ref(model, "OpenAI", "prod")


def test_model_ref_is_frozen_and_errors_are_fixed_messages():
    ref = ModelRef("m", "default", "OpenAI")
    with pytest.raises(dataclasses.FrozenInstanceError):
        ref.model = "x"  # type: ignore[misc]
    with pytest.raises(InvalidModelRef) as err:
        parse_model_ref("secret-looking value with spaces@x")
    assert "secret-looking" not in str(err.value)
    assert issubclass(InvalidModelRef, ValueError)
