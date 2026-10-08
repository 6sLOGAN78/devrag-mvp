"""Registry validation and policy resolution for conf/routes.yaml (D-30, R-90). Default is deny, never public by omission."""

from __future__ import annotations

import copy
import importlib
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

from test.conftest import REPO_ROOT

pytestmark = pytest.mark.unit

GEN = REPO_ROOT / "scripts" / "gen_routes.py"
CASES = json.loads((REPO_ROOT / "test/fixtures/route_policy_cases.json").read_text(encoding="utf-8"))["cases"]
ROUTES = REPO_ROOT / "conf" / "routes.yaml"


def policy_module() -> Any:
    return importlib.import_module("api.apps.route_policy_gen")


@pytest.mark.parametrize("case", CASES, ids=lambda c: f"{c['method']} {c['path'] or '(empty)'}")
def test_policy_for_matches_shared_cases(case: dict[str, Any]) -> None:
    pol = policy_module().policy_for(case["method"], case["path"])
    assert (pol.auth, pol.owner, pol.scope, pol.preflight) == (case["auth"], case["owner"], case["scope"], case["preflight"])


def test_unmatched_path_is_denied_never_public() -> None:
    mod = policy_module()
    for path in ("/unknown", "/", "", "/nope/deeper/still", "/api"):
        pol = mod.policy_for("GET", path)
        assert pol.auth == "jwt", path
        assert pol.auth != "none"


def test_openapi_json_is_a_protected_registry_row() -> None:
    data = yaml.safe_load(ROUTES.read_text(encoding="utf-8"))
    row = next(e for e in data["endpoints"] if e["path"] == "/api/v1/openapi.json")
    assert (row["method"], row["owner"], row["auth"], row["implemented"]) == ("GET", "python", "api", True)


def test_registry_marks_token_management_implemented_and_jwt_only() -> None:
    """Plan 02-20 landed API token create, list and delete; they accept the session token only (R-90)."""
    data = yaml.safe_load(ROUTES.read_text(encoding="utf-8"))
    rows = {(e["method"], e["path"]): e for e in data["endpoints"]}
    for key in [("GET", "/api/v1/system/tokens"), ("POST", "/api/v1/system/tokens"), ("DELETE", "/api/v1/system/tokens/{token}")]:
        row = rows[key]
        assert (row["owner"], row["auth"], row["implemented"], row["scope"]) == ("go", "jwt", True, "tenant"), key
        assert row["roles"] == ["owner"], key


def test_registry_marks_members_invite_respond_role_change_and_removal_implemented_and_jwt_only() -> None:
    """Plans 02-22 and 02-23 landed the member list, invite, accept or decline, role change and removal; none accepts an API or beta token."""
    data = yaml.safe_load(ROUTES.read_text(encoding="utf-8"))
    rows = {(e["method"], e["path"]): e for e in data["endpoints"]}
    for key, roles in [
        (("GET", "/api/v1/tenants/{tenant_id}/users"), ["owner", "admin", "normal"]),
        (("POST", "/api/v1/tenants/{tenant_id}/users"), ["owner"]),
        (("PATCH", "/api/v1/tenants/{tenant_id}"), ["invite"]),
        (("PATCH", "/api/v1/tenants/{tenant_id}/users/{user_id}"), ["owner"]),
        (("DELETE", "/api/v1/tenants/{tenant_id}/users"), ["owner", "self"]),
    ]:
        row = rows[key]
        assert (row["owner"], row["auth"], row["implemented"], row["scope"], row["roles"]) == ("go", "jwt", True, "tenant", roles), key


def test_registry_marks_profile_password_and_tenant_endpoints_implemented() -> None:
    """Plan 02-15 landed the settings, password, tenant info and tenant list handlers."""
    data = yaml.safe_load(ROUTES.read_text(encoding="utf-8"))
    rows = {(e["method"], e["path"]): e for e in data["endpoints"]}
    for key in [
        ("POST", "/v1/user/setting"),
        ("POST", "/v1/user/setting/password"),
        ("GET", "/v1/user/tenant_info"),
        ("GET", "/v1/tenant/list"),
    ]:
        assert rows[key]["owner"] == "go" and rows[key]["auth"] == "jwt" and rows[key]["implemented"] is True, key


