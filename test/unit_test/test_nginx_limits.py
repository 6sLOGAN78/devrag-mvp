"""Request-size limits, timeouts and error-log hygiene of the generated Nginx ingress (WR-04, R-130)."""

from __future__ import annotations

import re

import pytest

from test.conftest import REPO_ROOT

pytestmark = pytest.mark.unit

NGINX = REPO_ROOT / "docker" / "nginx"
GO_PORT, PY_PORT = "9384", "9380"
BLOCK = re.compile(r"location (=|\^~)? ?(\S+) \{(.*?)\n    \}", re.S)
SIZE = re.compile(r"client_max_body_size (\d+)([kKmM]);")
AVATAR_BYTES = 256 * 1024  # R-118: largest avatar, decoded
CONFS = ["ragflow.conf", "ragflow.https.conf"]


def locations(name: str) -> list[tuple[str, str, str, str]]:
    """(match op, path, owner port, body) of every proxied location."""
    out = []
    for op, path, body in BLOCK.findall((NGINX / name).read_text(encoding="utf-8")):
        m = re.search(r"proxy_pass http://127\.0\.0\.1:(\d+);", body)
        if m:
            out.append((op, path, m.group(1), body))
    return out


def size_bytes(body: str) -> int:
    m = SIZE.search(body)
    assert m, f"no client_max_body_size in {body!r}"
    return int(m.group(1)) * (1024 if m.group(2).lower() == "k" else 1024 * 1024)


def max_settings_body() -> int:
    """The largest real POST /v1/user/setting body: a 256 KB avatar data URL plus the other fields at their maxima."""
    b64 = 4 * ((AVATAR_BYTES + 2) // 3)
    avatar = len("data:image/webp;base64,") + b64
    other = len('{"nickname":"","avatar":"","language":"en","color_schema":"Bright"}') + 64 * 6
    return avatar + other


def test_the_real_maximum_settings_body_is_below_the_go_cap_and_nginx_limit() -> None:
    need = max_settings_body()
    assert 349_000 < need < 351_000  # base64 of 262144 bytes is 349,528 characters
    go_src = (REPO_ROOT / "internal/handler/user.go").read_text(encoding="utf-8")
    assert "maxSettingBody = 400 << 10" in go_src and need < 400 << 10
    for conf in CONFS:
        prefix = {p: b for op, p, _, b in locations(conf) if op == "^~"}
        assert size_bytes(prefix["/v1/user/"]) >= need


@pytest.mark.parametrize("conf", CONFS)
def test_go_owned_locations_have_small_body_limits_except_the_profile_route(conf: str) -> None:
    for op, path, port, body in locations(conf):
        if port != GO_PORT:
            continue
        limit = size_bytes(body)
        if path == "/v1/user/":
            assert limit <= 1 << 20, path
        else:
            assert limit <= 16 << 10, f"{path} may take at most 16k, has {limit}"


MB = 1024 * 1024
UPLOAD_PATH = "/api/v1/documents/upload"
JSON_FAMILIES = ("/api/v1/providers", "/api/v1/providers/", "/api/v1/models", "/api/v1/models/default", "/api/v1/datasets", "/api/v1/datasets/")
CATCH_ALLS = ("/api/", "/v1/")


@pytest.mark.parametrize("conf", CONFS)
def test_python_owned_locations_have_an_explicit_per_path_body_limit(conf: str) -> None:
    """Upload 101m, JSON families 1m, the catch-alls keep 1024m (plan 03-04, T-03-04-04)."""
    py = {p: b for _, p, port, b in locations(conf) if port == PY_PORT}
    assert py
    assert size_bytes(py[UPLOAD_PATH]) == 101 * MB
    for path in JSON_FAMILIES:
        assert path in py, path
        assert size_bytes(py[path]) == 1 * MB, path
    for path in CATCH_ALLS:
        assert size_bytes(py[path]) == 1024 * MB, path
    for path, body in py.items():
        if path not in (UPLOAD_PATH, *JSON_FAMILIES, *CATCH_ALLS):
            assert size_bytes(body) == 1024 * MB, path


def test_global_default_is_small_so_a_new_location_cannot_inherit_the_upload_limit() -> None:
    conf = (NGINX / "nginx.conf").read_text(encoding="utf-8")
    assert re.search(r"^\s*client_max_body_size 1m;", conf, re.M)
    assert "1024m" not in conf
    assert re.search(r"^\s*client_body_timeout \d+s;", conf, re.M)
    assert re.search(r"^\s*client_header_timeout \d+s;", conf, re.M)


@pytest.mark.parametrize("conf", CONFS)
def test_go_auth_locations_have_short_upstream_timeouts_but_streaming_ones_stay_long(conf: str) -> None:
    for op, path, port, body in locations(conf):
        m = re.search(r"proxy_read_timeout (\d+)s;", body)
        assert m, f"{path} needs an explicit proxy_read_timeout"
        if port == GO_PORT and path not in ("/api/v1/mcp", "/api/v1/searchbots/"):
            assert int(m.group(1)) <= 60, path
        else:
            assert int(m.group(1)) >= 3600, path


def test_shared_proxy_include_sets_no_timeouts_so_locations_can_choose() -> None:
    text = (NGINX / "proxy.conf").read_text(encoding="utf-8")
    assert not re.search(r"^\s*proxy_(read|send)_timeout", text, re.M)


@pytest.mark.parametrize("conf", CONFS)
def test_oversize_bodies_get_the_json_envelope_not_an_html_page(conf: str) -> None:
    text = (NGINX / conf).read_text(encoding="utf-8")
    assert "error_page 413 @payload_too_large;" in text
    named = text.split("location @payload_too_large", 1)[1].split("\n    }", 1)[0]
    assert "return 413" in named and "application/json" in named
    assert '"code":400' in named and '"message":"payload too large"' in named
