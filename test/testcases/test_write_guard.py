"""WR-05 live: cross-site form posts cannot log a browser in, register, or drive a reset through Nginx."""
from __future__ import annotations

import httpx
import pytest

from test.helpers.accounts import AccountRegistry
from test.testcases.conftest import BASE_URL

pytestmark = pytest.mark.e2e

PUBLIC = ["/api/v1/auth/login", "/api/v1/users", "/api/v1/auth/password/forgot/otp", "/api/v1/auth/password/forgot/otp/verify", "/api/v1/auth/password/reset"]


@pytest.mark.parametrize("path", PUBLIC)
@pytest.mark.parametrize("content_type", ["application/x-www-form-urlencoded", "text/plain;charset=UTF-8", "multipart/form-data; boundary=x"])
def test_public_writes_refuse_form_content_types(ingress: httpx.Client, path: str, content_type: str) -> None:
    resp = ingress.post(path, content=b'{"email":"nobody@example.test","password":"fake-pass-0001"}', headers={"Content-Type": content_type})
    assert resp.status_code == 415, resp.text
    assert resp.json()["code"] == 400
    assert "set-cookie" not in resp.headers


@pytest.mark.parametrize("path", PUBLIC)
def test_public_writes_refuse_a_cross_site_origin(ingress: httpx.Client, path: str) -> None:
    resp = ingress.post(path, json={"email": "nobody@example.test", "password": "fake-pass-0001"}, headers={"Origin": "https://evil.example"})
    assert resp.status_code == 403, resp.text
    assert resp.json()["code"] == 403
    assert "set-cookie" not in resp.headers


def test_login_without_origin_and_with_the_sites_own_origin_still_works(ingress: httpx.Client) -> None:
    registry = AccountRegistry(BASE_URL)
    try:
        acc = registry.register(prefix="guard")
        creds = {"email": acc.email, "password": acc.password}
        assert ingress.post("/api/v1/auth/login", json=creds).status_code == 200
        own = ingress.post("/api/v1/auth/login", json=creds, headers={"Origin": BASE_URL})
        assert own.status_code == 200, own.text
        assert "ragflow_auth" in own.headers.get("set-cookie", "")
    finally:
        registry.cleanup()