def test_registry_marks_register_and_login_implemented() -> None:
    """Plan 02-09 landed both handlers."""
    data = yaml.safe_load(ROUTES.read_text(encoding="utf-8"))
    rows = {(e["method"], e["path"]): e for e in data["endpoints"]}
    for key in [("POST", "/api/v1/users"), ("POST", "/api/v1/auth/login")]:
        assert rows[key]["owner"] == "go" and rows[key]["implemented"] is True, key


def test_registry_marks_logout_and_user_info_implemented() -> None:
    """Plan 02-10 landed both handlers behind the Go auth gate."""
    data = yaml.safe_load(ROUTES.read_text(encoding="utf-8"))
    rows = {(e["method"], e["path"]): e for e in data["endpoints"]}
    for key in [("POST", "/api/v1/auth/logout"), ("GET", "/v1/user/info")]:
        assert rows[key]["owner"] == "go" and rows[key]["auth"] == "jwt" and rows[key]["implemented"] is True, key


def _copy_root(tmp_path: Path) -> Path:
    (tmp_path / "conf").mkdir()
    shutil.copy(ROUTES, tmp_path / "conf/routes.yaml")
    shutil.copy(REPO_ROOT / "conf" / "permissions.yaml", tmp_path / "conf/permissions.yaml")
    return tmp_path


def _gen(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(GEN), "--root", str(root), *args], capture_output=True, text=True, check=False, timeout=60)


def _mutate(tmp_path: Path, fn: Any) -> subprocess.CompletedProcess[str]:
    root = _copy_root(tmp_path)
    data = yaml.safe_load((root / "conf/routes.yaml").read_text(encoding="utf-8"))
    fn(data)
    (root / "conf/routes.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")
    return _gen(root)


def _row(data: dict[str, Any], method: str, path: str) -> dict[str, Any]:
    return next(e for e in data["endpoints"] if e["method"] == method and e["path"] == path)


def test_unmodified_registry_is_valid(tmp_path: Path) -> None:
    assert _gen(_copy_root(tmp_path)).returncode == 0


@pytest.mark.parametrize(
    "mutation",
    [
        lambda d: _row(d, "GET", "/health").update(owner="python"),
        lambda d: _row(d, "GET", "/health").update(auth="jwt"),
        lambda d: _row(d, "POST", "/api/v1/auth/login").update(auth="jwt"),
        lambda d: _row(d, "GET", "/health").update(auth="admin"),
        lambda d: _row(d, "GET", "/health").update(scope="global"),
        lambda d: _row(d, "GET", "/health").update(method="TRACE"),
        lambda d: _row(d, "GET", "/health").update(roles=["root"]),
        lambda d: _row(d, "GET", "/health").update(implemented="yes"),
        lambda d: _row(d, "GET", "/health").update(surprise=1),
        lambda d: d["endpoints"].append(copy.deepcopy(_row(d, "GET", "/health"))),
        lambda d: d["endpoints"].append({"method": "GET", "path": "/orphan", "owner": "go", "auth": "jwt", "roles": [], "scope": "none", "implemented": False}),
    ],
    ids=["owner", "auth", "auth-vs-prefix", "bad-auth", "bad-scope", "bad-method", "bad-role", "bad-bool", "extra-field", "duplicate", "unmatched-by-family"],
)
def test_invalid_registry_is_rejected(tmp_path: Path, mutation: Any) -> None:
    res = _mutate(tmp_path, mutation)
    assert res.returncode != 0, res.stdout


def test_orphan_with_matching_family_is_accepted(tmp_path: Path) -> None:
    def add(d: dict[str, Any]) -> None:
        d["endpoints"].append({"method": "GET", "path": "/api/v1/zzz", "owner": "python", "auth": "api", "roles": [], "scope": "none", "implemented": False})

    assert _mutate(tmp_path, add).returncode == 0


