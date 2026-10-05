"""Each request is logged once with method, path, status, duration_ms and no credentials (API-11, T-14-03)."""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

import httpx
import pytest

from test.helpers.wait import wait_until
from test.testcases.conftest import LOG_DIR

pytestmark = pytest.mark.e2e


def _find(log: Path, path: str) -> dict[str, Any] | None:
    if not log.is_file():
        return None
    for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
        if path not in line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if rec.get("path") == path:
            return rec
    return None


@pytest.mark.parametrize(("prefix", "logfile"), [("/api/v1/logprobe-", "ragflow_server.log"), ("/v1/user/logprobe-", "ragflow_go.log")])
def test_request_is_logged_without_credentials(ingress: httpx.Client, prefix: str, logfile: str) -> None:
    token = uuid.uuid4().hex
    path = f"{prefix}{token}"
    secret = f"secret-token-{token}"
    resp = ingress.get(path, headers={"Authorization": f"Bearer {secret}"})
    assert resp.status_code == 404
    rec = wait_until(lambda: _find(LOG_DIR / logfile, path), timeout=30, interval=0.5)
    assert rec["method"] == "GET"
    assert rec["status"] == 404
    assert isinstance(rec["duration_ms"], int | float)
    assert secret not in json.dumps(rec)
    assert secret not in (LOG_DIR / logfile).read_text(encoding="utf-8", errors="replace")
