"""Embedding drivers (plan 03-06, LLM-03, LLM-04, LLM-05, LLM-19, LLM-21, D-06, D-15).

``Base.encode(texts)`` returns ``(vectors, total_tokens)``. Callers record ``len(vectors[0])`` as the dimension: no driver
hard-codes one (D-06). ``OpenAIEmbed`` serves OpenAI, OpenRouter and OpenAI-compatible endpoints through the OpenAI SDK,
``AzureEmbed`` the Azure deployment path, ``OllamaEmbed`` Ollama's native ``/api/embed``. ``build_embedder`` picks one.

Safety rules the drivers enforce (they mirror ``rag.llm.chat_model``):

* SDKs are imported lazily; importing this module loads none of them.
* Each ``encode`` call builds its own ``httpx`` client with ``follow_redirects=False``; SDK retries are off
  (``max_retries=0``) and ``rag.llm.retry.run_with_retries`` is the only loop (T-03-06-01, T-03-06-04).
* The base URL is validated by ``common.net.url_guard`` before the first request and re-validated before every attempt.
* Failure text comes from the response body through ``ModelException`` (parsed, redacted, truncated); the string form of an SDK
  exception is never used, and the exception is raised outside the ``except`` block so no chained cause carries it (T-03-06-02).
* Input is cut to the model's token limit with tiktoken ``cl100k_base``; the vocabulary is read from the file litellm vendors,
  so nothing is downloaded at run time, with a character estimate as the last resort (T-03-06-05).

The SDK calls are synchronous: the service layer runs them in its bounded executor. This module never touches the event loop.
"""
from __future__ import annotations

import contextlib
import functools
import importlib.util
import json
import logging
import os
import sys
import time
from collections.abc import Callable, Collection, Iterator
from pathlib import Path
from typing import Any

import httpx

from common.net.url_guard import UnsafeBaseUrl, ValidatedUrl, assert_unchanged, validate_base_url
from common.settings import LlmSettings
from rag.llm import Provider, ProviderSpec, validate_base_url_shape
from rag.llm.errors import LLMErrorCode, ModelException
from rag.llm.model_meta import lookup
from rag.llm.retry import run_with_retries
from rag.llm.stream import Usage, usage_from

logger = logging.getLogger(__name__)

BATCH_SIZE = 16
TOKEN_CEILING = 8191
_BODY_LIMIT = 65536
_PLACEHOLDER_KEY = "not-needed"  # the OpenAI SDK insists on a key even for endpoints that need none
_CL100K_CACHE_NAME = "9b5ad71b2ce5302211f9c61530b329a4922fc6a4"  # sha1 of the cl100k_base URL: tiktoken's cache file name


# --- tokenizer ------------------------------------------------------------------------------------------------------------
def _point_tiktoken_at_vendored_ranks() -> None:
    """Use litellm's vendored cl100k_base file so tiktoken never downloads it. No-op when the file or litellm is absent."""
    if os.environ.get("TIKTOKEN_CACHE_DIR"):
        return
    try:
        spec = importlib.util.find_spec("litellm")  # locates the package without importing it (litellm is heavy)
        roots = list(spec.submodule_search_locations or []) if spec else []
    except (ImportError, ValueError):
        return
    for root in roots:
        directory = Path(root) / "litellm_core_utils" / "tokenizers"
        if (directory / _CL100K_CACHE_NAME).is_file():
            os.environ.setdefault("TIKTOKEN_CACHE_DIR", str(directory))
            return


@functools.lru_cache(maxsize=1)
def _encoding() -> Any:
    _point_tiktoken_at_vendored_ranks()
    import tiktoken

    return tiktoken.get_encoding("cl100k_base")


def truncate_to_tokens(text: str, limit: int, model: str) -> str:
    """Cut ``text`` to at most ``limit`` cl100k_base tokens. ``model`` is kept for a later per-model tokenizer."""
    del model
    if len(text) <= limit:  # a token is at least one character, so the text cannot exceed the limit
        return text
    try:
        encoding = _encoding()
        tokens = encoding.encode(text, disallowed_special=())
        return text if len(tokens) <= limit else encoding.decode(tokens[:limit])
    except Exception:  # noqa: BLE001 - offline without a vocabulary, or a malformed surrogate: fall back to a rough cut
        return text[: limit * 3]


