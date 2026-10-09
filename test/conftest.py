"""Shared fixtures for the devRag test suite."""
from __future__ import annotations

import asyncio
import gc
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT


def stack_env(root: Path = REPO_ROOT) -> dict[str, str]:
    """Load KEY=VALUE pairs from docker/.env when present (used by integration tests)."""
    env_file = root / "docker" / ".env"
    values: dict[str, str] = {}
    if not env_file.is_file():
        return values
    for raw in env_file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip("'\"")
    return values


@pytest.fixture
def gc_at_loop_teardown(monkeypatch):
    """Run a full GC right where the private loop is wound down: the moment an unclosed async generator gets finalized.

    The suite runs with ``filterwarnings=error``, so a generator that is finalized on a dead loop fails the test it lands in;
    without this fixture that happens only when allocation pressure triggers the collector at that instant (intermittent).
    """
    real_shutdown, real_close = asyncio.BaseEventLoop.shutdown_asyncgens, asyncio.BaseEventLoop.close

    async def shutdown_asyncgens(self):
        gc.collect()
        await real_shutdown(self)

    def close(self):
        gc.collect()
        real_close(self)

    monkeypatch.setattr(asyncio.BaseEventLoop, "shutdown_asyncgens", shutdown_asyncgens)
    monkeypatch.setattr(asyncio.BaseEventLoop, "close", close)
