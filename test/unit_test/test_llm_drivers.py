"""Chat driver contract tests against the loopback fake provider (plan 03-05, LLM-01, LLM-04, LLM-05, LLM-17..20, D-03, D-15).

Ollama and Azure are proven here only (no live key exists for them, D-03). Backoff is injected, so no test waits.
"""
from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path

import pytest

from common.settings import LlmSettings
from rag.llm import resolve_provider
from rag.llm.chat_model import ALLOWED_GEN_CONF_KEYS, Base, LiteLLMBase, _estimate_usage, classify_exception, sanitize_gen_conf
from rag.llm.errors import LLMErrorCode, ModelException
from rag.llm.stream import Usage
from test.helpers.fake_provider import CHAT_PIECES, CHAT_TEXT, FAKE_KEY, SECRET_ECHO_KEY, fake_provider  # noqa: F401  (fixture)

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
HISTORY = [{"role": "user", "content": "hello"}]
EXPECTED_USAGE = Usage(11, 5, 16, False)


class Sleeps:
    """Injected backoff: records the delay and never waits."""

    def __init__(self) -> None:
        self.delays: list[float] = []

    async def __call__(self, delay: float) -> None:
        self.delays.append(delay)


def make(provider, model, base, *, key=FAKE_KEY, version=None, retries=3, timeout=10.0, sleeps=None, allow_private=True) -> LiteLLMBase:
    return LiteLLMBase(
        resolve_provider(provider),
        model,
        key,
        base,
        version,
        llm_settings=LlmSettings(max_retries=retries),
        allow_private=allow_private,
        deny_hosts=(),
        sleep=sleeps if sleeps is not None else Sleeps(),
        timeout=timeout,
    )


def chat_requests(fake, path):
    return [r for r in fake.requests if r.path == path]


# --- generation parameter whitelist (LLM-17, LLM-18) ------------------------------------------------------------
def test_whitelist_is_the_documented_set():
    assert len(ALLOWED_GEN_CONF_KEYS) == 20
    assert {"temperature", "max_completion_tokens", "top_p", "stop", "seed", "tools", "extra_headers", "response_format"} <= ALLOWED_GEN_CONF_KEYS
    assert not {"api_key", "base_url", "api_base", "model", "messages", "mirostat", "model_type", "prompt_type"} & ALLOWED_GEN_CONF_KEYS


def test_sanitize_drops_unknown_keys_and_keeps_known_ones():
    out = sanitize_gen_conf({"temperature": 0.1, "top_p": 0.9, "api_key": "x", "base_url": "http://evil", "mirostat": 2, "model_type": "chat"}, "gpt-4o")
    assert out == {"temperature": 0.1, "top_p": 0.9}


def test_sanitize_keeps_max_tokens_for_ordinary_models_and_handles_none():
    assert sanitize_gen_conf({"max_tokens": 64}, "gpt-4o") == {"max_tokens": 64}
    assert sanitize_gen_conf(None, "gpt-4o") == {}


@pytest.mark.parametrize("model", ["o1", "o3-mini", "o4-mini", "openai/o3-mini"])
def test_sanitize_reasoning_models_drop_temperature_and_move_max_tokens(model):
    out = sanitize_gen_conf({"temperature": 0.3, "max_tokens": 77, "top_p": 1}, model)
    assert "temperature" not in out and "max_tokens" not in out
    assert out["max_completion_tokens"] == 77 and out["top_p"] == 1


def test_sanitize_reasoning_model_keeps_an_explicit_max_completion_tokens():
    assert sanitize_gen_conf({"max_completion_tokens": 5}, "o3-mini") == {"max_completion_tokens": 5}