def test_row_may_tighten_an_api_family_to_session_only_but_never_loosen(tmp_path: Path) -> None:
    """Key-writing methods share a path with readable ones (plan 03-04): jwt over an api family is allowed, api over jwt is not."""

    def tighten(d: dict[str, Any]) -> None:
        d["endpoints"].append({"method": "POST", "path": "/api/v1/zzz", "owner": "python", "auth": "jwt", "roles": [], "scope": "none", "implemented": False})

    def loosen(d: dict[str, Any]) -> None:
        _row(d, "GET", "/api/v1/system/tokens").update(auth="api")

    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    assert _mutate(tmp_path / "a", tighten).returncode == 0
    assert _mutate(tmp_path / "b", loosen).returncode != 0


def test_phase3_key_writing_rows_are_session_only() -> None:
    """D-19, Pitfall 6: an API token must not reach the rows that write provider keys or default models.

    The provider rows landed in plan 03-12 and the default-model row in plan 03-13 (all implemented).
    """
    data = yaml.safe_load(ROUTES.read_text(encoding="utf-8"))
    rows = {(e["method"], e["path"]): e for e in data["endpoints"]}
    implemented = {
        ("PUT", "/api/v1/providers"): True,
        ("DELETE", "/api/v1/providers/{provider}"): True,
        ("POST", "/api/v1/providers/{provider}/instances"): True,
        ("PATCH", "/api/v1/models/default"): True,
    }
    for key, landed in implemented.items():
        row = rows[key]
        assert (row["owner"], row["auth"], row["scope"], row["implemented"]) == ("python", "jwt", "tenant", landed), key
        assert row["roles"] == ["owner", "admin"], key
    for key in [("GET", "/api/v1/providers"), ("GET", "/api/v1/models"), ("POST", "/api/v1/datasets"), ("POST", "/api/v1/documents/upload")]:
        assert rows[key]["auth"] == "api" and rows[key]["roles"] == ["owner", "admin", "normal"], key


def test_provider_rows_are_implemented_and_the_credential_detail_is_session_only() -> None:
    """Plan 03-12: six provider rows are served; the instance detail shows last4 and the address, so no token may read it."""
    data = yaml.safe_load(ROUTES.read_text(encoding="utf-8"))
    rows = {(e["method"], e["path"]): e for e in data["endpoints"]}
    provider_rows = {k: v for k, v in rows.items() if k[1].startswith("/api/v1/providers")}
    assert len(provider_rows) == 6 and all(r["implemented"] is True and r["owner"] == "python" for r in provider_rows.values())
    detail = rows[("GET", "/api/v1/providers/{provider}/instances/{instance}")]
    assert (detail["auth"], detail["roles"]) == ("jwt", ["owner", "admin"])
    assert rows[("GET", "/api/v1/providers/{provider}/models")]["auth"] == "api"


def test_check_fails_when_policy_modules_are_stale(tmp_path: Path) -> None:
    root = _copy_root(tmp_path)
    assert _gen(root).returncode == 0
    assert _gen(root, "--check").returncode == 0
    for rel in ("internal/common/route_policy_gen.go", "api/apps/route_policy_gen.py"):
        target = root / rel
        original = target.read_text(encoding="utf-8")
        target.write_text(original + "\n// stale\n", encoding="utf-8")
        assert _gen(root, "--check").returncode == 1, rel
        target.write_text(original, encoding="utf-8")
        assert _gen(root, "--check").returncode == 0


def test_generated_headers_say_do_not_edit() -> None:
    for rel in ("internal/common/route_policy_gen.go", "api/apps/route_policy_gen.py"):
        head = (REPO_ROOT / rel).read_text(encoding="utf-8")[:300]
        assert "generated by scripts/gen_routes.py, do not edit" in head.lower()


def test_registry_marks_password_reset_routes_public_and_implemented() -> None:
    """Plan 02-17 landed the three forgot-password handlers; they are Go-owned and public (auth none)."""
    data = yaml.safe_load(ROUTES.read_text(encoding="utf-8"))
    rows = {(e["method"], e["path"]): e for e in data["endpoints"]}
    for key in [
        ("POST", "/api/v1/auth/password/forgot/otp"),
        ("POST", "/api/v1/auth/password/forgot/otp/verify"),
        ("POST", "/api/v1/auth/password/reset"),
    ]:
        assert rows[key]["owner"] == "go" and rows[key]["auth"] == "none" and rows[key]["implemented"] is True, key
