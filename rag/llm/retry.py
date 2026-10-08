"""The one bounded retry loop for model calls (plan 03-05, LLM-19, Pitfall 9).

SDK retries are switched off in the drivers (``num_retries=0``, ``max_retries=0``) so this is the only place a call is
repeated. Only a ``ModelException`` marked ``retryable`` (rate limit, timeout) is retried; everything else propagates
unchanged. The sleep function is injected so tests never wait. Logging carries only the attempt number and the code, never
exception text.
"""
from __future__ import annotations

import asyncio
import logging
import random
import time
from collections.abc import Awaitable, Callable
from typing import TypeVar

from rag.llm.errors import LLMErrorCode, ModelException

logger = logging.getLogger(__name__)

T = TypeVar("T")
BASE_DELAY = 0.5
MAX_DELAY = 8.0
MAX_RETRY_AFTER = 30.0  # a hostile or buggy Retry-After must not park a worker for minutes


def retry_delay(attempt: int, retry_after: float | None, *, jitter: float = 0.25) -> float:
    """``min(8, 0.5 * 2**attempt)`` plus up to ``jitter`` seconds, raised to ``retry_after`` (itself capped) when larger."""
    delay = min(MAX_DELAY, BASE_DELAY * 2 ** min(attempt, 16)) + (random.uniform(0.0, jitter) if jitter > 0 else 0.0)  # noqa: S311 - jitter, not security
    if retry_after is not None and retry_after > 0:
        delay = max(delay, min(retry_after, MAX_RETRY_AFTER))
    return delay


def _exhausted(last: ModelException) -> ModelException:
    wrapped = ModelException(
        LLMErrorCode.ERROR_MAX_RETRIES,
        provider_status=last.provider_status,
        retry_after=last.retry_after,
        message=last.safe_message,
    )
    wrapped.__cause__ = last
    return wrapped


def run_with_retries(call: Callable[[], T], *, max_retries: int, sleep: Callable[[float], object] = time.sleep) -> T:
    attempt = 0
    while True:
        try:
            return call()
        except ModelException as exc:
            if not exc.retryable or max_retries <= 0:
                raise
            if attempt >= max_retries:
                raise _exhausted(exc) from exc
            logger.warning("model call retry attempt=%d code=%s", attempt + 1, exc.code.value)
            sleep(retry_delay(attempt, exc.retry_after))
            attempt += 1


async def arun_with_retries(
    call: Callable[[], Awaitable[T]],
    *,
    max_retries: int,
    sleep: Callable[[float], Awaitable[object]] = asyncio.sleep,
) -> T:
    attempt = 0
    while True:
        try:
            return await call()
        except ModelException as exc:
            if not exc.retryable or max_retries <= 0:
                raise
            if attempt >= max_retries:
                raise _exhausted(exc) from exc
            logger.warning("model call retry attempt=%d code=%s", attempt + 1, exc.code.value)
            await sleep(retry_delay(attempt, exc.retry_after))
            attempt += 1
