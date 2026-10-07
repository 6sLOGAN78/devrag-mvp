"""Python route table enumeration: no route without a registry row, every protected row answers 401 (D-30, SEC-01, WR-25).

The first half builds the REAL app from the real factory and walks ``app.url_map.iter_rules()``; the second
half sends the same probes through Nginx to the live stack (needs ``make up``).
"""
from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import Any

import httpx
import pytest
import yaml
from quart import Blueprint

from api.apps import create_app
from api.apps.route_policy_gen import policy_for
from api.utils.api_utils import json_result
from test.conftest import REPO_ROOT
from test.helpers.app import StubPrincipalResolver, memory_settings
from test.testcases._routes import ROUTES_FILE, load_probes

pytestmark = pytest.mark.e2e

UNAUTHORIZED = {"code": 401, "message": "unauthorized", "data": None}
IMPLICIT_METHODS = {"HEAD", "OPTIONS"}
DATA: dict[str, Any] = yaml.safe_load(ROUTES_FILE.read_text(encoding="utf-8"))
ENDPOINTS: list[dict[str, Any]] = DATA["endpoints"]
REGISTRY = {(row["method"], row["path"]) for row in ENDPOINTS}


def _template(rule: str) -> str:
    """Flask-style ``<int:id>`` converters become the registry's ``{id}`` form."""
    return re.sub(r"<(?:[^:>]+:)?([^>]+)>", r"{\1}", rule)


def undeclared_rules(app: Any, registry: set[tuple[str, str]] = REGISTRY) -> list[str]:
    """One message per (method, rule) of the app's url_map that has no registry row."""
    found = []
    for rule in app.url_map.iter_rules():
        for method in sorted(rule.methods - IMPLICIT_METHODS):
            if (method, _template(rule.rule)) not in registry:
                found.append(f"{method} {rule.rule} (endpoint {rule.endpoint})")
    return found


def real_app() -> Any:
    return create_app(memory_settings(), principal_resolver=StubPrincipalResolver())


def test_every_python_route_is_declared_in_the_registry() -> None:
    app = real_app()
    rules = list(app.url_map.iter_rules())
    assert len(rules) >= 6, "the app serves at least health, status, language and the schema"
    assert undeclared_rules(app) == []


def test_enumeration_counts_what_it_checked() -> None:
    app = real_app()
    checked = [(m, _template(r.rule)) for r in app.url_map.iter_rules() for m in sorted(r.methods - IMPLICIT_METHODS)]
    assert checked, "the enumeration must iterate real rules"
    assert set(checked) <= REGISTRY
    # The Python engine owns (or directly duplicates) exactly these rows today.
    assert ("GET", "/api/v1/system/status") in checked and ("GET", "/api/v1/openapi.json") in checked


def test_an_undeclared_route_is_detected_and_still_denied() -> None:
    bp = Blueprint("undeclared_probe", __name__)

    @bp.get("/api/v1/undeclared-" + uuid.uuid4().hex[:8])
    async def handler() -> Any:  # pragma: no cover - never reached unauthenticated
        return json_result({"reached": True})

    app = create_app(memory_settings(), extra_blueprints=(bp,), principal_resolver=StubPrincipalResolver())
    flagged = undeclared_rules(app)
    assert len(flagged) == 1 and "undeclared-" in flagged[0]


async def test_undeclared_route_answers_401_without_credentials() -> None:
    bp = Blueprint("undeclared_probe2", __name__)
    path = "/api/v1/undeclared-" + uuid.uuid4().hex[:8]

    @bp.get(path)
    async def handler() -> Any:  # pragma: no cover - never reached unauthenticated
        return json_result({"reached": True})

    app = create_app(memory_settings(), extra_blueprints=(bp,), principal_resolver=StubPrincipalResolver())
    resp = await app.test_client().get(path)
    assert resp.status_code == 401
    assert await resp.get_json() == UNAUTHORIZED


def test_no_static_route_is_served() -> None:
    assert not any(r.endpoint == "static" for r in real_app().url_map.iter_rules())


PYTHON_ROWS = [r for r in ENDPOINTS if r["owner"] == "python" and r.get("implemented")]
PROTECTED_PYTHON_ROWS = [r for r in PYTHON_ROWS if r["auth"] != "none"]
PUBLIC_PYTHON_ROWS = [r for r in PYTHON_ROWS if r["auth"] == "none"]


