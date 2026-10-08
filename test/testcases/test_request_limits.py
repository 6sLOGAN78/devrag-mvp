"""WR-04 live: body-size limits at Nginx and at Go, the 413 envelope, the real maximum avatar upload."""
from __future__ import annotations

import base64

import httpx
import pytest

from test.helpers.accounts import AccountRegistry
from test.testcases.conftest import BASE_URL, exec_app

pytestmark = pytest.mark.e2e

OVER_SMALL = b"{" + b" " * (20 * 1024) + b"}"  # 20 KB, over the 16 KB limit of every small Go route
PNG = b"\x89PNG\r\n\x1a\n"


def _envelope_413(resp: httpx.Response) -> None:
    assert resp.status_code == 413, resp.text[:200]
    assert resp.headers["content-type"].startswith("application/json")
    assert resp.json() == {"code": 400, "message": "payload too large", "data": None}
    # Go stamps every response with X-API-Source; its absence proves Nginx refused the body before the upstream saw it.
    assert "x-api-source" not in resp.headers, "the body reached the Go server; Nginx did not enforce the limit"


@pytest.mark.parametrize(
    "path",
    ["/api/v1/auth/login", "/api/v1/users", "/api/v1/auth/password/forgot/otp", "/api/v1/auth/password/forgot/otp/verify", "/api/v1/auth/password/reset"],
)
def test_public_auth_routes_refuse_an_oversize_body_with_the_envelope(ingress: httpx.Client, path: str) -> None:
    _envelope_413(ingress.post(path, content=OVER_SMALL, headers={"Content-Type": "application/json"}))


def test_authenticated_small_routes_refuse_an_oversize_body_with_the_envelope(ingress: httpx.Client) -> None:
    registry = AccountRegistry(BASE_URL)
    try:
        acc = registry.register(prefix="limits")
        auth = {"Authorization": f"Bearer {acc.token}", "Content-Type": "application/json"}
        for path in ("/api/v1/system/tokens", f"/api/v1/tenants/{acc.tenant_id}/users"):
            _envelope_413(ingress.post(path, content=OVER_SMALL, headers=auth))
        # /v1/user/ shares the profile route's 512k Nginx limit; Go's own 2 KB cap answers a smaller password body.
        small = ingress.post("/v1/user/setting/password", content=OVER_SMALL, headers=auth)
        assert small.status_code == 413 and small.json()["message"] == "payload too large"
        _envelope_413(ingress.post("/v1/user/setting/password", content=b"{" + b" " * (600 * 1024) + b"}", headers=auth))
    finally:
        registry.cleanup()


def test_the_largest_legal_avatar_passes_nginx_and_go_and_a_larger_body_does_not(ingress: httpx.Client) -> None:
    registry = AccountRegistry(BASE_URL)
    try:
        acc = registry.register(prefix="avatar")
        auth = {"Authorization": f"Bearer {acc.token}"}
        raw = PNG + b"\x00" * (256 * 1024 - len(PNG))
        assert len(raw) == 256 * 1024
        avatar = "data:image/png;base64," + base64.b64encode(raw).decode()
        assert len(avatar) == len("data:image/png;base64,") + 349_528
        ok = ingress.post("/v1/user/setting", json={"nickname": "n" * 64, "avatar": avatar, "language": "en", "color_schema": "Bright"}, headers=auth)
        assert ok.status_code == 200 and ok.json()["code"] == 0, ok.text[:200]

        too_big = ingress.post("/v1/user/setting", content=b'{"avatar":"' + b"A" * (600 * 1024) + b'"}', headers={**auth, "Content-Type": "application/json"})
        _envelope_413(too_big)
    finally:
        registry.cleanup()


def test_nginx_accepts_its_generated_configuration() -> None:
    out = exec_app("nginx", "-t")
    assert out.returncode == 0, out.stderr[-400:]
