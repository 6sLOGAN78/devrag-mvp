"""Chat drivers (plan 03-05, LLM-01, LLM-04, LLM-05, LLM-17..20, D-15).

``Base`` is the driver interface (``chat``, ``async_chat``, ``chat_streamly``, ``async_chat_streamly``, ``last_usage``);
``LiteLLMBase`` implements it for all five providers through ``litellm.acompletion``. Error types, the retry loop and the
stream sanitizer live in ``rag.llm.errors``, ``rag.llm.retry`` and ``rag.llm.stream``; this module only composes them.

Safety rules the driver enforces:

* litellm is imported lazily (``_litellm``): it is heavy and must not load at app start (T-03-05-05).
* Each call builds its own ``httpx`` client with ``follow_redirects=False`` and passes it to litellm, so a provider redirect
  to an internal host is never followed; the base URL is re-validated by ``common.net.url_guard`` before every attempt
  (T-03-05-01).
* SDK retries are off (``num_retries=0``, ``max_retries=0``); ``arun_with_retries`` is the only retry loop (T-03-05-03).
* Failure text comes from the captured response body (``error.message``, truncated and redacted by ``ModelException``), never
  from the string form of a provider exception, which can echo the key (T-03-05-02, Pitfall 14).
* Only whitelisted generation parameters are forwarded (LLM-17). ``extra_headers`` can override ``Authorization``, so it is
  dropped unless the driver was built by server code with ``trust_extra_headers=True`` (T-03-05-04); it never comes from a
  request body.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import sys
from collections.abc import AsyncIterator, Awaitable, Callable, Collection, Iterator, Mapping
from dataclasses import dataclass
from typing import Any

import httpx

from common.net.url_guard import UnsafeBaseUrl, ValidatedUrl, assert_unchanged, validate_base_url
from common.settings import LlmSettings
from rag.llm import ProviderSpec
from rag.llm.errors import LLMErrorCode, ModelException
from rag.llm.model_meta import REASONING_MODEL
from rag.llm.retry import arun_with_retries
from rag.llm.stream import StreamSanitizer, Usage, strip_control, usage_from

logger = logging.getLogger(__name__)

ALLOWED_GEN_CONF_KEYS = frozenset(
    {
        "temperature", "max_completion_tokens", "top_p", "stream", "stream_options", "stop", "n",
        "presence_penalty", "frequency_penalty", "functions", "function_call", "logit_bias", "user",
        "response_format", "seed", "tools", "tool_choice", "logprobs", "top_logprobs", "extra_headers",
    }
)  # fmt: skip
_BODY_LIMIT = 65536
_PLACEHOLDER_KEY = "not-needed"  # providers that need no key still require the SDK to be given one
_litellm_ready = False


def _litellm() -> Any:
    """Import litellm on first use and silence its debug output."""
    global _litellm_ready
    import litellm

    if not _litellm_ready:
        litellm.suppress_debug_info = True
        litellm.set_verbose = False
        _litellm_ready = True
    return litellm


def sanitize_gen_conf(conf: Mapping[str, Any] | None, model_name: str) -> dict[str, Any]:
    """Keep whitelisted keys (LLM-17). Reasoning models lose ``temperature`` and use ``max_completion_tokens`` (LLM-18).

    ``max_tokens`` is not on the documented whitelist; ordinary models keep it as the one accepted length limit.
    """
    source = conf or {}
    out = {k: v for k, v in source.items() if k in ALLOWED_GEN_CONF_KEYS}
    if REASONING_MODEL.match(model_name):
        out.pop("temperature", None)
        if "max_tokens" in source:
            out.setdefault("max_completion_tokens", source["max_tokens"])
    elif "max_tokens" in source:
        out["max_tokens"] = source["max_tokens"]
    return out


@dataclass
class _Capture:
    """What the response hook saw of the last failed HTTP response."""

    status: int | None = None
    body: bytes | None = None
    retry_after: float | None = None

    def reset(self) -> None:
        self.status = self.body = self.retry_after = None


def _retry_after(value: str | None) -> float | None:
    try:
        seconds = float(value) if value is not None else None
    except ValueError:
        return None  # an HTTP-date form is ignored; the backoff schedule applies
    return seconds if seconds is not None and seconds >= 0 else None


def _is_timeout(exc: BaseException, mods: Any | None) -> bool:
    return isinstance(exc, (TimeoutError, httpx.TimeoutException)) or (mods is not None and isinstance(exc, mods.Timeout))


def _status_code(status: int | None, body_code: str | None) -> tuple[LLMErrorCode, bool]:
    if status in (401, 403):
        return LLMErrorCode.ERROR_AUTHENTICATION, False
    if status == 429:
        return LLMErrorCode.ERROR_RATE_LIMIT, True
    if status == 408:
        return LLMErrorCode.ERROR_TIMEOUT, True
    if status is not None and 400 <= status < 500:
        return (LLMErrorCode.ERROR_CONTENT_FILTER if body_code == "content_filter" else LLMErrorCode.ERROR_INVALID_REQUEST), False
    if status is not None and status >= 500:
        return LLMErrorCode.ERROR_SERVER, False
    return LLMErrorCode.ERROR_GENERIC, False


def classify_exception(exc: BaseException, capture: _Capture | None = None) -> ModelException:
    """Map a provider/SDK exception to a ``ModelException`` by type and status code, never by message text.

    The captured response body (if any) supplies ``safe_message``; the exception's own text is discarded.
    """
    if isinstance(exc, ModelException):
        return exc
    mods = sys.modules.get("litellm.exceptions")
    body = capture.body if capture else None
    retry_after = capture.retry_after if capture else None
    status = capture.status if capture and capture.status else getattr(exc, "status_code", None)
    status = status if isinstance(status, int) else None
    if _is_timeout(exc, mods):
        return ModelException(LLMErrorCode.ERROR_TIMEOUT, retryable=True, provider_status=status, retry_after=retry_after, body=body)
    body_code = getattr(exc, "code", None)
    if mods is not None:
        if isinstance(exc, mods.ContentPolicyViolationError):
            return ModelException(LLMErrorCode.ERROR_CONTENT_FILTER, provider_status=status, body=body)
        # litellm reports a refused or reset connection as a 500 InternalServerError or APIConnectionError. No error response was
        # captured, so the provider never answered: that is a connection failure, not a server error.
        transport_like = tuple(getattr(mods, n) for n in ("InternalServerError", "APIConnectionError", "ServiceUnavailableError") if hasattr(mods, n))
        if capture is not None and capture.status is None and isinstance(exc, transport_like):
            return ModelException(LLMErrorCode.ERROR_CONNECTION)
    if status is None and isinstance(exc, (httpx.TransportError, OSError)):
        return ModelException(LLMErrorCode.ERROR_CONNECTION)
    if status is None:
        return ModelException(LLMErrorCode.ERROR_GENERIC)
    code, retryable = _status_code(status, body_code if isinstance(body_code, str) else None)
    return ModelException(code, retryable=retryable, provider_status=status, retry_after=retry_after, body=body)


def _count_tokens(text: str) -> int:
    try:
        import tiktoken

        return len(tiktoken.get_encoding("cl100k_base").encode(text, disallowed_special=()))
    except Exception:  # noqa: BLE001 - the vocabulary may be unavailable offline; a rough estimate is still useful
        return max(1, len(text) // 4)


def _estimate_usage(messages: list[dict[str, Any]], answer: str) -> Usage:
    prompt = sum(_count_tokens(str(m.get("content") or "")) for m in messages)
    completion = _count_tokens(answer)
    return Usage(prompt, completion, prompt + completion, True)


def _reported_or_estimated(reported: Usage | None, messages: list[dict[str, Any]], answer: str) -> Usage:
    """Trust provider usage unless it is missing or all zero for a non-empty answer (some gateways send zeros)."""
    if reported is not None and (reported.total_tokens > 0 or not answer):
        return reported
    return _estimate_usage(messages, answer)


class Base:
    """Chat driver interface. Subclasses implement the two async methods; the sync ones wrap them."""

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
        sleep: Callable[[float], Awaitable[object]] = asyncio.sleep,
        timeout: float | None = None,
        trust_extra_headers: bool = False,
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
        self.timeout = float(timeout if timeout is not None else llm_settings.chat_timeout_seconds)
        self.trust_extra_headers = trust_extra_headers
        self.last_usage: Usage | None = None

    def __repr__(self) -> str:
        return f"{type(self).__name__}(provider={self.spec.name!r}, model={self.model_name!r})"

    async def async_chat(self, system: str, history: list[dict[str, Any]], gen_conf: Mapping[str, Any] | None = None) -> tuple[str, int]:
        raise NotImplementedError

    def async_chat_streamly(self, system: str, history: list[dict[str, Any]], gen_conf: Mapping[str, Any] | None = None) -> AsyncIterator[str]:
        raise NotImplementedError

    @staticmethod
    def _require_no_loop() -> None:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return
        raise RuntimeError("synchronous chat called inside a running event loop; await the async method instead")

    def chat(self, system: str, history: list[dict[str, Any]], gen_conf: Mapping[str, Any] | None = None) -> tuple[str, int]:
        self._require_no_loop()
        return asyncio.run(self.async_chat(system, history, gen_conf))

    def chat_streamly(self, system: str, history: list[dict[str, Any]], gen_conf: Mapping[str, Any] | None = None) -> Iterator[str]:
        self._require_no_loop()
        loop = asyncio.new_event_loop()
        agen = self.async_chat_streamly(system, history, gen_conf)
        try:
            while True:
                try:
                    yield loop.run_until_complete(agen.__anext__())
                except StopAsyncIteration:
                    return
        finally:
            with contextlib.suppress(Exception):
                loop.run_until_complete(agen.aclose())  # type: ignore[attr-defined]
                loop.run_until_complete(loop.shutdown_asyncgens())
            loop.close()


class _Session:
    """One call's HTTP client(s): no redirects, response hook capturing failed bodies, closed on exit."""

    def __init__(self, timeout: float) -> None:
        self.capture = _Capture()
        self.http = httpx.AsyncClient(follow_redirects=False, timeout=timeout, event_hooks={"response": [self._on_response]})

    async def _on_response(self, response: httpx.Response) -> None:
        if response.status_code >= 300:
            await response.aread()
            self.capture.status = response.status_code
            self.capture.body = response.content[:_BODY_LIMIT]
            self.capture.retry_after = _retry_after(response.headers.get("retry-after"))

    async def __aenter__(self) -> _Session:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.http.aclose()