# --- OpenAI-style providers -------------------------------------------------------------------------------------
async def test_openai_chat_sends_bearer_to_chat_completions_with_a_whitelisted_body(fake_provider):  # noqa: F811
    llm = make("OpenAI", "gpt-4o-mini", fake_provider.base_url)
    conf = {"temperature": 0.2, "max_tokens": 50, "api_key": "leak", "base_url": "http://evil.invalid", "mirostat": 1}
    text, tokens = await llm.async_chat("be brief", HISTORY, conf)
    assert (text, tokens) == (CHAT_TEXT, 16)
    (rec,) = chat_requests(fake_provider, "/v1/chat/completions")
    assert rec.method == "POST" and rec.headers["authorization"] == f"Bearer {FAKE_KEY}"
    assert rec.body["model"] == "gpt-4o-mini"
    assert rec.body["messages"] == [{"role": "system", "content": "be brief"}, *HISTORY]
    assert rec.body["temperature"] == 0.2 and rec.body["max_tokens"] == 50
    assert not {"api_key", "base_url", "mirostat", "api_base"} & set(rec.body)
    assert not rec.body.get("stream")
    assert llm.last_usage == EXPECTED_USAGE


async def test_openrouter_default_base_url_is_public_and_overridable(fake_provider):  # noqa: F811
    default = make("OpenRouter", "meta-llama/llama-3.1-8b-instruct", None)
    assert default.api_base == "https://openrouter.ai/api/v1"
    llm = make("OpenRouter", "meta-llama/llama-3.1-8b-instruct", fake_provider.base_url)
    text, _ = await llm.async_chat("", HISTORY, {})
    assert text == CHAT_TEXT
    (rec,) = chat_requests(fake_provider, "/v1/chat/completions")
    assert rec.headers["authorization"] == f"Bearer {FAKE_KEY}" and rec.body["model"] == "meta-llama/llama-3.1-8b-instruct"
    assert rec.body["messages"] == HISTORY  # an empty system prompt adds no system message


async def test_openai_compatible_works_without_a_key(fake_provider):  # noqa: F811
    llm = make("OpenAI-API-Compatible", "local-model", fake_provider.base_url, key=None)
    text, _ = await llm.async_chat("s", HISTORY, {})
    assert text == CHAT_TEXT
    (rec,) = chat_requests(fake_provider, "/v1/chat/completions")
    assert FAKE_KEY not in rec.headers.get("authorization", "")  # no credential was configured, none is invented


async def test_streaming_yields_only_content_in_order_and_captures_usage(fake_provider):  # noqa: F811
    llm = make("OpenAI", "gpt-4o-mini", fake_provider.base_url)
    pieces = [p async for p in llm.async_chat_streamly("s", HISTORY, {"temperature": 0})]
    assert pieces == list(CHAT_PIECES)
    assert all(isinstance(p, str) and p for p in pieces)
    (rec,) = chat_requests(fake_provider, "/v1/chat/completions")
    assert rec.body["stream"] is True and rec.body["stream_options"] == {"include_usage": True}
    assert llm.last_usage == EXPECTED_USAGE


async def test_usage_is_estimated_when_the_provider_reports_none(fake_provider):  # noqa: F811
    llm = make("OpenAI", "fake-no-usage", fake_provider.base_url)
    pieces = [p async for p in llm.async_chat_streamly("s", HISTORY, {})]
    assert "".join(pieces) == CHAT_TEXT
    assert llm.last_usage is not None and llm.last_usage.total_tokens > 0  # litellm counts a stream that reports none
    text, tokens = await llm.async_chat("s", HISTORY, {})
    assert text == CHAT_TEXT and tokens > 0


def test_estimate_usage_is_marked_estimated_and_counts_both_sides():
    usage = _estimate_usage([{"role": "user", "content": "hello there general"}], "hi back")
    assert usage.estimated is True and usage.prompt_tokens > 0 and usage.completion_tokens > 0
    assert usage.total_tokens == usage.prompt_tokens + usage.completion_tokens


