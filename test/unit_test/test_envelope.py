from __future__ import annotations

import json
import logging

import pytest

from api.utils.api_utils import json_result
from common.settings import ConfigError
from test.helpers.app import make_test_app

pytestmark = pytest.mark.unit


def test_json_result_key_order_and_shape():
    async def run():
        app = make_test_app()
        async with app.app_context():
            resp = json_result({"a": 1})
            return await resp.get_data(as_text=True)

    import asyncio

    body = asyncio.run(run())
    assert body == '{"code": 0, "message": "", "data": {"a": 1}}'
    assert list(json.loads(body)) == ["code", "message", "data"]


async def test_not_found_envelope():
    resp = await make_test_app().test_client().get("/nope")
    assert resp.status_code == 404
    assert await resp.get_json() == {"code": 404, "message": "not found", "data": None}
    assert resp.headers["X-API-Source"] == "python"


async def test_method_not_allowed_envelope():
    resp = await make_test_app().test_client().get("/test/named")
    assert resp.status_code == 405
    body = await resp.get_json()
    assert body["code"] == 405 and body["data"] is None
    assert resp.headers["X-API-Source"] == "python"


async def test_malformed_json_is_400_code_101():
    resp = await make_test_app().test_client().post("/test/named", data="{not json", headers={"Content-Type": "application/json"})
    assert resp.status_code == 400
    assert await resp.get_json() == {"code": 101, "message": "invalid request", "data": None}


async def test_schema_violation_is_400_code_101_without_echo():
    resp = await make_test_app().test_client().post("/test/named", json={"name": "' OR 1=1 --"})
    assert resp.status_code == 400
    text = await resp.get_data(as_text=True)
    assert json.loads(text) == {"code": 101, "message": "invalid request", "data": None}
    assert "OR 1=1" not in text


async def test_unhandled_exception_does_not_leak_and_is_logged(caplog):
    with caplog.at_level(logging.ERROR):
        resp = await make_test_app().test_client().get("/test/boom")
    assert resp.status_code == 500
    text = await resp.get_data(as_text=True)
    assert json.loads(text) == {"code": 500, "message": "internal error", "data": None}
    assert "secret detail" not in text and "Traceback" not in text
    assert resp.headers["X-API-Source"] == "python"
    logged = [r for r in caplog.records if r.getMessage() == "unhandled exception"]
    assert logged and logged[0].exc_info is not None


async def test_source_header_on_success():
    resp = await make_test_app().test_client().post("/test/named", json={"name": "ok"})
    assert resp.status_code == 200
    assert resp.headers["X-API-Source"] == "python"
    assert await resp.get_json() == {"code": 0, "message": "", "data": {"name": "ok"}}


async def test_access_log_fields():
    records: list[logging.LogRecord] = []

    class Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    logger = logging.getLogger("ragflow.access")
    handler = Capture(level=logging.INFO)
    logger.addHandler(handler)
    old = logger.level
    logger.setLevel(logging.INFO)
    try:
        await make_test_app().test_client().get("/nope", headers={"Authorization": "Bearer abc"})
    finally:
        logger.removeHandler(handler)
        logger.setLevel(old)
    assert len(records) == 1
    rec = records[0]
    assert rec.method == "GET" and rec.path == "/nope" and rec.status == 404
    assert isinstance(rec.duration_ms, float)
    assert not hasattr(rec, "headers") and "abc" not in rec.getMessage()


async def test_cors_allow_list():
    app = make_test_app(allowed_origins=("http://a.test",))
    client = app.test_client()
    ok = await client.get("/nope", headers={"Origin": "http://a.test"})
    assert ok.headers.get("Access-Control-Allow-Origin") == "http://a.test"
    bad = await client.get("/nope", headers={"Origin": "http://b.test"})
    assert "Access-Control-Allow-Origin" not in bad.headers


async def test_cors_empty_adds_no_headers():
    resp = await make_test_app().test_client().get("/nope", headers={"Origin": "http://a.test"})
    assert not [h for h in resp.headers.keys() if h.lower().startswith("access-control-")]


def test_wildcard_origin_rejected():
    with pytest.raises(ConfigError):
        make_test_app(allowed_origins=("*",))
