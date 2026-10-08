"""Pure helpers and argument checks of the model bundle (plan 03-11; LLM-14, LLM-19, LLM-21, T-03-11-02).

No database row is read and no request is made here: usage arithmetic, the ModelException -> ServiceError mapping, and the
checks the constructor makes before it touches any storage. The flows against the real MySQL and the loopback provider live in
test/integration/test_llm_bundle_flow.py.
"""

from __future__ import annotations

import logging

import pytest

from api.db.services.llm_service import LLMBundle, bundle_error, merge_usage, split_usage
from api.db.services.service_errors import Kind, ServiceError
from api.utils import reasons
from common.log_utils import RedactingFilter
from rag.llm.errors import LLMErrorCode, ModelException
from rag.llm.stream import Usage

pytestmark = pytest.mark.unit

KEY = "-".join(("sk", "fake", "unit", "0011"))


def test_split_usage_returns_the_three_counts():
    assert split_usage(Usage(3, 4, 7)) == (3, 4, 7)
    assert split_usage(None) == (0, 0, 0)


def test_merge_usage_adds_every_count():
    merged = merge_usage(Usage(3, 4, 7), Usage(10, 20, 30))
    assert (merged.prompt_tokens, merged.completion_tokens, merged.total_tokens) == (13, 24, 37)
    assert merged.estimated is False


def test_merge_usage_is_estimated_only_when_every_part_was_estimated():
    assert merge_usage(Usage(1, 1, 2, True), Usage(2, 2, 4, True)).estimated is True
    assert merge_usage(Usage(1, 1, 2, True), Usage(2, 2, 4, False)).estimated is False
    assert merge_usage(Usage(1, 1, 2, False), Usage(2, 2, 4, True)).estimated is False


def test_merge_usage_treats_none_as_nothing():
    only = Usage(5, 6, 11, True)
    assert merge_usage(None, only) == only
    assert merge_usage(only, None) == only
    assert merge_usage(None, None) == Usage(0, 0, 0, False)


@pytest.mark.parametrize(
    "code",
    [
        LLMErrorCode.ERROR_AUTHENTICATION,
        LLMErrorCode.ERROR_INVALID_REQUEST,
        LLMErrorCode.ERROR_QUOTA,
        LLMErrorCode.ERROR_CONTENT_FILTER,
        LLMErrorCode.ERROR_MODEL,
    ],
)
def test_refusals_map_to_invalid_provider_refused_with_the_safe_message(code):
    error = bundle_error(ModelException(code, message="Incorrect API key provided."))
    assert isinstance(error, ServiceError)
    assert (error.kind, error.reason) == (Kind.INVALID, reasons.PROVIDER_REFUSED)
    assert error.message == "Incorrect API key provided."


def test_a_refusal_without_provider_text_gets_a_fixed_message():
    error = bundle_error(ModelException(LLMErrorCode.ERROR_AUTHENTICATION))
    assert error.reason == reasons.PROVIDER_REFUSED and error.message


def test_rate_limit_maps_to_unavailable_and_keeps_retry_after():
    error = bundle_error(ModelException(LLMErrorCode.ERROR_RATE_LIMIT, retryable=True, provider_status=429, retry_after=0.0))
    assert (error.kind, error.reason) == (Kind.UNAVAILABLE, reasons.PROVIDER_RATE_LIMITED)
    assert error.retry_after == 0.0


def test_retries_ended_by_a_rate_limit_still_read_as_a_rate_limit():
    error = bundle_error(ModelException(LLMErrorCode.ERROR_MAX_RETRIES, provider_status=429, retry_after=2.0))
    assert (error.kind, error.reason) == (Kind.UNAVAILABLE, reasons.PROVIDER_RATE_LIMITED)
    assert error.retry_after == 2.0


def test_timeouts_map_to_timeout():
    for source in (ModelException(LLMErrorCode.ERROR_TIMEOUT), ModelException(LLMErrorCode.ERROR_MAX_RETRIES, provider_status=None)):
        error = bundle_error(source)
        assert (error.kind, error.reason) == (Kind.TIMEOUT, reasons.PROVIDER_TIMEOUT)


@pytest.mark.parametrize(
    "code",
    [LLMErrorCode.ERROR_SERVER, LLMErrorCode.ERROR_CONNECTION, LLMErrorCode.ERROR_GENERIC, LLMErrorCode.ERROR_MAX_ROUNDS],
)
def test_everything_else_maps_to_bad_gateway(code):
    error = bundle_error(ModelException(code, message="the upstream said something"))
    assert (error.kind, error.reason) == (Kind.BAD_GATEWAY, reasons.PROVIDER_UNREACHABLE)
    assert "upstream" not in error.message, "provider text is shown only for a refusal"


def test_a_server_error_that_is_a_503_reads_as_a_rate_limit_like_the_provider_service():
    error = bundle_error(ModelException(LLMErrorCode.ERROR_SERVER, provider_status=503))
    assert error.reason == reasons.PROVIDER_RATE_LIMITED


def test_every_error_code_is_covered_by_the_mapping():
    for code in LLMErrorCode:
        error = bundle_error(ModelException(code))
        assert isinstance(error, ServiceError) and error.reason


def test_the_error_carries_no_provider_exception_text_or_cause():
    source = ModelException(LLMErrorCode.ERROR_AUTHENTICATION, message=f"bad key {KEY}")
    error = bundle_error(source, lambda text: text.replace(KEY, "***"))
    assert KEY not in error.message and KEY not in str(error) and KEY not in repr(error)
    assert error.__cause__ is None


def test_a_scrubber_masks_a_key_the_redactor_cannot_recognise():
    odd_key = "plainly-not-a-key-shape"
    source = ModelException(LLMErrorCode.ERROR_AUTHENTICATION, message=f"bad key {odd_key} given")
    unscrubbed = bundle_error(source)
    scrubbed = bundle_error(source, lambda text: text.replace(odd_key, "***"))
    assert odd_key in unscrubbed.message
    assert odd_key not in scrubbed.message and "***" in scrubbed.message


def test_an_unsupported_model_type_is_a_programming_error():
    with pytest.raises(ValueError):
        LLMBundle("t" * 32, "gpt-4o-mini@OpenAI", "image")


@pytest.mark.parametrize("model_id", ["", "plain", "a@b@c@d", "gpt @OpenAI", "x" * 200 + "@OpenAI"])
def test_a_malformed_model_id_is_model_unavailable_before_any_lookup(model_id):
    with pytest.raises(ServiceError) as caught:
        LLMBundle("t" * 32, model_id, "chat")
    assert (caught.value.kind, caught.value.reason) == (Kind.NOT_FOUND, reasons.MODEL_UNAVAILABLE)


def test_usage_log_fields_survive_the_redacting_filter():
    """The logging filter masks any field whose name contains ``token``; the usage fields must not use that word."""
    from api.db.services import llm_service

    record = logging.LogRecord("x", logging.INFO, __file__, 1, "llm usage", None, None)
    for name, value in llm_service.usage_log_fields("tenant-1", "OpenAI", "m", Usage(3, 4, 7, False)).items():
        setattr(record, name, value)
    RedactingFilter().filter(record)
    assert record.usage_in == 3 and record.usage_out == 4 and record.usage_total == 7
    assert record.provider == "OpenAI" and record.model == "m" and record.estimated is False
    assert record.tenant == "tenant-1"