async def test_reasoning_model_gets_max_completion_tokens_and_no_temperature(fake_provider):  # noqa: F811
    llm = make("OpenAI", "o3-mini", fake_provider.base_url)
    await llm.async_chat("s", HISTORY, {"temperature": 0.7, "max_tokens": 321})
    (rec,) = chat_requests(fake_provider, "/v1/chat/completions")
    assert rec.body["max_completion_tokens"] == 321
    assert "temperature" not in rec.body and "max_tokens" not in rec.body


# --- Azure and Ollama (contract only) ---------------------------------------------------------------------------
async def test_azure_uses_the_deployment_path_api_key_header_and_api_version(fake_provider):  # noqa: F811
    llm = make("Azure-OpenAI", "my-deployment", fake_provider.azure_url, version="2024-06-01")
    text, tokens = await llm.async_chat("s", HISTORY, {})
    assert (text, tokens) == (CHAT_TEXT, 16)
    (rec,) = chat_requests(fake_provider, "/openai/deployments/my-deployment/chat/completions")
    assert rec.headers["api-key"] == FAKE_KEY and rec.query["api-version"] == "2024-06-01"
    assert "authorization" not in rec.headers or FAKE_KEY not in rec.headers["authorization"]


async def test_ollama_posts_to_api_chat_without_v1_and_streams(fake_provider):  # noqa: F811
    llm = make("Ollama", "llama3.1", fake_provider.ollama_url, key=None)
    text, tokens = await llm.async_chat("s", HISTORY, {"temperature": 0.1})
    assert text == CHAT_TEXT and tokens == 16
    (rec,) = chat_requests(fake_provider, "/api/chat")
    assert rec.method == "POST" and rec.body["model"] == "llama3.1" and rec.body["messages"][-1]["content"] == "hello"
    assert "authorization" not in rec.headers
    fake_provider.reset()
    pieces = [p async for p in llm.async_chat_streamly("s", HISTORY, {})]
    assert "".join(pieces) == CHAT_TEXT
    assert llm.last_usage == EXPECTED_USAGE
    assert [r.path for r in fake_provider.requests] == ["/api/chat"]


# --- error mapping, retry (LLM-19) ------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "model,code,status",
    [
        ("fake-401", LLMErrorCode.ERROR_AUTHENTICATION, 401),
        ("fake-402", LLMErrorCode.ERROR_INVALID_REQUEST, 402),
        ("fake-404", LLMErrorCode.ERROR_INVALID_REQUEST, 404),
        ("fake-filter", LLMErrorCode.ERROR_CONTENT_FILTER, 400),
        ("fake-500", LLMErrorCode.ERROR_SERVER, 500),
    ],
)
async def test_non_retryable_failures_map_and_make_exactly_one_request(fake_provider, model, code, status):  # noqa: F811
    sleeps = Sleeps()
    llm = make("OpenAI", model, fake_provider.base_url, sleeps=sleeps)
    with pytest.raises(ModelException) as info:
        await llm.async_chat("s", HISTORY, {})
    assert info.value.code == code and info.value.provider_status == status and info.value.retryable is False
    assert len(chat_requests(fake_provider, "/v1/chat/completions")) == 1 and sleeps.delays == []


async def test_rate_limit_once_succeeds_after_exactly_one_retry(fake_provider):  # noqa: F811
    sleeps = Sleeps()
    llm = make("OpenAI", "fake-429-once", fake_provider.base_url, sleeps=sleeps)
    text, _ = await llm.async_chat("s", HISTORY, {})
    assert text == CHAT_TEXT
    assert len(chat_requests(fake_provider, "/v1/chat/completions")) == 2
    assert len(sleeps.delays) == 1 and sleeps.delays[0] >= 0.5


async def test_rate_limit_is_retried_a_bounded_number_of_times_then_wrapped(fake_provider):  # noqa: F811
    sleeps = Sleeps()
    llm = make("OpenAI", "fake-429", fake_provider.base_url, retries=2, sleeps=sleeps)
    with pytest.raises(ModelException) as info:
        await llm.async_chat("s", HISTORY, {})
    assert info.value.code == LLMErrorCode.ERROR_MAX_RETRIES and info.value.provider_status == 429
    assert info.value.safe_message == "Rate limit reached."
    assert len(chat_requests(fake_provider, "/v1/chat/completions")) == 3  # one call plus two retries, the SDK adds none
    assert len(sleeps.delays) == 2


