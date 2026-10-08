"""WR-05: the browser write guard lives in the Go server; the premise is that Python owns no public state-changing route."""

from __future__ import annotations

import pytest
import yaml

from test.conftest import REPO_ROOT

pytestmark = pytest.mark.unit

UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}


def test_python_has_no_public_state_changing_route() -> None:
    """If this fails, mirror internal/handler/writeguard.go (JSON-only bodies, Origin check) in api/apps before adding the route."""
    rows = yaml.safe_load((REPO_ROOT / "conf/routes.yaml").read_text(encoding="utf-8"))["endpoints"]
    offenders = [f"{r['method']} {r['path']}" for r in rows if r["owner"] == "python" and r["auth"] == "none" and r["method"] in UNSAFE]
    assert offenders == []


def test_every_go_public_write_is_json_post() -> None:
    rows = yaml.safe_load((REPO_ROOT / "conf/routes.yaml").read_text(encoding="utf-8"))["endpoints"]
    public = sorted(r["path"] for r in rows if r["owner"] == "go" and r["auth"] == "none" and r["method"] in UNSAFE)
    assert public == [
        "/api/v1/auth/login",
        "/api/v1/auth/password/forgot/otp",
        "/api/v1/auth/password/forgot/otp/verify",
        "/api/v1/auth/password/reset",
        "/api/v1/users",
    ]
