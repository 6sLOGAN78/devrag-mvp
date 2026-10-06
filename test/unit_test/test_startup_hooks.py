"""Startup hooks run on the loop that serves requests (WR-07, B-08)."""
from __future__ import annotations

import asyncio

import pytest
from quart import Quart
from quart.testing.app import LifespanError

import api.ragflow_server as server

pytestmark = pytest.mark.unit


@pytest.fixture
def hooks(monkeypatch):
    registry: list = []
    monkeypatch.setattr(server, "_HOOKS", registry)
    return registry


async def test_hooks_run_on_serving_loop_and_tasks_survive(hooks):
    seen: dict = {}

    async def async_hook():
        seen["loop"] = asyncio.get_running_loop()
        seen["task"] = asyncio.create_task(asyncio.sleep(30))

    server.register_startup_hook("async", async_hook)
    app = Quart(__name__)
    server.install_startup_hooks(app)
    async with app.test_app():
        assert seen["loop"] is asyncio.get_running_loop()
        await asyncio.sleep(0)
        assert not seen["task"].done() and not seen["task"].cancelled()
    seen["task"].cancel()


async def test_hooks_run_in_registration_order_sync_and_async(hooks):
    order: list[str] = []

    async def b():
        order.append("b")

    server.register_startup_hook("a", lambda: order.append("a"))
    server.register_startup_hook("b", b)
    server.register_startup_hook("c", lambda: order.append("c"))
    app = Quart(__name__)
    server.install_startup_hooks(app)
    async with app.test_app():
        assert order == ["a", "b", "c"]


async def test_raising_hook_aborts_startup(hooks):
    def bad():
        raise RuntimeError("hook failed")

    server.register_startup_hook("bad", bad)
    app = Quart(__name__)
    server.install_startup_hooks(app)
    with pytest.raises(LifespanError, match="hook failed"):
        async with app.test_app():
            pass


async def test_hooks_and_serve_steps_emitted_after_hooks(hooks, caplog):
    import logging

    order: list[str] = []
    server.register_startup_hook("h", lambda: order.append("hook"))
    app = Quart(__name__)
    server.install_startup_hooks(app)
    with caplog.at_level(logging.INFO, logger="ragflow.boot"):
        async with app.test_app():
            pass
    steps = [r.step for r in caplog.records if r.getMessage() == "boot.step"]
    assert steps == ["hooks", "serve"] and order == ["hook"]