async def test_zero_retries_means_one_request(fake_provider):  # noqa: F811
    llm = make("OpenAI", "fake-429", fake_provider.base_url, retries=0)
    with pytest.raises(ModelException) as info:
        await llm.async_chat("s", HISTORY, {})
    assert info.value.code == LLMErrorCode.ERROR_RATE_LIMIT and info.value.retryable
    assert len(chat_requests(fake_provider, "/v1/chat/completions")) == 1


async def test_ollama_failures_map_through_the_same_path(fake_provider):  # noqa: F811
    llm = make("Ollama", "fake-401", fake_provider.ollama_url, key=None)
    with pytest.raises(ModelException) as info:
        await llm.async_chat("s", HISTORY, {})
    assert info.value.code == LLMErrorCode.ERROR_AUTHENTICATION and info.value.safe_message == "Incorrect API key provided."
    assert len(chat_requests(fake_provider, "/api/chat")) == 1


async def test_a_redirect_from_ollama_is_not_followed(fake_provider):  # noqa: F811
    llm = make("Ollama", "fake-redirect", fake_provider.ollama_url, key=None)
    with pytest.raises(ModelException):
        await llm.async_chat("s", HISTORY, {})
    assert fake_provider.hits("/v1/redirect-target") == []


async def test_extra_headers_from_a_caller_are_dropped_unless_the_driver_is_trusted(fake_provider):  # noqa: F811
    conf = {"extra_headers": {"X-Probe": "1"}, "top_p": 0.5}
    await make("OpenAI", "gpt-4o-mini", fake_provider.base_url).async_chat("s", HISTORY, conf)
    assert "x-probe" not in chat_requests(fake_provider, "/v1/chat/completions")[0].headers
    fake_provider.reset()
    trusted = make("OpenAI", "gpt-4o-mini", fake_provider.base_url)
    trusted.trust_extra_headers = True
    await trusted.async_chat("s", HISTORY, conf)
    assert chat_requests(fake_provider, "/v1/chat/completions")[0].headers["x-probe"] == "1"


async def test_a_stream_that_fails_to_open_maps_the_same_way(fake_provider):  # noqa: F811
    llm = make("OpenAI", "fake-401", fake_provider.base_url)
    with pytest.raises(ModelException) as info:
        _ = [p async for p in llm.async_chat_streamly("s", HISTORY, {})]
    assert info.value.code == LLMErrorCode.ERROR_AUTHENTICATION


async def test_a_call_timeout_maps_to_error_timeout(fake_provider):  # noqa: F811
    llm = make("OpenAI-API-Compatible", "anything", fake_provider.slow_url, retries=0, timeout=0.3)
    with pytest.raises(ModelException) as info:
        await llm.async_chat("s", HISTORY, {})
    assert info.value.code == LLMErrorCode.ERROR_TIMEOUT and info.value.retryable


async def test_a_refused_connection_maps_to_error_connection():
    llm = make("OpenAI-API-Compatible", "m", "http://127.0.0.1:9/v1", retries=0)
    with pytest.raises(ModelException) as info:
        await llm.async_chat("s", HISTORY, {})
    assert info.value.code == LLMErrorCode.ERROR_CONNECTION


async def test_a_provider_echoing_the_key_never_reaches_the_message_or_the_log(fake_provider, caplog):  # noqa: F811
    caplog.set_level(logging.DEBUG)
    llm = make("OpenAI", "fake-secret-echo", fake_provider.base_url)
    with pytest.raises(ModelException) as info:
        await llm.async_chat("s", HISTORY, {})
    exc = info.value
    assert SECRET_ECHO_KEY not in exc.safe_message and "***" in exc.safe_message
    assert SECRET_ECHO_KEY not in str(exc) and SECRET_ECHO_KEY not in repr(exc)
    assert SECRET_ECHO_KEY not in caplog.text and FAKE_KEY not in caplog.text