def _estimate_tokens(texts: list[str]) -> int:
    try:
        encoding = _encoding()
        return sum(len(encoding.encode(t, disallowed_special=())) for t in texts)
    except Exception:  # noqa: BLE001
        return sum(max(1, len(t) // 4) for t in texts)


# --- error mapping ----------------------------------------------------------------------------------------------------------
def _parse_retry_after(value: str | None) -> float | None:
    try:
        seconds = float(value) if value is not None else None
    except ValueError:
        return None
    return seconds if seconds is not None and seconds >= 0 else None


def _by_status(status: int | None, body: bytes | None, retry_after: float | None) -> ModelException:
    if status in (401, 403):
        return ModelException(LLMErrorCode.ERROR_AUTHENTICATION, provider_status=status, body=body)
    if status == 429:
        return ModelException(LLMErrorCode.ERROR_RATE_LIMIT, retryable=True, provider_status=status, retry_after=retry_after, body=body)
    if status == 408:
        return ModelException(LLMErrorCode.ERROR_TIMEOUT, retryable=True, provider_status=status, retry_after=retry_after, body=body)
    if status is not None and 400 <= status < 500:
        return ModelException(LLMErrorCode.ERROR_INVALID_REQUEST, provider_status=status, body=body)
    if status is not None and status >= 500:
        return ModelException(LLMErrorCode.ERROR_SERVER, provider_status=status, body=body)
    return ModelException(LLMErrorCode.ERROR_GENERIC, provider_status=status)  # 3xx (never followed) and anything unexpected


def classify_embedding_error(exc: BaseException) -> ModelException:
    """Map an SDK or transport exception to a ``ModelException`` by type and status code, never by message text."""
    if isinstance(exc, ModelException):
        return exc
    openai, ollama = sys.modules.get("openai"), sys.modules.get("ollama")
    if openai is not None and isinstance(exc, openai.APITimeoutError):
        return ModelException(LLMErrorCode.ERROR_TIMEOUT, retryable=True)
    if openai is not None and isinstance(exc, openai.APIConnectionError):
        return ModelException(LLMErrorCode.ERROR_CONNECTION)
    if openai is not None and isinstance(exc, openai.APIStatusError):
        response = exc.response
        body = response.content[:_BODY_LIMIT]
        return _by_status(exc.status_code, body, _parse_retry_after(response.headers.get("retry-after")))
    if ollama is not None and isinstance(exc, ollama.ResponseError):
        detail = exc.error if isinstance(exc.error, (str, dict)) else None
        status = exc.status_code if isinstance(exc.status_code, int) and exc.status_code > 0 else None
        return _by_status(status, json.dumps({"error": detail}).encode() if detail is not None else None, None)
    if isinstance(exc, (TimeoutError, httpx.TimeoutException)):
        return ModelException(LLMErrorCode.ERROR_TIMEOUT, retryable=True)
    if isinstance(exc, (httpx.TransportError, ConnectionError, OSError)):
        return ModelException(LLMErrorCode.ERROR_CONNECTION)
    return ModelException(LLMErrorCode.ERROR_GENERIC)


# --- drivers ----------------------------------------------------------------------------------------------------------------
class Base:
    """Embedding driver interface. Subclasses implement ``_open`` (one client per call) and ``_embed`` (one batch)."""

    def __init__(
        self,
        provider_spec: ProviderSpec,
        model_name: str,
        api_key: str | None,
        api_base: str | None,
        api_version: str | None = None,
        *,
        llm_settings: LlmSettings,
        allow_private: bool,
        deny_hosts: Collection[str] = (),
        sleep: Callable[[float], object] = time.sleep,
        timeout: float | None = None,
    ) -> None:
        self.spec = provider_spec
        self.model_name = model_name
        self._api_key = api_key
        self.api_base = (api_base or provider_spec.default_base_url or "").strip().rstrip("/") or None
        self.api_version = api_version
        self.llm_settings = llm_settings
        self.allow_private = allow_private
        self.deny_hosts = tuple(deny_hosts)
        self._sleep = sleep
        self.timeout = float(timeout if timeout is not None else llm_settings.embedding_timeout_seconds)
        self.last_usage: Usage | None = None

    def __repr__(self) -> str:
        return f"{type(self).__name__}(provider={self.spec.name!r}, model={self.model_name!r})"

    @property
    def token_limit(self) -> int:
        return min(TOKEN_CEILING, lookup(self.spec.name, self.model_name).max_tokens)

    def _check_target(self, validated: ValidatedUrl | None) -> ValidatedUrl | None:
        """Shape check, then SSRF check before an attempt (re-checked on later ones against DNS rebinding)."""
        problem = validate_base_url_shape(self.spec, self.api_base)
        if problem is not None:
            raise ModelException(LLMErrorCode.ERROR_INVALID_REQUEST, message=f"base URL rejected: {problem}")
        if self.api_base is None:
            raise ModelException(LLMErrorCode.ERROR_INVALID_REQUEST, message="base URL is required for this provider")
        if self.api_base == self.spec.default_base_url:
            return None  # the documented public host
        try:
            if validated is None:
                return validate_base_url(self.api_base, allow_private=self.allow_private, deny_hosts=self.deny_hosts)
            return assert_unchanged(validated, self.api_base, allow_private=self.allow_private, deny_hosts=self.deny_hosts)
        except UnsafeBaseUrl as refused:
            reason = refused.reason
        raise ModelException(LLMErrorCode.ERROR_INVALID_REQUEST, message=f"base URL rejected: {reason}")

    def _http(self) -> httpx.Client:
        return httpx.Client(follow_redirects=False, timeout=self.timeout)

    @contextlib.contextmanager
    def _open(self) -> Iterator[Any]:
        raise NotImplementedError
        yield  # pragma: no cover

    def _embed(self, client: Any, batch: list[str]) -> tuple[list[list[float]], Usage | None]:
        raise NotImplementedError

    def _attempt(self, client: Any, state: dict[str, Any], batch: list[str]) -> tuple[list[list[float]], Usage | None]:
        state["validated"] = self._check_target(state.get("validated"))
        failure: ModelException | None = None
        try:
            vectors, usage = self._embed(client, batch)
        except Exception as exc:  # noqa: BLE001 - every provider/SDK failure is mapped below
            failure = classify_embedding_error(exc)
        else:
            if len(vectors) != len(batch) or any(not v for v in vectors):
                failure = ModelException(LLMErrorCode.ERROR_GENERIC, message="provider returned an unexpected number of vectors")
            else:
                return vectors, usage
        logger.warning("embedding call failed provider=%s model=%s code=%s", self.spec.name, self.model_name, failure.code.value)
        raise failure

    def encode(self, texts: list[str]) -> tuple[list[list[float]], int]:
        if not texts:
            self.last_usage = Usage(0, 0, 0, False)
            return [], 0
        limit = self.token_limit
        prepared = [truncate_to_tokens(t if t else " ", limit, self.model_name) for t in texts]
        state: dict[str, Any] = {"validated": self._check_target(None)}  # refuse a bad target before any client exists
        vectors: list[list[float]] = []
        prompt = total = 0
        estimated = False
        with self._open() as client:
            for start in range(0, len(prepared), BATCH_SIZE):
                batch = prepared[start : start + BATCH_SIZE]
                got, usage = run_with_retries(
                    lambda b=batch: self._attempt(client, state, b), max_retries=self.llm_settings.max_retries, sleep=self._sleep
                )
                vectors.extend(got)
                if usage is None or usage.total_tokens <= 0:
                    guess = _estimate_tokens(batch)
                    usage, estimated = Usage(guess, 0, guess, True), True
                prompt, total = prompt + usage.prompt_tokens, total + usage.total_tokens
        if len({len(v) for v in vectors}) != 1:
            raise ModelException(LLMErrorCode.ERROR_GENERIC, message="provider returned vectors of different lengths")
        self.last_usage = Usage(prompt, 0, total, estimated)
        return vectors, total

    def encode_queries(self, text: str) -> tuple[list[float], int]:
        vectors, tokens = self.encode([text])
        return vectors[0], tokens


class _OpenAISdkEmbed(Base):
    def _make(self, openai: Any, http: httpx.Client) -> Any:
        raise NotImplementedError

    @contextlib.contextmanager
    def _open(self) -> Iterator[Any]:
        import openai

        http = self._http()
        client = self._make(openai, http)
        try:
            yield client
        finally:
            with contextlib.suppress(Exception):
                client.close()
            http.close()

    def _embed(self, client: Any, batch: list[str]) -> tuple[list[list[float]], Usage | None]:
        response = client.embeddings.create(model=self.model_name, input=batch, encoding_format="float")
        rows = sorted(response.data, key=lambda row: row.index)
        return [[float(x) for x in row.embedding] for row in rows], usage_from(getattr(response, "usage", None))


class OpenAIEmbed(_OpenAISdkEmbed):
    """OpenAI, OpenRouter and any OpenAI-compatible endpoint (LLM-03)."""

    def _make(self, openai: Any, http: httpx.Client) -> Any:
        return openai.OpenAI(api_key=self._api_key or _PLACEHOLDER_KEY, base_url=self.api_base, timeout=self.timeout, max_retries=0, http_client=http)


class AzureEmbed(_OpenAISdkEmbed):
    """Azure OpenAI: ``/openai/deployments/<deployment>/embeddings?api-version=...`` with the ``api-key`` header (LLM-04)."""

    def _check_target(self, validated: ValidatedUrl | None) -> ValidatedUrl | None:
        if not self.api_version:
            raise ModelException(LLMErrorCode.ERROR_INVALID_REQUEST, message="api_version is required for this provider")
        return super()._check_target(validated)

    def _make(self, openai: Any, http: httpx.Client) -> Any:
        return openai.AzureOpenAI(
            azure_endpoint=self.api_base,
            azure_deployment=self.model_name,
            api_version=self.api_version,
            api_key=self._api_key or _PLACEHOLDER_KEY,
            timeout=self.timeout,
            max_retries=0,
            http_client=http,
        )


class OllamaEmbed(Base):
    """Ollama native ``POST /api/embed`` on a base URL without ``/v1``; tokens come from ``prompt_eval_count`` (LLM-05)."""

    @contextlib.contextmanager
    def _open(self) -> Iterator[Any]:
        import ollama

        key = self._api_key

        def set_authorization(request: httpx.Request) -> None:
            # ollama reads OLLAMA_API_KEY from the environment; a request to a tenant-chosen host must carry only the tenant's key.
            if key:
                request.headers["authorization"] = f"Bearer {key}"
            elif "authorization" in request.headers:
                del request.headers["authorization"]

        client = ollama.Client(host=self.api_base, timeout=self.timeout, follow_redirects=False, event_hooks={"request": [set_authorization]})
        try:
            yield client
        finally:
            with contextlib.suppress(Exception):
                client.close()

    def _embed(self, client: Any, batch: list[str]) -> tuple[list[list[float]], Usage | None]:
        response = client.embed(model=self.model_name, input=batch)
        count = getattr(response, "prompt_eval_count", None)
        usage = usage_from({"prompt_tokens": count}) if isinstance(count, int) else None
        return [[float(x) for x in row] for row in response.embeddings], usage


def build_embedder(
    spec: ProviderSpec,
    model_name: str,
    api_key: str | None,
    api_base: str | None,
    api_version: str | None = None,
    *,
    llm_settings: LlmSettings,
    allow_private: bool,
    deny_hosts: Collection[str] = (),
    sleep: Callable[[float], object] = time.sleep,
    timeout: float | None = None,
) -> Base:
    """Pick the driver for ``spec``. Construction does no I/O; the target is validated on the first ``encode``."""
    kind: type[Base]
    if spec.name == Provider.AZURE_OPENAI:
        kind = AzureEmbed
    elif spec.name == Provider.OLLAMA:
        kind = OllamaEmbed
    else:
        kind = OpenAIEmbed
    return kind(
        spec, model_name, api_key, api_base, api_version,
        llm_settings=llm_settings, allow_private=allow_private, deny_hosts=deny_hosts, sleep=sleep, timeout=timeout,
    )  # fmt: skip
