"""The Python access log records the route template, never the raw path of a matched route (plan 02-25, T-02-94, T-02-119).

A credential carried in a URL path (``DELETE /api/v1/system/tokens/<token>`` is Go-owned, but any later Python route may
carry an id or a token) must not reach the log. Unmatched requests (404/405) have no template and log the truncated raw path,
except under the credential family, which is replaced by its template.
"""
from __future__ import annotations

import logging

import pytest
from quart import Quart

from api.apps.middleware import register_middleware
from test.helpers.app import memory_settings

pytestmark = pytest.mark.unit

SECRET = "fake-path-credential-0123456789abcdefghijklmnopq"


def _app() -> Quart:
    app = Quart("template-log-test")
    register_middleware(app, memory_settings())

    @app.get("/api/v1/widgets/<widget_id>/parts/<part>")
    async def widget(widget_id: str, part: str) -> tuple[str, int]:
        return "ok", 200

    return app


async def _logged(caplog: pytest.LogCaptureFixture, method: str, path: str) -> tuple[int, str]:
    with caplog.at_level(logging.INFO, logger="ragflow.access"):
        resp = await _app().test_client().open(path, method=method)
    records = [r for r in caplog.records if r.name == "ragflow.access"]
    assert len(records) == 1
    return resp.status_code, records[0].path


async def test_matched_route_logs_the_template_not_the_path_values(caplog: pytest.LogCaptureFixture) -> None:
    status, logged = await _logged(caplog, "GET", f"/api/v1/widgets/{SECRET}/parts/abc")
    assert status == 200
    assert logged == "/api/v1/widgets/<widget_id>/parts/<part>"
    assert logged.count(SECRET) == 0


async def test_unmatched_path_logs_the_truncated_raw_path(caplog: pytest.LogCaptureFixture) -> None:
    status, logged = await _logged(caplog, "GET", "/no/such/route")
    assert status == 404
    assert logged == "/no/such/route"


async def test_unmatched_credential_family_logs_its_template(caplog: pytest.LogCaptureFixture) -> None:
    status, logged = await _logged(caplog, "DELETE", f"/api/v1/system/tokens/{SECRET}")
    assert status == 404
    assert logged == "/api/v1/system/tokens/:token"
    assert logged.count(SECRET) == 0