def test_registry_has_protected_and_public_python_rows() -> None:
    assert {r["path"] for r in PROTECTED_PYTHON_ROWS} >= {"/api/v1/system/status", "/system/status", "/api/v1/openapi.json"}
    assert {r["path"] for r in PUBLIC_PYTHON_ROWS} == {"/api/v1/system/healthz", "/system/healthz"}


@pytest.mark.parametrize("row", PROTECTED_PYTHON_ROWS, ids=[f"{r['method']} {r['path']}" for r in PROTECTED_PYTHON_ROWS])
async def test_protected_python_row_answers_401_without_credentials(row: dict[str, Any]) -> None:
    resp = await real_app().test_client().open(row["path"], method=row["method"])
    assert resp.status_code == 401
    assert await resp.get_json() == UNAUTHORIZED
    assert resp.headers["X-API-Source"] == "python"


@pytest.mark.parametrize("row", PUBLIC_PYTHON_ROWS, ids=[r["path"] for r in PUBLIC_PYTHON_ROWS])
async def test_public_python_health_row_is_never_401(row: dict[str, Any]) -> None:
    resp = await real_app().test_client().open(row["path"], method=row["method"])
    assert resp.status_code in (200, 503), "the probe answers (503 when a dependency is down), it is never denied"


FAMILIES = load_probes()


@pytest.mark.parametrize("probe", FAMILIES, ids=[p.id for p in FAMILIES])
async def test_every_family_probe_follows_the_generated_policy(probe: Any) -> None:
    """Each family probe `prefixprobe-<uuid>` answers 401 unless the family is declared auth none."""
    path = probe.request_path(token=f"prefixprobe-{uuid.uuid4().hex}")
    resp = await real_app().test_client().get(path)
    if probe.auth == "none":
        assert resp.status_code != 401, f"{probe.id} is a public family"
    else:
        assert resp.status_code == 401, f"{probe.id} must be denied without credentials (got {resp.status_code})"
        assert await resp.get_json() == UNAUTHORIZED
    assert policy_for("GET", path).auth == probe.auth, "the generated resolver and routes.yaml agree on this family"


def test_container_probes_only_use_public_routes() -> None:
    """The container healthcheck and wait_stack.sh must keep working with the status route authenticated."""
    scripts = [REPO_ROOT / "docker" / "healthcheck.sh", REPO_ROOT / "scripts" / "wait_stack.sh"]
    paths: set[str] = set()
    for script in scripts:
        text = Path(script).read_text(encoding="utf-8")
        paths |= set(re.findall(r"(?:BASE_URL|\{PY_PORT\}|\{GO_PORT\})(/[A-Za-z0-9_/.-]*)", text))
    assert {"/health", "/api/v1/system/healthz"} <= paths
    assert paths, "expected the probe scripts to name at least one route"
    for path in paths:
        assert policy_for("GET", path).auth == "none", f"{path} is used by a container probe but is not public"


# --- live, through Nginx ------------------------------------------------------------------------------------


@pytest.mark.parametrize("path", ["/api/v1/system/status", "/system/status", "/api/v1/openapi.json"])
def test_live_protected_python_routes_are_401_through_nginx(ingress: httpx.Client, path: str) -> None:
    resp = ingress.get(path)
    assert resp.status_code == 401
    assert resp.json() == UNAUTHORIZED
    assert resp.headers["x-api-source"] == "python"


@pytest.mark.parametrize("prefix", ["/api/v1/", "/v1/"])
def test_live_unknown_paths_under_the_python_catch_alls_are_401(ingress: httpx.Client, prefix: str) -> None:
    resp = ingress.get(f"{prefix}prefixprobe-{uuid.uuid4().hex}")
    assert resp.status_code == 401
    assert resp.json() == UNAUTHORIZED
    assert resp.headers["x-api-source"] == "python"


def test_live_healthz_stays_public(ingress: httpx.Client) -> None:
    for path in ("/api/v1/system/healthz", "/system/healthz"):
        assert ingress.get(path).status_code == 200, path


def test_live_authenticated_unknown_path_is_404_not_401(ingress: httpx.Client, account: Any) -> None:
    resp = ingress.get(f"/api/v1/prefixprobe-{uuid.uuid4().hex}", headers={"Authorization": f"Bearer {account.token}"})
    assert resp.status_code == 404
    assert resp.json() == {"code": 404, "message": "not found", "data": None}
