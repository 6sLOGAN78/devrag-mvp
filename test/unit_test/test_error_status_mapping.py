"""Unmapped HTTP statuses keep an envelope code of the same class (WR-08, R-63)."""
from __future__ import annotations

import pytest
from quart import Quart
from werkzeug.exceptions import HTTPException, abort, default_exceptions

from api.apps.errors import register_error_handlers

pytestmark = pytest.mark.unit

CLIENT_STATUSES = sorted(code for code, exc in default_exceptions.items() if 400 <= code < 500 and issubclass(exc, HTTPException))


def _app() -> Quart:
    app = Quart(__name__)
    register_error_handlers(app)

    @app.get("/abort/<int:status>")
    async def _abort(status: int):
        abort(status)

    @app.get("/boom")
    async def _boom():
        raise RuntimeError("secret")

    return app


@pytest.mark.parametrize("status", [408, 413, 415, 429])
async def test_unmapped_client_errors_keep_4xx_code(status):
    resp = await _app().test_client().get(f"/abort/{status}")
    body = await resp.get_json()
    assert resp.status_code == status
    assert 400 <= body["code"] <= 499
    assert body["message"]
    assert body["data"] is None


async def test_explicit_messages_for_413_and_429():
    client = _app().test_client()
    assert (await (await client.get("/abort/413")).get_json())["message"] == "payload too large"
    assert (await (await client.get("/abort/429")).get_json())["message"] == "too many requests"
    assert (await (await client.get("/abort/415")).get_json())["message"] == "request failed"


async def test_server_errors_stay_500_class():
    client = _app().test_client()
    resp = await client.get("/abort/503")
    body = await resp.get_json()
    assert resp.status_code == 503 and body["code"] >= 500 and body["message"] == "internal error"
    resp = await client.get("/boom")
    body = await resp.get_json()
    assert resp.status_code == 500 and body == {"code": 500, "message": "internal error", "data": None}


async def test_every_client_status_yields_client_code():
    client = _app().test_client()
    assert len(CLIENT_STATUSES) >= 10
    for status in CLIENT_STATUSES:
        resp = await client.get(f"/abort/{status}")
        body = await resp.get_json()
        assert resp.status_code == status
        assert body["code"] < 500, status