# --- SSRF (T-03-05-01) ------------------------------------------------------------------------------------------
async def test_a_redirect_is_not_followed(fake_provider):  # noqa: F811
    llm = make("OpenAI", "fake-redirect", fake_provider.base_url)
    with pytest.raises(ModelException):
        await llm.async_chat("s", HISTORY, {})
    assert fake_provider.hits("/v1/redirect-target") == []
    assert len(chat_requests(fake_provider, "/v1/chat/completions")) == 1


@pytest.mark.parametrize("base", ["http://169.254.169.254/v1", "http://[fd00:ec2::254]/v1", "http://es01:9200/v1", "http://minio:9000"])
async def test_metadata_and_internal_addresses_are_refused_before_any_request(fake_provider, base):  # noqa: F811
    llm = make("OpenAI-API-Compatible", "m", base)
    with pytest.raises(ModelException) as info:
        await llm.async_chat("s", HISTORY, {})
    assert info.value.code == LLMErrorCode.ERROR_INVALID_REQUEST
    assert fake_provider.requests == []


async def test_a_loopback_base_url_is_refused_when_private_addresses_are_not_allowed(fake_provider):  # noqa: F811
    llm = make("OpenAI-API-Compatible", "m", fake_provider.base_url, allow_private=False)
    with pytest.raises(ModelException) as info:
        _ = [p async for p in llm.async_chat_streamly("s", HISTORY, {})]
    assert info.value.code == LLMErrorCode.ERROR_INVALID_REQUEST
    assert fake_provider.requests == []


# --- interface and lazy import ----------------------------------------------------------------------------------
def test_base_declares_the_four_chat_methods_and_last_usage():
    for name in ("chat", "async_chat", "chat_streamly", "async_chat_streamly"):
        assert callable(getattr(Base, name))
    assert issubclass(LiteLLMBase, Base)


def test_sync_chat_and_streaming_work_outside_an_event_loop(fake_provider):  # noqa: F811
    llm = make("OpenAI", "gpt-4o-mini", fake_provider.base_url)
    assert llm.chat("s", HISTORY, {}) == (CHAT_TEXT, 16)
    assert list(llm.chat_streamly("s", HISTORY, {})) == list(CHAT_PIECES)
    assert llm.last_usage == EXPECTED_USAGE


async def test_sync_chat_inside_a_running_loop_is_refused(fake_provider):  # noqa: F811
    llm = make("OpenAI", "gpt-4o-mini", fake_provider.base_url)
    with pytest.raises(RuntimeError):
        llm.chat("s", HISTORY, {})


def test_classify_exception_wraps_an_unknown_exception_without_its_text():
    exc = classify_exception(ValueError("secret-text-" + FAKE_KEY))
    assert isinstance(exc, ModelException) and exc.code == LLMErrorCode.ERROR_GENERIC and exc.retryable is False
    assert FAKE_KEY not in exc.safe_message and FAKE_KEY not in str(exc)


def test_classify_exception_passes_a_model_exception_through():
    original = ModelException(LLMErrorCode.ERROR_QUOTA)
    assert classify_exception(original) is original


@pytest.mark.parametrize("module", ["rag.llm", "rag.llm.model_meta", "rag.llm.errors", "rag.llm.retry", "rag.llm.stream", "rag.llm.chat_model"])
def test_importing_the_package_does_not_import_litellm(module):
    code = f"import sys, {module}; bad = [m for m in ('litellm', 'openai') if m in sys.modules]; sys.exit(1 if bad else 0)"
    result = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, timeout=120, check=False)
    assert result.returncode == 0, result.stderr[-500:]
