"""Named, bounded executors for blocking work started from request handlers (plan 03-12, TEN-13).

The event loop's default executor is never used for request work: it is shared by every ``to_thread`` caller (health probes,
the superuser seed), so one stalled MySQL, provider or storage call could park all of them. Each concern gets its own small pool
instead, and a stall can occupy at most that pool.

``run_blocking`` puts an explicit deadline on every call. A worker thread that is already inside a driver cannot be cancelled: on
timeout the caller stops waiting and gets a typed error, but the thread runs on until its own driver timeout. Service-level
timeouts must therefore sit below the handler timeout (the provider service caps each test call at 20 s, the handler at 50 s), so a
late worker finishes quickly and its result is simply dropped.
"""
from __future__ import annotations

import asyncio
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import TypeVar

from api.db.services.service_errors import Kind, ServiceError
from api.utils import reasons

T = TypeVar("T")

DB_EXECUTOR = ThreadPoolExecutor(max_workers=16, thread_name_prefix="db")
PROVIDER_EXECUTOR = ThreadPoolExecutor(max_workers=8, thread_name_prefix="provider")
DOCSTORE_EXECUTOR = ThreadPoolExecutor(max_workers=8, thread_name_prefix="docstore")
STORAGE_EXECUTOR = ThreadPoolExecutor(max_workers=8, thread_name_prefix="storage")


async def run_blocking(executor: ThreadPoolExecutor, fn: Callable[..., T], *args: object, timeout: float) -> T:  # noqa: ASYNC109 - the explicit deadline is the contract
    """Run ``fn(*args)`` on ``executor`` and wait at most ``timeout`` seconds.

    An exception raised by ``fn`` propagates unchanged. A missed deadline raises ``ServiceError`` (TIMEOUT) with reason
    ``provider_timeout`` for the provider pool and ``operation_timeout`` for the others. The wait is on the future itself, so a
    ``TimeoutError`` raised inside ``fn`` is never mistaken for a missed deadline.
    """
    loop = asyncio.get_running_loop()
    future = loop.run_in_executor(executor, fn, *args)
    done, _pending = await asyncio.wait({future}, timeout=timeout)
    if not done:
        future.cancel()  # drops the job if it has not started; a running thread cannot be stopped
        if executor is PROVIDER_EXECUTOR:
            raise ServiceError(Kind.TIMEOUT, reasons.PROVIDER_TIMEOUT, "the provider did not answer in time")
        raise ServiceError(Kind.TIMEOUT, reasons.OPERATION_TIMEOUT, "the operation took too long")
    return future.result()
