"""The Nginx access log never records a credential-bearing request target (plan 02-25, T-02-94, T-02-119)."""
from __future__ import annotations

import re

import pytest

from test.conftest import REPO_ROOT

pytestmark = pytest.mark.unit

CONF = (REPO_ROOT / "docker" / "nginx" / "nginx.conf").read_text(encoding="utf-8")


def test_access_log_uses_a_named_format_not_the_default_combined_one() -> None:
    assert re.search(r"^\s*access_log\s+/dev/stdout\s+devrag;", CONF, re.MULTILINE)
    assert "log_format devrag" in CONF


def test_log_format_has_no_raw_request_target_query_or_referer() -> None:
    fmt = CONF[CONF.index("log_format devrag") :].split(";", 1)[0]
    for banned in ("$request ", "$request_uri", "$args", "$query_string", "$is_args", "$http_referer", "$http_authorization", "$http_cookie", "$uri "):
        assert banned not in fmt + " ", f"the access log format must not contain {banned.strip()}"
    assert "$loggable_uri" in fmt


def test_token_family_is_masked_by_a_map_on_the_normalised_path() -> None:
    assert "map $uri $loggable_uri" in CONF
    assert "/api/v1/system/tokens/" in CONF.split("map $uri $loggable_uri", 1)[1].split("log_format", 1)[0]
    assert "***" in CONF


def test_credential_shaped_segments_are_masked_wherever_they_appear() -> None:
    block = CONF.split("map $uri $loggable_uri", 1)[1].split("log_format", 1)[0]
    assert "ragflow-" in block and "ragflow-***" in block
