"""LLMBundle: the one way later features call a workspace's chat or embedding model (LLM-14, LLM-15, LLM-21; plan 03-11).

``LLMBundle(tenant_id, "model@provider" | "model@instance@provider", "chat" | "embedding")`` resolves the composite id to the
tenant's own credential row, opens the sealed key in memory, builds the driver once and exposes ``chat``, ``chat_streamly``,
their async twins, ``encode`` and ``encode_queries``. Callers never see a key.

Contracts:

* Usage: every successful call resets ``last_usage`` first and then reports the provider's usage (an estimate only when the
  provider sent none) to ``tenant_llm.used_tokens`` through one atomic statement, plus one structured log line. A stream is
  counted once, after it ends; a failed call, or a stream the consumer abandons, adds nothing.
* Errors: ``ModelException`` never escapes. Every provider failure is a ``ServiceError`` with the machine reasons the provider
  service uses (``provider_refused``, ``provider_rate_limited``, ``provider_timeout``, ``provider_unreachable``); a model the
  workspace does not have is ``model_unavailable``; an unconfigured or tampered key store is ``key_store_unavailable`` or
  ``key_unreadable``. Provider text reaches a message only as the sanitized ``safe_message`` of a refusal, with the key
  scrubbed out again.
* Dimension: ``encode`` compares vector lengths with ``expected_dimension`` and raises ``dimension_mismatch`` before usage is
  recorded, so a provider that changes its vector size cannot corrupt an index.
* Blocking: the drivers are blocking. Call the sync methods from a worker thread (a bounded executor owned by the caller); the
  async methods run on the caller's loop. The bundle never touches the loop's default executor. Construction reads one
  credential row, so build the bundle from the same worker thread.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator, Mapping
from typing import Any

from peewee import PeeweeException

from api.db.services import tenant_llm_service
from api.db.services.service_errors import Kind, ServiceError
from api.utils import reasons
from common.model_ref import InvalidModelRef, ModelRef, parse_model_ref
from common.settings import Settings, get_settings
from rag.llm import ProviderSpec, resolve_provider
from rag.llm.chat_model import LiteLLMBase
from rag.llm.embedding_model import Base as EmbeddingBase
from rag.llm.embedding_model import build_embedder
from rag.llm.errors import LLMErrorCode, ModelException
from rag.llm.stream import Usage
from rag.llm.sync_loop import PrivateLoop

logger = logging.getLogger(__name__)

MODEL_TYPES = ("chat", "embedding")
_REFUSAL_CODES = frozenset(
    {
        LLMErrorCode.ERROR_AUTHENTICATION,
        LLMErrorCode.ERROR_INVALID_REQUEST,
        LLMErrorCode.ERROR_QUOTA,
        LLMErrorCode.ERROR_CONTENT_FILTER,
        LLMErrorCode.ERROR_MODEL,
    }
)
_RATE_LIMIT_STATUSES = frozenset({429, 503})
_SCRUBBED = "***"
_FALLBACK_REFUSAL = "the provider rejected the request"
_UNAVAILABLE_MODEL = "that model is not available in this workspace"

Scrub = Callable[[str], str]


# ----------------------------------------------------------------------------- pure helpers


def split_usage(usage: Usage | None) -> tuple[int, int, int]:
    """``(prompt, completion, total)``; all zero for no usage."""
    return (0, 0, 0) if usage is None else (usage.prompt_tokens, usage.completion_tokens, usage.total_tokens)


def merge_usage(a: Usage | None, b: Usage | None) -> Usage:
    """Add two usages. The result is flagged estimated only when every part present was estimated."""
    parts = [u for u in (a, b) if u is not None]
    if not parts:
        return Usage(0, 0, 0, False)
    return Usage(
        sum(u.prompt_tokens for u in parts),
        sum(u.completion_tokens for u in parts),
        sum(u.total_tokens for u in parts),
        all(u.estimated for u in parts),
    )


def usage_log_fields(tenant_id: str, provider: str, model: str, usage: Usage) -> dict[str, Any]:
    """The structured fields of the usage line. No name contains ``token``: the log redactor masks any such field."""
    return {
        "tenant": tenant_id,
        "provider": provider,
        "model": model,
        "usage_in": usage.prompt_tokens,
        "usage_out": usage.completion_tokens,
        "usage_total": usage.total_tokens,
        "estimated": usage.estimated,
    }


def bundle_error(exc: ModelException, scrub: Scrub | None = None) -> ServiceError:
    """Map a driver failure to a typed, safe ``ServiceError``. Only a refusal shows the (sanitized, scrubbed) provider text."""
    code, status = exc.code, exc.provider_status
    if code == LLMErrorCode.ERROR_RATE_LIMIT or status in _RATE_LIMIT_STATUSES:
        return ServiceError(Kind.UNAVAILABLE, reasons.PROVIDER_RATE_LIMITED, "the provider is limiting requests, try again shortly", retry_after=exc.retry_after)
    if code in _REFUSAL_CODES:
        text = exc.safe_message
        return ServiceError(Kind.INVALID, reasons.PROVIDER_REFUSED, (scrub(text) if scrub else text) or _FALLBACK_REFUSAL)
    if code == LLMErrorCode.ERROR_TIMEOUT or (code == LLMErrorCode.ERROR_MAX_RETRIES and status is None):
        return ServiceError(Kind.TIMEOUT, reasons.PROVIDER_TIMEOUT, "the provider did not answer in time")
    return ServiceError(Kind.BAD_GATEWAY, reasons.PROVIDER_UNREACHABLE, "the provider could not be reached")


def _unavailable() -> ServiceError:
    return ServiceError(Kind.NOT_FOUND, reasons.MODEL_UNAVAILABLE, _UNAVAILABLE_MODEL)


def _scrubber(key: str | None) -> Scrub:
    """A closure over the key, so the bundle can mask it in provider text without keeping it as an attribute."""
    if not key:
        return lambda text: text
    return lambda text: text.replace(key, _SCRUBBED)


# ----------------------------------------------------------------------------- bundle


class LLMBundle:
    def __init__(
        self,
        tenant_id: str,
        model_id: str,
        model_type: str,
        *,
        settings: Settings | None = None,
        expected_dimension: int | None = None,
        sleep: Callable[[float], Awaitable[None]] | None = None,
    ) -> None:
        if model_type not in MODEL_TYPES:
            raise ValueError("model_type must be 'chat' or 'embedding'")
        try:
            ref = parse_model_ref(model_id)
        except InvalidModelRef:
            raise _unavailable() from None
        self.tenant_id = tenant_id
        self.model_type = model_type
        self.expected_dimension = expected_dimension
        self._settings = settings or get_settings()
        self._sleep = sleep
        self._last_usage: Usage | None = None
        # get_credential opens its own connection context; wrapping it would close the connection on the inner exit.
        credential = tenant_llm_service.get_credential(self._settings.llm, tenant_id, ref, model_type)
        if credential is None:
            raise _unavailable()
        self._spec: ProviderSpec = resolve_provider(credential.provider)
        self.ref = ModelRef(credential.model, credential.instance, self._spec.name)
        self._scrub = _scrubber(credential.api_key)
        self._driver: LiteLLMBase | EmbeddingBase = self._build(credential.api_key, credential.api_base, credential.api_version)

    def _build(self, api_key: str | None, api_base: str | None, api_version: str | None) -> LiteLLMBase | EmbeddingBase:
        llm = self._settings.llm
        common: dict[str, Any] = {
            "llm_settings": llm,
            "allow_private": llm.allow_private_base_urls,
            "deny_hosts": tenant_llm_service.internal_hosts(self._settings),
        }
        if self.model_type == "chat":
            return LiteLLMBase(self._spec, self.ref.model, api_key, api_base, api_version, sleep=self._sleep or asyncio.sleep, **common)
        return build_embedder(self._spec, self.ref.model, api_key, api_base, api_version, sleep=self._sync_sleep, **common)

    def _sync_sleep(self, delay: float) -> None:
        """The embedding driver retries synchronously; an injected async sleep is driven on a private loop."""
        if self._sleep is None:
            time.sleep(delay)
            return
        loop = PrivateLoop()
        try:
            loop.run(self._sleep(delay))
        finally:
            loop.close()

    def __repr__(self) -> str:
        return f"LLMBundle(provider={self._spec.name!r}, model={self.ref.model!r}, type={self.model_type!r})"

    @property
    def provider(self) -> str:
        return self._spec.name

    @property
    def model(self) -> str:
        return self.ref.model

    @property
    def last_usage(self) -> Usage | None:
        return self._last_usage

    # ------------------------------------------------------------------------- shared steps

    def _chat_driver(self) -> LiteLLMBase:
        if not isinstance(self._driver, LiteLLMBase):
            raise TypeError("this bundle was built for embeddings, not chat")
        return self._driver

    def _embedder(self) -> EmbeddingBase:
        if not isinstance(self._driver, EmbeddingBase):
            raise TypeError("this bundle was built for chat, not embeddings")
        return self._driver

    def _reset_last_usage(self) -> None:
        self._last_usage = None
        self._driver.last_usage = None

    def _failure(self, exc: ModelException) -> ServiceError:
        return bundle_error(exc, self._scrub)

    def _report_usage(self, usage: Usage | None) -> None:
        """Count a finished, successful call: one atomic counter update and one log line. Never raises for storage errors."""
        if usage is None:
            return
        self._last_usage = usage
        try:
            tenant_llm_service.add_used_tokens(self.tenant_id, self._spec.name, self.ref.model, usage.total_tokens)
        except PeeweeException:
            # The provider call already succeeded and was paid for; losing the answer would not recover the count.
            logger.error("llm usage not recorded", extra={"tenant": self.tenant_id, "provider": self._spec.name, "model": self.ref.model})
        logger.info("llm usage", extra=usage_log_fields(self.tenant_id, self._spec.name, self.ref.model, usage))

    def _check_dimension(self, vectors: list[list[float]]) -> None:
        expected = self.expected_dimension
        if expected is not None and any(len(v) != expected for v in vectors):
            raise ServiceError(Kind.INVALID, reasons.DIMENSION_MISMATCH, "the model returned vectors of a different size")

    # ------------------------------------------------------------------------- chat

    def chat(self, system: str, history: list[dict[str, Any]], gen_conf: Mapping[str, Any] | None = None) -> str:
        driver = self._chat_driver()
        self._reset_last_usage()
        try:
            text, _ = driver.chat(system, history, gen_conf)
        except ModelException as exc:
            raise self._failure(exc) from None
        self._report_usage(driver.last_usage)
        return text

    def chat_streamly(self, system: str, history: list[dict[str, Any]], gen_conf: Mapping[str, Any] | None = None) -> Iterator[str]:
        driver = self._chat_driver()
        self._reset_last_usage()
        try:
            with contextlib.closing(driver.chat_streamly(system, history, gen_conf)) as stream:
                yield from stream
        except ModelException as exc:
            raise self._failure(exc) from None
        self._report_usage(driver.last_usage)  # reached only when the stream ran to its end

    async def async_chat(self, system: str, history: list[dict[str, Any]], gen_conf: Mapping[str, Any] | None = None) -> str:
        driver = self._chat_driver()
        self._reset_last_usage()
        try:
            text, _ = await driver.async_chat(system, history, gen_conf)
        except ModelException as exc:
            raise self._failure(exc) from None
        self._report_usage(driver.last_usage)
        return text

    async def async_chat_streamly(self, system: str, history: list[dict[str, Any]], gen_conf: Mapping[str, Any] | None = None) -> AsyncIterator[str]:
        driver = self._chat_driver()
        self._reset_last_usage()
        try:
            async with contextlib.aclosing(driver.async_chat_streamly(system, history, gen_conf)) as stream:
                async for piece in stream:
                    yield piece
        except ModelException as exc:
            raise self._failure(exc) from None
        self._report_usage(driver.last_usage)

    # ------------------------------------------------------------------------- embeddings

    def encode(self, texts: list[str]) -> tuple[list[list[float]], int]:
        embedder = self._embedder()
        self._reset_last_usage()
        try:
            vectors, tokens = embedder.encode(texts)
        except ModelException as exc:
            raise self._failure(exc) from None
        self._check_dimension(vectors)
        self._report_usage(embedder.last_usage)
        return vectors, tokens

    def encode_queries(self, text: str) -> tuple[list[float], int]:
        vectors, tokens = self.encode([text])
        return vectors[0], tokens


__all__ = ["LLMBundle", "bundle_error", "merge_usage", "split_usage", "usage_log_fields"]
