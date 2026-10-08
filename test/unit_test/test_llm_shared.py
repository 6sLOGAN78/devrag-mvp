"""Shared error, retry and stream modules (plan 03-05, LLM-19, LLM-20). Pure: no server, no SDK."""
from __future__ import annotations

import json

import pytest
from rag.llm.errors import LLMErrorCode, ModelException
from rag.llm.retry import arun_with_retries, retry_delay, run_with_retries
from rag.llm.stream import StreamSanitizer, Usage

pytestmark = pytest.mark.unit

FAKE_KEY = "-".join(["sk", "fakesharedsecret", "0123456789abcdef"])


def _body(message: str) -> str:
    return json.dumps({"error": {"message": message, "type": "x"}})


# --- ModelException ---------------------------------------------------------------------------------------------
def test_error_codes_exist():
    names = {c.name for c in LLMErrorCode}
    assert {
        "ERROR_RATE_LIMIT", "ERROR_AUTHENTICATION", "ERROR_INVALID_REQUEST", "ERROR_SERVER", "ERROR_TIMEOUT", "ERROR_CONNECTION",
        "ERROR_MODEL", "ERROR_MAX_ROUNDS", "ERROR_CONTENT_FILTER", "ERROR_QUOTA", "ERROR_MAX_RETRIES", "ERROR_GENERIC",
    } <= names


def test_model_exception_keeps_its_fields():
    exc = ModelException(LLMErrorCode.ERROR_RATE_LIMIT, retryable=True, provider_status=429, retry_after=1.5, body=_body("slow down"))
    assert (exc.code, exc.retryable, exc.provider_status, exc.retry_after) == (LLMErrorCode.ERROR_RATE_LIMIT, True, 429, 1.5)
    assert exc.safe_message == "slow down"


def test_model_exception_defaults_are_not_retryable():
    exc = ModelException(LLMErrorCode.ERROR_AUTHENTICATION)
    assert (exc.retryable, exc.provider_status, exc.retry_after, exc.safe_message) == (False, None, None, "")


def test_str_is_only_the_code():
    exc = ModelException(LLMErrorCode.ERROR_INVALID_REQUEST, body=_body(f"bad key {FAKE_KEY}"))
    assert str(exc) == LLMErrorCode.ERROR_INVALID_REQUEST.value
    assert FAKE_KEY not in str(exc) and FAKE_KEY not in repr(exc)


def test_safe_message_is_truncated_to_200():
    exc = ModelException(LLMErrorCode.ERROR_INVALID_REQUEST, body=_body("x" * 500))
    assert exc.safe_message == "x" * 200


def test_safe_message_redacts_a_key_and_keeps_no_fragment_across_the_cut():
    text = "a" * 190 + FAKE_KEY
    exc = ModelException(LLMErrorCode.ERROR_INVALID_REQUEST, body=_body(text))
    assert FAKE_KEY not in exc.safe_message and "sk-fake" not in exc.safe_message
    assert len(exc.safe_message) <= 200
    plain = ModelException(LLMErrorCode.ERROR_INVALID_REQUEST, body=_body(f"Incorrect API key provided: {FAKE_KEY}."))
    assert "***" in plain.safe_message and FAKE_KEY not in plain.safe_message


@pytest.mark.parametrize("body", [None, "", "not json", "<html>nope</html>", "[1, 2]", '{"error": 5}', '{"error": {"message": 7}}', b"\xff\xfe"])
def test_safe_message_is_empty_when_the_body_is_not_a_usable_error(body):
    assert ModelException(LLMErrorCode.ERROR_SERVER, body=body).safe_message == ""


def test_safe_message_accepts_the_ollama_string_error_shape_and_bytes():
    assert ModelException(LLMErrorCode.ERROR_INVALID_REQUEST, body='{"error": "model not found"}').safe_message == "model not found"
    assert ModelException(LLMErrorCode.ERROR_INVALID_REQUEST, body=_body("as bytes").encode()).safe_message == "as bytes"


def test_message_argument_is_also_redacted_and_truncated():
    exc = ModelException(LLMErrorCode.ERROR_MAX_RETRIES, message=f"{FAKE_KEY} " + "y" * 400)
    assert FAKE_KEY not in exc.safe_message and len(exc.safe_message) <= 200


