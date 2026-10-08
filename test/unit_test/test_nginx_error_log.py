"""The Nginx error log cannot record a token-bearing request line (WR-03, R-131)."""

from __future__ import annotations

import re

import pytest

from test.unit_test.test_nginx_limits import CONFS, locations

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("conf", CONFS)
def test_credential_bearing_location_cannot_write_its_request_line_to_the_error_log(conf: str) -> None:
    """WR-03: upstream failures log `request: "DELETE /api/v1/system/tokens/<token> ..."` at error level."""
    token_family = [b for op, p, _, b in locations(conf) if p == "/api/v1/system/tokens/"]
    assert len(token_family) == 1
    assert re.search(r"^\s*error_log /dev/stderr emerg;", token_family[0], re.M)
    for op, path, _, body in locations(conf):
        if path != "/api/v1/system/tokens/":
            assert "error_log" not in body, f"{path} keeps normal error logging"