class LiteLLMBase(Base):
    def _check_target(self, validated: ValidatedUrl | None) -> ValidatedUrl | None:
        """Validate the base URL before an attempt (and re-validate on later ones, DNS rebinding)."""
        if not self.api_base:
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

    def _model_string(self) -> str:
        return f"{self.spec.litellm_prefix}{self.model_name}"

    def _client_for(self, litellm: Any, session: _Session) -> Any:
        if self.spec.ollama_style:
            from litellm.llms.custom_httpx.http_handler import AsyncHTTPHandler

            handler = AsyncHTTPHandler(timeout=self.timeout)
            handler.client = session.http  # replaces litellm's redirect-following client for this call
            return handler
        import openai

        key = self._api_key or _PLACEHOLDER_KEY
        if self.spec.requires_api_version:
            return openai.AsyncAzureOpenAI(api_key=key, azure_endpoint=self.api_base, api_version=self.api_version, max_retries=0, http_client=session.http)
        return openai.AsyncOpenAI(api_key=key, base_url=self.api_base, max_retries=0, http_client=session.http)

    def _messages(self, system: str, history: list[dict[str, Any]]) -> list[dict[str, Any]]:
        head = [{"role": "system", "content": system}] if system else []
        return [*head, *history]

    def _call_kwargs(self, messages: list[dict[str, Any]], gen_conf: Mapping[str, Any] | None, client: Any, *, stream: bool) -> dict[str, Any]:
        conf = sanitize_gen_conf(gen_conf, self.model_name)
        for managed in ("stream", "stream_options"):
            conf.pop(managed, None)
        if not self.trust_extra_headers:
            conf.pop("extra_headers", None)
        kwargs: dict[str, Any] = {
            **conf,
            "model": self._model_string(),
            "messages": messages,
            "api_base": self.api_base,
            "timeout": self.timeout,
            "num_retries": 0,
            "drop_params": True,
            "client": client,
        }
        if not self.spec.ollama_style:
            kwargs["api_key"] = self._api_key or _PLACEHOLDER_KEY
        if self.spec.requires_api_version:
            kwargs["api_version"] = self.api_version
        if stream:
            kwargs.update(stream=True, stream_options={"include_usage": True})
        return kwargs

    async def _attempt(self, session: _Session, state: dict[str, Any], messages: list[dict[str, Any]], gen_conf: Mapping[str, Any] | None, *, stream: bool) -> Any:
        state["validated"] = self._check_target(state.get("validated"))
        session.capture.reset()
        failure: ModelException | None = None
        try:
            litellm = _litellm()
            return await litellm.acompletion(**self._call_kwargs(messages, gen_conf, self._client_for(litellm, session), stream=stream))
        except Exception as exc:  # noqa: BLE001 - every provider/SDK failure is mapped below
            failure = classify_exception(exc, session.capture)
        logger.warning("model call failed provider=%s model=%s code=%s", self.spec.name, self.model_name, failure.code.value)
        raise failure

    async def async_chat(self, system: str, history: list[dict[str, Any]], gen_conf: Mapping[str, Any] | None = None) -> tuple[str, int]:
        messages, state = self._messages(system, history), {}
        async with _Session(self.timeout) as session:
            response = await arun_with_retries(
                lambda: self._attempt(session, state, messages, gen_conf, stream=False), max_retries=self.llm_settings.max_retries, sleep=self._sleep
            )
        choices = getattr(response, "choices", None) or []
        text = strip_control(getattr(getattr(choices[0], "message", None), "content", None) or "") if choices else ""
        self.last_usage = _reported_or_estimated(usage_from(getattr(response, "usage", None)), messages, text)
        return text, self.last_usage.total_tokens

    async def async_chat_streamly(self, system: str, history: list[dict[str, Any]], gen_conf: Mapping[str, Any] | None = None) -> AsyncIterator[str]:
        """Yield content deltas only. Opening the stream is retried; a failure mid-stream is raised, not replayed."""
        messages, state, sanitizer, shown = self._messages(system, history), {}, StreamSanitizer(), []
        async with _Session(self.timeout) as session:
            stream = await arun_with_retries(
                lambda: self._attempt(session, state, messages, gen_conf, stream=True), max_retries=self.llm_settings.max_retries, sleep=self._sleep
            )
            failure: ModelException | None = None
            try:
                async for chunk in stream:
                    piece = sanitizer.feed(chunk)
                    if piece:
                        shown.append(piece)
                        yield piece
            except Exception as exc:  # noqa: BLE001
                failure = classify_exception(exc, session.capture)
            finally:
                close = getattr(stream, "aclose", None)
                if close is not None:
                    with contextlib.suppress(Exception):
                        await close()
            if failure is not None:
                raise failure
        self.last_usage = _reported_or_estimated(sanitizer.usage, messages, "".join(shown))