# --- retry_delay ------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("attempt,expected", [(0, 0.5), (1, 1.0), (2, 2.0), (3, 4.0), (4, 8.0), (5, 8.0), (30, 8.0)])
def test_delay_is_capped_exponential(attempt, expected):
    assert retry_delay(attempt, None, jitter=0.0) == expected


def test_delay_jitter_is_bounded():
    for _ in range(50):
        assert 1.0 <= retry_delay(1, None, jitter=0.25) <= 1.25


def test_delay_is_raised_to_retry_after_when_larger_and_not_lowered():
    assert retry_delay(0, 3.0, jitter=0.0) == 3.0
    assert retry_delay(3, 1.0, jitter=0.0) == 4.0
    assert retry_delay(0, 0.0, jitter=0.0) == 0.5


def test_a_hostile_retry_after_is_capped():
    assert retry_delay(0, 86400.0, jitter=0.0) <= 60.0


# --- run_with_retries / arun_with_retries -----------------------------------------------------------------------
def _retryable(code: LLMErrorCode = LLMErrorCode.ERROR_RATE_LIMIT, **kw) -> ModelException:
    return ModelException(code, retryable=True, provider_status=429, **kw)


class Script:
    """A callable that raises the scripted exceptions in order and then returns."""

    def __init__(self, *steps):
        self.steps = list(steps)
        self.calls = 0

    def __call__(self):
        self.calls += 1
        step = self.steps.pop(0) if self.steps else "ok"
        if isinstance(step, Exception):
            raise step
        return step

    async def acall(self):
        return self()


def test_sync_retries_a_retryable_error_then_succeeds():
    script, sleeps = Script(_retryable(), "fine"), []
    assert run_with_retries(script, max_retries=3, sleep=sleeps.append) == "fine"
    assert script.calls == 2 and len(sleeps) == 1


def test_sync_gives_up_after_max_retries_with_the_wrapped_code_and_message():
    script, sleeps = Script(*[_retryable(body=_body("busy")) for _ in range(10)]), []
    with pytest.raises(ModelException) as info:
        run_with_retries(script, max_retries=2, sleep=sleeps.append)
    assert info.value.code == LLMErrorCode.ERROR_MAX_RETRIES
    assert info.value.safe_message == "busy" and info.value.provider_status == 429
    assert script.calls == 3 and len(sleeps) == 2


def test_sync_zero_retries_propagates_the_original():
    script = Script(_retryable(), "never")
    with pytest.raises(ModelException) as info:
        run_with_retries(script, max_retries=0, sleep=lambda _d: None)
    assert info.value.code == LLMErrorCode.ERROR_RATE_LIMIT and script.calls == 1


@pytest.mark.parametrize("code", [LLMErrorCode.ERROR_AUTHENTICATION, LLMErrorCode.ERROR_INVALID_REQUEST, LLMErrorCode.ERROR_CONTENT_FILTER, LLMErrorCode.ERROR_SERVER])
def test_sync_never_retries_a_non_retryable_error(code):
    script, sleeps = Script(ModelException(code), "never"), []
    with pytest.raises(ModelException) as info:
        run_with_retries(script, max_retries=5, sleep=sleeps.append)
    assert info.value.code == code and script.calls == 1 and sleeps == []


def test_sync_does_not_swallow_a_foreign_exception():
    with pytest.raises(KeyError):
        run_with_retries(Script(KeyError("x")), max_retries=3, sleep=lambda _d: None)


def test_sync_sleep_uses_retry_after():
    sleeps = []
    run_with_retries(Script(_retryable(retry_after=4.0), "ok"), max_retries=1, sleep=sleeps.append)
    assert sleeps[0] >= 4.0


async def test_async_retries_then_succeeds_with_an_injected_async_sleep():
    script, sleeps = Script(_retryable(LLMErrorCode.ERROR_TIMEOUT), _retryable(), "fine"), []

    async def record_delay(delay):
        sleeps.append(delay)

    assert await arun_with_retries(script.acall, max_retries=3, sleep=record_delay) == "fine"
    assert script.calls == 3 and len(sleeps) == 2


