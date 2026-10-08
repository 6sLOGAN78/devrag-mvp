"""Embedding driver contract tests against the loopback fake provider (plan 03-06, LLM-03, LLM-04, LLM-05, LLM-19, LLM-21, D-03, D-06).

Azure and Ollama are proven here only (no live key exists for them, D-03, D-15). Backoff is injected, so no test waits.
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path

import pytest

from common.settings import LlmSettings
from rag.llm import resolve_provider
from rag.llm.embedding_model import AzureEmbed, Base, OllamaEmbed, OpenAIEmbed, build_embedder, truncate_to_tokens
from rag.llm.errors import LLMErrorCode, ModelException
from rag.llm.stream import Usage
from test.helpers.fake_provider import FAKE_KEY, SECRET_ECHO_KEY, fake_provider  # noqa: F401  (fixture)

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
TOKEN_LIMIT = 8191


class Sleeps:
    """Injected backoff: records the delay and never waits."""

    def __init__(self) -> None:
        self.delays: list[float] = []

    def __call__(self, delay: float) -> None:
        self.delays.append(delay)


def make(provider, model, base, *, key=FAKE_KEY, version=None, retries=3, sleeps=None, allow_private=True, timeout=10.0) -> Base:
    return build_embedder(
        resolve_provider(provider),
        model,
        key,
        base,
        version,
        llm_settings=LlmSettings(max_retries=retries, embedding_timeout_seconds=int(timeout)),
        allow_private=allow_private,
        deny_hosts=(),
        sleep=sleeps if sleeps is not None else Sleeps(),
    )


def requests_to(fake, path):
    return [r for r in fake.requests if r.path == path]


# --- OpenAI SDK providers -------------------------------------------------------------------------------------------
def test_openai_style_encode_returns_vectors_of_the_requested_length_and_provider_usage(fake_provider):  # noqa: F811
    fake_provider.embedding_dim = 8
    embedder = make("OpenAI-API-Compatible", "emb-model", fake_provider.base_url)
    vectors, tokens = embedder.encode(["alpha beta", "gamma"])
    assert isinstance(embedder, OpenAIEmbed)
    assert [len(v) for v in vectors] == [8, 8]
    assert tokens == 3  # the fake counts words: 2 + 1
    assert embedder.last_usage == Usage(3, 0, 3, False)
    sent = requests_to(fake_provider, "/v1/embeddings")
    assert len(sent) == 1
    assert sent[0].body["encoding_format"] == "float"
    assert sent[0].body["model"] == "emb-model"
    assert sent[0].body["input"] == ["alpha beta", "gamma"]
    assert sent[0].headers["authorization"] == f"Bearer {FAKE_KEY}"


@pytest.mark.parametrize("provider", ["OpenAI-API-Compatible", "OpenRouter"])
def test_openai_compatible_and_openrouter_use_the_openai_driver(provider, fake_provider):  # noqa: F811
    embedder = make(provider, "m", fake_provider.base_url)
    assert isinstance(embedder, OpenAIEmbed)
    assert len(embedder.encode(["x"])[0][0]) == 8


def test_the_returned_dimension_is_what_the_provider_sent_never_a_constant(fake_provider):  # noqa: F811
    fake_provider.embedding_dim = 1536
    vectors, _ = make("OpenAI", "text-embedding-3-small", fake_provider.base_url).encode(["a"])
    assert len(vectors[0]) == 1536
    fake_provider.embedding_dim = 384
    vectors, _ = make("OpenAI", "text-embedding-3-small", fake_provider.base_url).encode(["a"])
    assert len(vectors[0]) == 384


def test_results_follow_input_order_even_when_the_provider_shuffles(fake_provider):  # noqa: F811
    fake_provider.shuffle_embeddings = True
    vectors, _ = make("OpenAI-API-Compatible", "m", fake_provider.base_url).encode(["a", "b", "c"])
    assert [v[0] for v in vectors] == [0.1, 0.2, 0.3]


def test_an_empty_string_is_sent_as_a_single_space(fake_provider):  # noqa: F811
    make("OpenAI-API-Compatible", "m", fake_provider.base_url).encode(["", "text"])
    assert requests_to(fake_provider, "/v1/embeddings")[0].body["input"] == [" ", "text"]


def test_forty_inputs_make_three_requests_of_at_most_sixteen(fake_provider):  # noqa: F811
    vectors, tokens = make("OpenAI-API-Compatible", "m", fake_provider.base_url).encode([f"t{i}" for i in range(40)])
    sizes = [len(r.body["input"]) for r in requests_to(fake_provider, "/v1/embeddings")]
    assert sizes == [16, 16, 8]
    assert len(vectors) == 40 and tokens == 40


def test_encode_nothing_makes_no_request(fake_provider):  # noqa: F811
    assert make("OpenAI-API-Compatible", "m", fake_provider.base_url).encode([]) == ([], 0)
    assert fake_provider.requests == []


def test_encode_queries_returns_one_vector_and_its_tokens(fake_provider):  # noqa: F811
    vector, tokens = make("OpenAI-API-Compatible", "m", fake_provider.base_url).encode_queries("what is this")
    assert len(vector) == 8 and tokens == 3


def test_missing_provider_usage_is_estimated_and_marked(fake_provider):  # noqa: F811
    embedder = make("OpenAI-API-Compatible", "fake-no-usage", fake_provider.base_url)
    _, tokens = embedder.encode(["one two three four"])
    assert tokens > 0
    assert embedder.last_usage is not None and embedder.last_usage.estimated is True and embedder.last_usage.total_tokens == tokens


def test_a_provider_answering_with_the_wrong_number_of_vectors_is_an_error(fake_provider, monkeypatch):  # noqa: F811
    embedder = make("OpenAI-API-Compatible", "m", fake_provider.base_url)
    monkeypatch.setattr("test.helpers.fake_provider._inputs", lambda body: ["only-one"])
    with pytest.raises(ModelException) as info:
        embedder.encode(["a", "b"])
    assert info.value.code == LLMErrorCode.ERROR_GENERIC


# --- Azure ------------------------------------------------------------------------------------------------------------
def test_azure_posts_to_the_deployment_path_with_api_version_and_api_key_header(fake_provider):  # noqa: F811
    embedder = make("Azure-OpenAI", "my-deploy", fake_provider.azure_url, version="2024-02-01")
    vectors, tokens = embedder.encode(["alpha beta"])
    assert isinstance(embedder, AzureEmbed)
    assert len(vectors[0]) == 8 and tokens == 2
    sent = requests_to(fake_provider, "/openai/deployments/my-deploy/embeddings")
    assert len(sent) == 1
    assert sent[0].query["api-version"] == "2024-02-01"
    assert sent[0].headers["api-key"] == FAKE_KEY
    assert "authorization" not in sent[0].headers
    assert sent[0].body["encoding_format"] == "float"


# --- Ollama -----------------------------------------------------------------------------------------------------------
def test_ollama_posts_model_and_input_to_api_embed_and_reads_prompt_eval_count(fake_provider):  # noqa: F811
    fake_provider.embedding_dim = 5
    embedder = make("Ollama", "nomic-embed-text", fake_provider.ollama_url, key=None)
    vectors, tokens = embedder.encode(["alpha beta", "gamma"])
    assert isinstance(embedder, OllamaEmbed)
    assert [len(v) for v in vectors] == [5, 5]
    assert tokens == 3
    assert embedder.last_usage == Usage(3, 0, 3, False)
    sent = requests_to(fake_provider, "/api/embed")
    assert len(sent) == 1
    assert sent[0].body["model"] == "nomic-embed-text"
    assert sent[0].body["input"] == ["alpha beta", "gamma"]


def test_ollama_batches_and_replaces_empty_strings(fake_provider):  # noqa: F811
    vectors, _ = make("Ollama", "m", fake_provider.ollama_url, key=None).encode(["", *[f"t{i}" for i in range(19)]])
    sent = requests_to(fake_provider, "/api/embed")
    assert [len(r.body["input"]) for r in sent] == [16, 4]
    assert sent[0].body["input"][0] == " " and len(vectors) == 20


def test_ollama_sends_no_authorization_header_without_a_key(fake_provider, monkeypatch):  # noqa: F811
    monkeypatch.setenv("OLLAMA_API_KEY", "should-not-be-sent-" + "x" * 12)
    make("Ollama", "m", fake_provider.ollama_url, key=None).encode(["a"])
    assert "authorization" not in requests_to(fake_provider, "/api/embed")[0].headers


def test_an_ollama_base_url_ending_in_v1_is_refused_before_any_request(fake_provider):  # noqa: F811
    embedder = make("Ollama", "m", fake_provider.ollama_url + "/v1", key=None)
    with pytest.raises(ModelException) as info:
        embedder.encode(["a"])
    assert info.value.code == LLMErrorCode.ERROR_INVALID_REQUEST
    assert fake_provider.requests == []


# --- errors, retries, safety -----------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("provider", "base", "path"),
    [
        ("OpenAI-API-Compatible", "base_url", "/v1/embeddings"),
        ("Ollama", "ollama_url", "/api/embed"),
    ],
)
def test_authentication_failure_is_not_retried(provider, base, path, fake_provider):  # noqa: F811
    sleeps = Sleeps()
    embedder = make(provider, "fake-401", getattr(fake_provider, base), sleeps=sleeps, key=None if provider == "Ollama" else FAKE_KEY)
    with pytest.raises(ModelException) as info:
        embedder.encode(["a"])
    assert info.value.code == LLMErrorCode.ERROR_AUTHENTICATION and info.value.retryable is False
    assert len(requests_to(fake_provider, path)) == 1
    assert sleeps.delays == []


def test_azure_authentication_failure_is_not_retried(fake_provider):  # noqa: F811
    embedder = make("Azure-OpenAI", "fake-401", fake_provider.azure_url, version="2024-02-01")
    with pytest.raises(ModelException) as info:
        embedder.encode(["a"])
    assert info.value.code == LLMErrorCode.ERROR_AUTHENTICATION
    assert len(requests_to(fake_provider, "/openai/deployments/fake-401/embeddings")) == 1


def test_a_rate_limit_is_retried_once_and_then_succeeds(fake_provider):  # noqa: F811
    sleeps = Sleeps()
    vectors, _ = make("OpenAI-API-Compatible", "fake-429-once", fake_provider.base_url, sleeps=sleeps).encode(["a"])
    assert len(vectors) == 1
    assert len(requests_to(fake_provider, "/v1/embeddings")) == 2
    assert len(sleeps.delays) == 1


def test_a_persistent_rate_limit_stops_at_the_retry_bound(fake_provider):  # noqa: F811
    sleeps = Sleeps()
    embedder = make("OpenAI-API-Compatible", "fake-429", fake_provider.base_url, retries=2, sleeps=sleeps)
    with pytest.raises(ModelException) as info:
        embedder.encode(["a"])
    assert info.value.code == LLMErrorCode.ERROR_MAX_RETRIES
    assert len(requests_to(fake_provider, "/v1/embeddings")) == 3
    assert len(sleeps.delays) == 2


def test_an_invalid_request_is_not_retried(fake_provider):  # noqa: F811
    embedder = make("OpenAI-API-Compatible", "fake-404", fake_provider.base_url)
    with pytest.raises(ModelException) as info:
        embedder.encode(["a"])
    assert info.value.code == LLMErrorCode.ERROR_INVALID_REQUEST
    assert len(requests_to(fake_provider, "/v1/embeddings")) == 1


def test_a_server_error_is_classified_and_not_retried(fake_provider):  # noqa: F811
    with pytest.raises(ModelException) as info:
        make("OpenAI-API-Compatible", "fake-500", fake_provider.base_url).encode(["a"])
    assert info.value.code == LLMErrorCode.ERROR_SERVER and info.value.retryable is False
    assert len(requests_to(fake_provider, "/v1/embeddings")) == 1


def test_a_refused_connection_is_a_connection_error():
    embedder = make("OpenAI-API-Compatible", "m", "http://127.0.0.1:1/v1", retries=0)
    with pytest.raises(ModelException) as info:
        embedder.encode(["a"])
    assert info.value.code == LLMErrorCode.ERROR_CONNECTION


@pytest.mark.parametrize(("provider", "base", "path"), [("OpenAI-API-Compatible", "base_url", "/v1/embeddings"), ("Ollama", "ollama_url", "/api/embed")])
def test_a_redirect_is_not_followed(provider, base, path, fake_provider):  # noqa: F811
    embedder = make(provider, "fake-redirect", getattr(fake_provider, base), key=None if provider == "Ollama" else FAKE_KEY)
    with pytest.raises(ModelException):
        embedder.encode(["a"])
    assert fake_provider.hits("/v1/redirect-target") == []
    assert len(requests_to(fake_provider, path)) == 1


@pytest.mark.parametrize("base", ["http://169.254.169.254/v1", "http://[fd00:ec2::254]/v1", "http://es01:9200/v1", "http://minio:9000"])
def test_metadata_and_internal_addresses_are_refused_before_any_request(fake_provider, base):  # noqa: F811
    with pytest.raises(ModelException) as info:
        make("OpenAI-API-Compatible", "m", base).encode(["a"])
    assert info.value.code == LLMErrorCode.ERROR_INVALID_REQUEST
    assert fake_provider.requests == []


def test_a_loopback_base_url_is_refused_when_private_addresses_are_not_allowed(fake_provider):  # noqa: F811
    with pytest.raises(ModelException) as info:
        make("OpenAI-API-Compatible", "m", fake_provider.base_url, allow_private=False).encode(["a"])
    assert info.value.code == LLMErrorCode.ERROR_INVALID_REQUEST
    assert fake_provider.requests == []


def test_a_key_echoed_by_the_provider_never_reaches_a_message_or_a_log(fake_provider, caplog):  # noqa: F811
    caplog.set_level(logging.DEBUG)
    with pytest.raises(ModelException) as info:
        make("OpenAI-API-Compatible", "fake-secret-echo", fake_provider.base_url).encode(["a"])
    exc = info.value
    for text in (exc.safe_message, str(exc), repr(exc), caplog.text):
        assert SECRET_ECHO_KEY not in text
        assert FAKE_KEY not in text
    assert exc.__cause__ is None and exc.__context__ is None


def test_the_fake_key_never_appears_in_the_driver_repr(fake_provider):  # noqa: F811
    assert FAKE_KEY not in repr(make("OpenAI", "m", fake_provider.base_url))


# --- factory ----------------------------------------------------------------------------------------------------------
def test_the_factory_maps_each_provider_to_its_driver():
    kinds = {
        "OpenAI": OpenAIEmbed,
        "OpenRouter": OpenAIEmbed,
        "OpenAI-API-Compatible": OpenAIEmbed,
        "Azure-OpenAI": AzureEmbed,
        "Ollama": OllamaEmbed,
    }
    for name, kind in kinds.items():
        assert type(make(name, "m", "http://127.0.0.1:9", key=None)) is kind


def test_base_declares_the_embedding_interface():
    for name in ("encode", "encode_queries"):
        assert callable(getattr(Base, name))
    assert issubclass(OpenAIEmbed, Base) and issubclass(AzureEmbed, Base) and issubclass(OllamaEmbed, Base)


# --- truncation and the offline tokenizer cache ------------------------------------------------------------------------
_OFFLINE_SCRIPT = """
import os, sys
from rag.llm.embedding_model import truncate_to_tokens
import tiktoken
cut = truncate_to_tokens("word " * 20000, 8191, "text-embedding-3-small")
print(len(tiktoken.get_encoding("cl100k_base").encode(cut)))
print(os.environ.get("TIKTOKEN_CACHE_DIR", ""))
"""


def test_truncation_to_8191_tokens_works_with_the_network_blocked(tmp_path):
    env = {k: v for k, v in os.environ.items() if k not in {"TIKTOKEN_CACHE_DIR", "DATA_GYM_CACHE_DIR"}}
    env.update(
        HTTP_PROXY="http://192.0.2.1:9", HTTPS_PROXY="http://192.0.2.1:9", http_proxy="http://192.0.2.1:9", https_proxy="http://192.0.2.1:9",
        TMPDIR=str(tmp_path), XDG_CACHE_HOME=str(tmp_path / "xdg"), NO_PROXY="", no_proxy="",
    )  # fmt: skip
    result = subprocess.run([sys.executable, "-c", _OFFLINE_SCRIPT], cwd=ROOT, env=env, capture_output=True, text=True, timeout=120, check=False)
    assert result.returncode == 0, result.stderr[-800:]
    count, cache_dir = result.stdout.split("\n")[:2]
    assert int(count) == TOKEN_LIMIT
    assert cache_dir and "litellm" in cache_dir
    assert list(tmp_path.iterdir()) == []  # nothing was downloaded into the temp directory


def test_a_text_under_the_limit_is_returned_unchanged():
    assert truncate_to_tokens("short text", TOKEN_LIMIT, "m") == "short text"


def test_truncation_uses_the_lower_model_limit_when_given():
    assert len(truncate_to_tokens("word " * 500, 100, "m")) < len("word " * 500)


def test_truncation_falls_back_to_a_character_estimate_when_the_tokenizer_is_unavailable(monkeypatch):
    import rag.llm.embedding_model as module

    def broken():
        raise RuntimeError("no vocabulary")

    monkeypatch.setattr(module, "_encoding", broken)
    text = "x" * 1000
    assert truncate_to_tokens(text, 100, "m") == text[:300]
    assert truncate_to_tokens("tiny", 100, "m") == "tiny"


def test_encode_truncates_each_text_before_sending(fake_provider):  # noqa: F811
    make("OpenAI-API-Compatible", "m", fake_provider.base_url).encode(["word " * 20000])
    sent = requests_to(fake_provider, "/v1/embeddings")[0].body["input"][0]
    assert len(sent) < len("word " * 20000)


def test_the_embedding_module_imports_no_sdk_at_import_time():
    code = "import sys, rag.llm.embedding_model; bad = [m for m in ('litellm', 'openai', 'ollama') if m in sys.modules]; sys.exit(1 if bad else 0)"
    result = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, timeout=120, check=False)
    assert result.returncode == 0, result.stderr[-500:]
