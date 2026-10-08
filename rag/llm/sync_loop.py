"""A private event loop for the synchronous chat wrappers (plan 03-05, LLM-04).

``Base.chat`` and ``Base.chat_streamly`` are sync facades over the async drivers. The httpx/httpcore response body is an async
generator that is routinely left suspended (the SDK stops reading at ``[DONE]``, or the consumer stops early). While a loop is
alive its asyncgen hooks adopt such a generator, and when the collector finalizes it the hook only *schedules* an ``aclose()``
task with ``call_soon_threadsafe``. A loop that is closed before that task has run destroys it ("Task was destroyed but it is
pending"), and the generator is then finalized on a dead loop (``PytestUnraisableExceptionWarning`` under ``-W error``).

``PrivateLoop.close`` therefore settles the loop before closing it: it lets queued hook callbacks turn into tasks, closes every
tracked async generator, and cancels and awaits whatever is left (``asyncio.run`` does the last two but not the first, and not
for a loop that stays open between ``__anext__`` calls). Callers must close the underlying stream (``aclose``) first; this is
the backstop for the generators the SDKs do not close themselves.
"""
from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable
from typing import TypeVar

T = TypeVar("T")
_SETTLE_ROUNDS = 3  # each round can expose tasks that an earlier cancellation scheduled
_YIELDS = 3  # loop iterations needed for call_soon_threadsafe(create_task) -> first step -> completion


async def _drain_ready() -> None:
    for _ in range(_YIELDS):
        await asyncio.sleep(0)


async def _cancel_pending() -> None:
    current = asyncio.current_task()
    pending = [t for t in asyncio.all_tasks() if t is not current and not t.done()]
    for task in pending:
        task.cancel()
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)


class PrivateLoop:
    """One event loop owned by one synchronous call; ``run`` drives awaitables, ``close`` settles and closes it."""

    def __init__(self) -> None:
        self._loop = asyncio.new_event_loop()

    def run(self, awaitable: Awaitable[T]) -> T:
        return self._loop.run_until_complete(awaitable)

    def close(self) -> None:
        loop = self._loop
        if loop.is_closed():
            return
        try:
            for _ in range(_SETTLE_ROUNDS):
                with contextlib.suppress(Exception):  # cleanup must not mask the caller's result or error
                    loop.run_until_complete(_drain_ready())
                    loop.run_until_complete(loop.shutdown_asyncgens())
                    loop.run_until_complete(_drain_ready())
                    loop.run_until_complete(_cancel_pending())
                if not any(not t.done() for t in asyncio.all_tasks(loop)):
                    break
        finally:
            loop.close()
