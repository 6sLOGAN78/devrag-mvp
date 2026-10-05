"""Default CORS is same-origin only and never `*` (API-10, T-1-cors)."""
from __future__ import annotations

import httpx
import pytest

pytestmark = pytest.mark.e2e

EVIL = {"Origin": "http://evil.test"}
ROUTES = ["/health", "/api/v1/system/healthz"]


def _assert_no_cors(resp: httpx.Response) -> None:
    lowered = {k.lower(): v for k, v in resp.headers.items()}
    assert "access-control-allow-origin" not in lowered
    assert "*" not in lowered.get("access-control-allow-origin", "")
    assert not [k for k in lowered if k.startswith("access-control-allow-")]


@pytest.mark.parametrize("path", ROUTES)
def test_foreign_origin_gets_no_allow_origin(ingress: httpx.Client, path: str) -> None:
    resp = ingress.get(path, headers=EVIL)
    assert resp.status_code == 200
    _assert_no_cors(resp)


@pytest.mark.parametrize("path", ROUTES)
def test_preflight_gets_no_allow_headers(ingress: httpx.Client, path: str) -> None:
    resp = ingress.options(path, headers={**EVIL, "Access-Control-Request-Method": "GET"})
    _assert_no_cors(resp)
