"""OpenAPI served live through the ingress (API-08) and authenticated since plan 02-14 (R-113)."""
from __future__ import annotations

import httpx
import pytest

from test.helpers.accounts import Account

pytestmark = pytest.mark.e2e


def test_openapi_document_requires_authentication(ingress: httpx.Client) -> None:
    resp = ingress.get("/api/v1/openapi.json")
    assert resp.status_code == 401
    assert resp.headers["x-api-source"] == "python"
    assert resp.json() == {"code": 401, "message": "unauthorized", "data": None}


def test_openapi_document_lists_system_routes(ingress: httpx.Client, account: Account) -> None:
    resp = ingress.get("/api/v1/openapi.json", headers={"Authorization": f"Bearer {account.token}"})
    assert resp.status_code == 200
    assert resp.headers["x-api-source"] == "python"
    doc = resp.json()
    assert doc["openapi"].startswith("3.")
    assert "/api/v1/system/healthz" in doc["paths"]
    assert "/api/v1/system/status" in doc["paths"]