async def test_async_exhaustion_and_non_retryable():
    async def no_sleep(_delay):
        return None

    exhausted = Script(*[_retryable(LLMErrorCode.ERROR_TIMEOUT) for _ in range(5)])
    with pytest.raises(ModelException) as info:
        await arun_with_retries(exhausted.acall, max_retries=1, sleep=no_sleep)
    assert info.value.code == LLMErrorCode.ERROR_MAX_RETRIES and exhausted.calls == 2
    auth = Script(ModelException(LLMErrorCode.ERROR_AUTHENTICATION))
    with pytest.raises(ModelException) as info2:
        await arun_with_retries(auth.acall, max_retries=3, sleep=no_sleep)
    assert info2.value.code == LLMErrorCode.ERROR_AUTHENTICATION and auth.calls == 1


# --- StreamSanitizer --------------------------------------------------------------------------------------------
def _chunk(content=None, *, usage=None, choices=True):
    body: dict = {"choices": [{"index": 0, "delta": ({"content": content} if content is not None else {})}] if choices else []}
    if usage is not None:
        body["usage"] = usage
    return body


def test_usage_dataclass_is_frozen():
    usage = Usage(1, 2, 3, False)
    assert (usage.prompt_tokens, usage.completion_tokens, usage.total_tokens, usage.estimated) == (1, 2, 3, False)
    with pytest.raises(AttributeError):
        usage.total_tokens = 9  # type: ignore[misc]


def test_content_chunks_pass_through_in_order():
    s = StreamSanitizer()
    assert [s.feed(_chunk(p)) for p in ("a", "b", "c")] == ["a", "b", "c"]


def test_empty_choices_and_no_content_are_dropped():
    s = StreamSanitizer()
    assert s.feed(_chunk(choices=False)) is None
    assert s.feed(_chunk()) is None
    assert s.feed({"choices": [{"delta": {"content": None}}]}) is None
    assert s.feed({"choices": [{"delta": {"content": ""}}]}) is None
    assert s.feed({}) is None


def test_control_characters_are_stripped_but_newline_and_tab_stay():
    assert StreamSanitizer().feed(_chunk("a\x00b\x07c\nd\te\x1bf\x7f")) == "abc\nd\tef"


def test_a_chunk_that_is_only_control_characters_yields_nothing():
    assert StreamSanitizer().feed(_chunk("\x00\x01")) is None


def test_trailing_partial_json_fragment_is_ignored():
    s = StreamSanitizer()
    assert s.feed('data: {"choices":[{"delta":{"content":"hi"}}]}') == "hi"
    assert s.feed('data: {"choices":[{"delta":{"con') is None
    assert s.feed("data: [DONE]") is None
    assert s.feed(b'data: {"choices":[{"delta":{"content":"by') is None
    assert s.feed(b'data: {"choices":[{"delta":{"content":"bytes"}}]}') == "bytes"


def test_usage_is_taken_from_a_final_chunk_with_empty_choices():
    s = StreamSanitizer()
    s.feed(_chunk("a"))
    assert s.usage is None
    s.feed(_chunk(choices=False, usage={"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10}))
    assert s.usage == Usage(7, 3, 10, False)


def test_usage_is_taken_from_a_content_chunk_and_not_overwritten_by_null():
    s = StreamSanitizer()
    assert s.feed(_chunk("a", usage={"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3})) == "a"
    s.feed(_chunk("b", usage=None))
    assert s.usage == Usage(1, 2, 3, False)


def test_usage_total_is_derived_when_absent_and_attribute_objects_work():
    class Obj:
        def __init__(self, **kw):
            self.__dict__.update(kw)

    s = StreamSanitizer()
    chunk = Obj(choices=[], usage=Obj(prompt_tokens=4, completion_tokens=6, total_tokens=None))
    assert s.feed(chunk) is None
    assert s.usage == Usage(4, 6, 10, False)
    assert StreamSanitizer().feed(Obj(choices=[Obj(delta=Obj(content="obj"))], usage=None)) == "obj"
