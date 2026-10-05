"""Readiness polling helper for tests."""
from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any


def wait_until(
    predicate: Callable[[], Any],
    timeout: float = 60.0,
    interval: float = 0.5,
    describe: Callable[[], str] = lambda: "",
) -> Any:
    """Poll ``predicate`` until it returns a truthy value and return that value.

    This is the only permitted polling site in Python tests: no other test code
    may call a fixed sleep. Raises TimeoutError (with the timeout and the last
    observed value) if the predicate never becomes truthy.
    """
    deadline = time.monotonic() + timeout
    last: Any = None
    while True:
        last = predicate()
        if last:
            return last
        if time.monotonic() >= deadline:
            extra = describe()
            raise TimeoutError(f"condition not met within {timeout}s; last={last!r}" + (f"; {extra}" if extra else ""))
        time.sleep(interval)
