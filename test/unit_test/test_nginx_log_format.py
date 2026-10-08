"""The Nginx access log never records a credential-bearing request target (plan 02-25, T-02-94, T-02-119)."""
from __future__ import annotations

import json
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


_MAP_BLOCK = CONF.split("map $uri $loggable_uri", 1)[1].split("log_format", 1)[0]
_MAP_ENTRY = re.compile(r'^\s*"~\*(?P<regex>.+)"\s+"(?P<repl>[^"]*)";', re.MULTILINE)


def _loggable(uri: str) -> str:
    """Apply the map entries in file order, first match wins, the way Nginx evaluates a regex map."""
    for entry in _MAP_ENTRY.finditer(_MAP_BLOCK):
        pattern = re.sub(r"\(\?<(\w+)>", r"(?P<\1>", entry.group("regex"))
        m = re.search(pattern, uri, re.IGNORECASE)
        if m:
            return re.sub(r"\$\{(\w+)\}", lambda g: m.group(g.group(1)), entry.group("repl"))
    return uri


_VECTORS = [v for v in json.loads((REPO_ROOT / "test" / "fixtures" / "log_redaction_vectors.json").read_text()) if "uri" in v]


def test_the_shared_vector_file_carries_uri_vectors() -> None:
    assert {v["id"] for v in _VECTORS} >= {"key_in_url_path", "key_in_url_path_openai"}


@pytest.mark.parametrize("vec", _VECTORS, ids=[v["id"] for v in _VECTORS])
def test_provider_key_shapes_are_masked_in_the_logged_uri(vec: dict) -> None:
    out = _loggable(vec["uri"])
    for secret in vec["secrets"]:
        assert secret not in out
    for kept in vec["keep"]:
        assert kept in out


def test_the_map_still_masks_the_existing_credential_families() -> None:
    assert _loggable("/api/v1/system/tokens/abc-fake") == "/api/v1/system/tokens/***"
    assert _loggable("/x/ragflow-" + "A" * 24 + "/y") == "/x/ragflow-***/y"
    assert _loggable("/api/v1/datasets") == "/api/v1/datasets"
    assert _loggable("/api/v1/task-force-leader-name") == "/api/v1/task-force-leader-name"
