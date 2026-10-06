"""An 8 KB request path cannot slow or bloat the request logger (CR-02, D-31)."""
from __future__ import annotations

import logging
import time

import pytest

from common.log_utils import MAX_LOG_FIELD, truncate_field
from test.helpers.app import make_test_app

pytestmark = pytest.mark.unit

RESPONSE_BOUND_S = 2.0


async def test_8kb_path_is_truncated_in_access_log_and_fast(caplog):
    path = "/" + "a" * 8192
    with caplog.at_level(logging.INFO, logger="ragflow.access"):
        started = time.perf_counter()
        resp = await make_test_app().test_client().get(path)
        elapsed = time.perf_counter() - started
    assert resp.status_code == 404
    assert elapsed < RESPONSE_BOUND_S
    logged = [r.path for r in caplog.records if r.name == "ragflow.access"]
    assert len(logged) == 1
    assert logged[0].endswith("[truncated]") and len(logged[0]) == MAX_LOG_FIELD + len("[truncated]")


def test_truncate_field_leaves_short_values():
    assert truncate_field("/health") == "/health"
