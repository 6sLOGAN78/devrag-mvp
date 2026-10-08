"""Python default-deny auth gate and principal resolution (plan 02-14; D-09, D-11, D-21, D-30, R-114).

The gate is the real before_request hook built by the real app factory. The persistence behind the
real auth service is an in-memory store here (unit tier); the live tiers use real MySQL.
"""
from __future__ import annotations

import ast
import json
import logging
import threading
import time
from pathlib import Path
from typing import Any

import pytest
from quart import Blueprint
from quart.testing import QuartClient

from api.apps import create_app
from api.db.services import auth_service
from api.db.services.auth_service import ApiTokenRecord, AuthInfrastructureError, MembershipRecord, Principal, UserRecord
from common.security import tokens
from test.helpers.app import STUB_SECRET, StubPrincipalResolver, make_client, make_test_app, memory_settings

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
UNAUTHORIZED = {"code": 401, "message": "unauthorized", "data": None}
UNAVAILABLE = {"code": 503, "message": "service unavailable", "data": None}
FORBIDDEN = {"code": 403, "message": "forbidden", "data": None}

INNER = "0123456789abcdef0123456789abcdef"
OTHER_INNER = "fedcba9876543210fedcba9876543210"
USER_ID = "u" * 32
API_TOKEN = "ragflow-" + "A" * 43
BETA_TOKEN = "b" * 32
FAKE_COOKIE_SECRET = "cookie-value-that-must-never-be-logged"

JWT_PATH = "/v1/tenant/gate-probe"  # family /v1/tenant/ is jwt
API_PATH = "/api/v1/gate-probe-api"  # falls under the /api/ catch-all, which is api
BETA_PATH = "/api/v1/searchbots/gate-probe"  # family /api/v1/searchbots/ is beta
PUBLIC_PATH = "/api/v1/auth/gate-probe"  # family /api/v1/auth/ is none


class FakeStore:
    """In-memory AuthStore. Case-insensitive equality mimics the MySQL collation on purpose."""

    def __init__(self) -> None:
        self.users: dict[str, UserRecord] = {}
        self.roles: dict[str, str] = {}
        self.api_tokens: list[ApiTokenRecord] = []
        self.lookups = 0
        self.fail_with: Exception | None = None

    def _tick(self) -> None:
        self.lookups += 1
        if self.fail_with is not None:
            raise self.fail_with

    def add_user(self, user_id: str = USER_ID, access_token: str | None = INNER, status: str | None = "1", role: str | None = "owner") -> None:
        self.users[user_id] = UserRecord(id=user_id, access_token=access_token, status=status, is_superuser=False)
        if role:
            self.roles[user_id] = role

    def find_user_by_access_token(self, token: str) -> UserRecord | None:
        self._tick()
        return next((u for u in self.users.values() if u.access_token is not None and u.access_token.lower() == token.lower()), None)

    def find_user_by_id(self, user_id: str) -> UserRecord | None:
        self._tick()
        return self.users.get(user_id)

    def find_own_membership(self, user_id: str) -> MembershipRecord | None:
        self._tick()
        role = self.roles.get(user_id)
        return MembershipRecord(tenant_id=user_id, role=role) if role else None

    def find_api_token(self, token: str) -> ApiTokenRecord | None:
        self._tick()
        return next((r for r in self.api_tokens if r.token.lower() == token.lower()), None)

    def find_beta_token(self, beta: str) -> ApiTokenRecord | None:
        self._tick()
        return next((r for r in self.api_tokens if r.beta and r.beta.lower() == beta.lower()), None)


def _blueprint() -> Blueprint:
    bp = Blueprint("gate_probe", __name__)

    async def ok() -> Any:
        from quart import g

        from api.utils.api_utils import json_result

        p = getattr(g, "principal", None)
        if p is None:
            return json_result({"anonymous": True})
        return json_result({"user_id": p.user_id, "tenant_id": p.tenant_id, "role": p.role, "auth_type": p.auth_type})

    for path in (JWT_PATH, API_PATH, BETA_PATH, PUBLIC_PATH):
        bp.add_url_rule(path, endpoint=path, view_func=ok, methods=["GET", "POST"])
    return bp


def _signed(inner: str = INNER, **kwargs: Any) -> str:
    return tokens.dump(inner, STUB_SECRET, **kwargs)


def _app(store: FakeStore | None = None, **kwargs: Any) -> Any:
    store = store or FakeStore()
    resolver = auth_service.make_resolver(STUB_SECRET, store)
    app = create_app(memory_settings(**kwargs), extra_blueprints=(_blueprint(),), principal_resolver=resolver)
    app.extensions["fake_store"] = store
    return app


def _client(app: Any) -> QuartClient:
    return make_client(app, authenticated=False)


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _is_401(resp: Any) -> bool:
    return resp.status_code == 401 and await resp.get_json() == UNAUTHORIZED


@pytest.fixture
def store() -> FakeStore:
    s = FakeStore()
    s.add_user()
    return s


# --- default deny ----------------------------------------------------------------------------


async def test_no_credential_is_401_envelope_on_every_credential_type(store):
    client = _client(_app(store))
    for path in (JWT_PATH, API_PATH, BETA_PATH, "/api/v1/unknown-" + "x" * 8, "/v1/unknown-x", "/nope"):
        resp = await client.get(path)
        assert await _is_401(resp), path
        assert resp.headers["X-API-Source"] == "python"
    assert store.lookups == 0, "a request with no credential never reaches the database"


async def test_public_row_needs_no_credential(store):
    resp = await _client(_app(store)).get(PUBLIC_PATH)
    assert resp.status_code == 200
    assert (await resp.get_json())["data"] == {"anonymous": True}


async def test_unknown_path_is_401_unauthenticated_and_404_authenticated(store):
    client = _client(_app(store))
    token = _signed()
    assert await _is_401(await client.get("/api/v1/nothing-here"))
    resp = await client.get("/api/v1/nothing-here", headers=_bearer(token))
    assert resp.status_code == 404
    assert await resp.get_json() == {"code": 404, "message": "not found", "data": None}


async def test_protected_row_is_denied_before_the_method_is_considered(store):
    client = _client(_app(store))
    assert (await client.post("/api/v1/system/healthz")).status_code == 405, "a public row lets the method error surface"
    assert await _is_401(await client.post("/api/v1/system/status")), "a protected row answers 401 before 405"


# --- jwt ---------------------------------------------------------------------------------------


async def test_valid_token_resolves_principal(store):
    resp = await _client(_app(store)).get(JWT_PATH, headers=_bearer(_signed()))
    assert resp.status_code == 200
    data = (await resp.get_json())["data"]
    assert data == {"user_id": USER_ID, "tenant_id": USER_ID, "role": "owner", "auth_type": "jwt"}


async def test_raw_header_without_bearer_prefix_is_accepted(store):
    resp = await _client(_app(store)).get(JWT_PATH, headers={"Authorization": _signed()})
    assert resp.status_code == 200


def _bad_tokens() -> dict[str, str]:
    good = _signed()
    head, _, tail = good.rpartition(".")
    # Change the first signature character: the last one carries unused trailing bits, so swapping it can decode to
    # the same bytes and leave the token valid.
    flipped = ("A" if tail[0] != "A" else "B") + tail[1:]
    now = int(time.time())
    return {
        "empty_bearer": "",
        "garbage": "not-a-token",
        "tampered_signature": f"{head}.{flipped}",
        "wrong_secret": tokens.dump(INNER, "another-fake-secret-0123456789abcdef0123"),
        "expired_by_one_second": tokens.dump(INNER, STUB_SECRET, now=now - tokens.MAX_AGE_SECONDS - 2),
        "future_timestamp": tokens.dump(INNER, STUB_SECRET, now=now + 3600),
        "invalid_prefixed_inner": _signed("INVALID_" + "0" * 32),
        "short_inner": _signed("short"),
        "whitespace_inner": _signed(" " * 40),
        "overlong": "a" * 1025,
    }


@pytest.mark.parametrize("name", sorted(_bad_tokens()))
async def test_bad_token_classes_are_401_without_a_database_lookup(store, name):
    token = _bad_tokens()[name]
    client = _client(_app(store))
    resp = await client.get(JWT_PATH, headers=_bearer(token) if token else {"Authorization": "Bearer "})
    assert await _is_401(resp), name
    assert store.lookups == 0, "signature, age and AUTH-08 are checked before any database call (T-02-59)"


async def test_signed_inner_that_is_not_the_stored_token_is_401(store):
    resp = await _client(_app(store)).get(JWT_PATH, headers=_bearer(_signed(OTHER_INNER)))
    assert await _is_401(resp)


async def test_logged_out_user_token_is_401(store):
    store.users[USER_ID] = UserRecord(id=USER_ID, access_token="INVALID_" + "0" * 32, status="1", is_superuser=False)
    assert await _is_401(await _client(_app(store)).get(JWT_PATH, headers=_bearer(_signed())))


async def test_disabled_user_status_zero_is_401(store):
    store.add_user(status="0")
    assert await _is_401(await _client(_app(store)).get(JWT_PATH, headers=_bearer(_signed())))


async def test_user_without_status_or_token_is_401(store):
    store.add_user(status=None)
    assert await _is_401(await _client(_app(store)).get(JWT_PATH, headers=_bearer(_signed())))
    store.add_user(access_token=None)
    assert await _is_401(await _client(_app(store)).get(JWT_PATH, headers=_bearer(_signed())))


async def test_stored_token_must_match_exactly_not_by_collation(store):
    store.add_user(access_token=INNER.upper())
    assert await _is_401(await _client(_app(store)).get(JWT_PATH, headers=_bearer(_signed(INNER.lower()))))


async def test_invite_only_membership_means_no_tenant(store):
    store.add_user(role="invite")
    data = (await (await _client(_app(store)).get(JWT_PATH, headers=_bearer(_signed()))).get_json())["data"]
    assert data["tenant_id"] == "" and data["role"] == ""


# --- cookie and CSRF (D-21) ---------------------------------------------------------------------


async def test_cookie_authenticates_a_safe_request(store):
    client = _client(_app(store))
    resp = await client.get(JWT_PATH, headers={"Cookie": f"ragflow_auth={_signed()}"})
    assert resp.status_code == 200


async def test_cookie_only_post_without_origin_is_403(store):
    client = _client(_app(store))
    resp = await client.post(JWT_PATH, headers={"Cookie": f"ragflow_auth={_signed()}"})
    assert resp.status_code == 403
    assert await resp.get_json() == FORBIDDEN
    assert store.lookups == 0, "the origin check happens before any lookup"


@pytest.mark.parametrize(
    ("headers", "expected"),
    [
        ({"Origin": "http://evil.test"}, 403),
        ({"Origin": "null"}, 403),
        ({"Referer": "http://evil.test/page"}, 403),
        ({"Origin": "http://localhost:9999"}, 403),
        ({"Origin": "http://localhost"}, 200),
        ({"Referer": "http://localhost/page?x=1"}, 200),
    ],
)
async def test_cookie_post_origin_rule(store, headers, expected):
    client = _client(_app(store))
    resp = await client.post(JWT_PATH, headers={"Cookie": f"ragflow_auth={_signed()}", **headers})
    assert resp.status_code == expected


async def test_forwarded_host_is_trusted_only_from_a_loopback_peer(store):
    client = _client(_app(store))
    hdr = {"Cookie": f"ragflow_auth={_signed()}", "Origin": "http://public.example.test:8088", "X-Forwarded-Host": "public.example.test:8088"}
    loopback = await client.post(JWT_PATH, headers=hdr, scope_base={"client": ("127.0.0.1", 40000)})
    assert loopback.status_code == 200, "the proxy in the same container supplies the public host"
    direct = await client.post(JWT_PATH, headers=hdr, scope_base={"client": ("198.51.100.9", 40000)})
    assert direct.status_code == 403, "R-114: a non-loopback peer cannot choose the host it is compared with"


async def test_allow_listed_origin_passes_the_csrf_check(store):
    client = _client(_app(store, allowed_origins=("http://trusted.example.test",)))
    resp = await client.post(JWT_PATH, headers={"Cookie": f"ragflow_auth={_signed()}", "Origin": "http://trusted.example.test"})
    assert resp.status_code == 200


async def test_bearer_post_needs_no_origin(store):
    assert (await _client(_app(store)).post(JWT_PATH, headers=_bearer(_signed()))).status_code == 200


async def test_header_beats_cookie(store):
    client = _client(_app(store))
    hdr = {**_bearer("garbage"), "Cookie": f"ragflow_auth={_signed()}"}
    assert await _is_401(await client.get(JWT_PATH, headers=hdr)), "a bad header is not rescued by a good cookie"
    hdr = {**_bearer(_signed()), "Cookie": "ragflow_auth=garbage"}
    assert (await client.get(JWT_PATH, headers=hdr)).status_code == 200, "a bad cookie is ignored when the header is valid"


async def test_cookie_is_never_read_on_api_or_beta_routes(store):
    store.api_tokens.append(ApiTokenRecord(tenant_id=USER_ID, token=API_TOKEN, beta=BETA_TOKEN))
    client = _client(_app(store))
    for path in (API_PATH, BETA_PATH):
        for cookie in (_signed(), API_TOKEN, BETA_TOKEN):
            assert await _is_401(await client.get(path, headers={"Cookie": f"ragflow_auth={cookie}"})), path


# --- api and beta credential types ---------------------------------------------------------------


async def test_api_token_resolves_to_its_own_tenant(store):
    store.api_tokens.append(ApiTokenRecord(tenant_id=USER_ID, token=API_TOKEN, beta=None))
    resp = await _client(_app(store)).get(API_PATH, headers=_bearer(API_TOKEN))
    assert resp.status_code == 200
    data = (await resp.get_json())["data"]
    assert data == {"user_id": USER_ID, "tenant_id": USER_ID, "role": "owner", "auth_type": "api"}


def test_a_token_principal_never_carries_superuser_rights(store):
    """Plan 02-20: a long-lived plaintext token must not confer superuser, even when its owner is one."""
    store.users[USER_ID] = UserRecord(id=USER_ID, access_token=INNER, status="1", is_superuser=True)
    store.roles[USER_ID] = "owner"
    store.api_tokens.append(ApiTokenRecord(tenant_id=USER_ID, token=API_TOKEN, beta="b" * 32))
    resolve = auth_service.make_resolver(STUB_SECRET, store)
    session = resolve(tokens.dump(INNER, STUB_SECRET), (auth_service.AUTH_JWT,))
    assert session is not None and session.is_superuser is True
    for credential, types, kind in [(API_TOKEN, (auth_service.AUTH_API,), "api"), ("b" * 32, (auth_service.AUTH_BETA,), "beta")]:
        principal = resolve(credential, types)
        assert principal is not None and principal.auth_type == kind
        assert principal.is_superuser is False


async def test_api_token_of_a_missing_or_disabled_owner_is_401(store):
    store.api_tokens.append(ApiTokenRecord(tenant_id="ghost" + "0" * 27, token=API_TOKEN, beta=None))
    assert await _is_401(await _client(_app(store)).get(API_PATH, headers=_bearer(API_TOKEN)))
    store.api_tokens[:] = [ApiTokenRecord(tenant_id=USER_ID, token=API_TOKEN, beta=None)]
    store.add_user(status="0")
    assert await _is_401(await _client(_app(store)).get(API_PATH, headers=_bearer(API_TOKEN)))


async def test_api_route_accepts_an_access_token_too(store):
    assert (await _client(_app(store)).get(API_PATH, headers=_bearer(_signed()))).status_code == 200


async def test_api_credential_on_a_jwt_only_route_is_401(store):
    store.api_tokens.append(ApiTokenRecord(tenant_id=USER_ID, token=API_TOKEN, beta=BETA_TOKEN))
    client = _client(_app(store))
    assert await _is_401(await client.get(JWT_PATH, headers=_bearer(API_TOKEN)))
    assert await _is_401(await client.get(JWT_PATH, headers=_bearer(BETA_TOKEN)))
    assert store.lookups == 0, "a credential that cannot be a jwt on a jwt-only route is rejected before the database"


async def test_api_token_must_match_exactly_not_by_collation(store):
    store.api_tokens.append(ApiTokenRecord(tenant_id=USER_ID, token=API_TOKEN, beta=None))
    assert await _is_401(await _client(_app(store)).get(API_PATH, headers=_bearer(API_TOKEN.lower())))


async def test_beta_value_is_accepted_only_on_beta_routes(store):
    store.api_tokens.append(ApiTokenRecord(tenant_id=USER_ID, token=API_TOKEN, beta=BETA_TOKEN))
    client = _client(_app(store))
    resp = await client.get(BETA_PATH, headers=_bearer(BETA_TOKEN))
    assert resp.status_code == 200
    assert (await resp.get_json())["data"]["auth_type"] == "beta"
    assert await _is_401(await client.get(API_PATH, headers=_bearer(BETA_TOKEN))), "an api route does not accept a beta token"
    assert await _is_401(await client.get(JWT_PATH, headers=_bearer(BETA_TOKEN)))


@pytest.mark.parametrize("bad", ["c" * 32, "b" * 31, "b" * 33, "", "B" * 32, "x-" * 16])
async def test_wrong_or_absent_beta_value_is_401_not_a_business_code(store, bad):
    store.api_tokens.append(ApiTokenRecord(tenant_id=USER_ID, token=API_TOKEN, beta=BETA_TOKEN))
    headers = _bearer(bad) if bad else {}
    resp = await _client(_app(store)).get(BETA_PATH, headers=headers)
    assert resp.status_code == 401
    assert await resp.get_json() == UNAUTHORIZED


async def test_beta_route_also_accepts_access_and_api_tokens(store):
    store.api_tokens.append(ApiTokenRecord(tenant_id=USER_ID, token=API_TOKEN, beta=BETA_TOKEN))
    client = _client(_app(store))
    assert (await client.get(BETA_PATH, headers=_bearer(_signed()))).status_code == 200
    assert (await client.get(BETA_PATH, headers=_bearer(API_TOKEN))).status_code == 200


# --- preflight ----------------------------------------------------------------------------------


async def test_options_preflight_is_not_401():
    app = _app(allowed_origins=("http://a.test",))
    resp = await _client(app).options(JWT_PATH, headers={"Origin": "http://a.test", "Access-Control-Request-Method": "GET"})
    assert resp.status_code != 401
    assert resp.headers.get("Access-Control-Allow-Origin") == "http://a.test", "CORS still answers the preflight (order of hooks)"


# --- R-114: infrastructure errors fail closed with 503, never 401 ------------------------------------


class _Raising:
    def __init__(self, exc: Exception) -> None:
        self.exc = exc
        self.calls = 0

    def __call__(self, credential: str, allowed_types: tuple[str, ...]) -> Principal | None:
        self.calls += 1
        raise self.exc


async def test_infrastructure_error_is_503_envelope_without_detail():
    resolver = _Raising(AuthInfrastructureError("database"))
    app = make_test_app(authenticated=False, resolver=resolver)
    resp = await _client(app).get(JWT_PATH, headers=_bearer(_signed()))
    assert resp.status_code == 503
    body = await resp.get_data(as_text=True)
    assert json.loads(body) == UNAVAILABLE
    assert "database" not in body


async def test_malformed_token_is_401_and_never_calls_the_resolver():
    resolver = _Raising(AuthInfrastructureError("database"))
    app = make_test_app(authenticated=False, resolver=resolver)
    resp = await _client(app).get(JWT_PATH, headers=_bearer("garbage"))
    assert await _is_401(resp)
    assert resolver.calls == 0


async def test_lookup_returning_no_row_is_401_not_503():
    app = make_test_app(authenticated=False, resolver=StubPrincipalResolver(token="a-different-token"))
    resp = await _client(app).get(JWT_PATH, headers=_bearer(_signed()))
    assert await _is_401(resp)


async def test_resolver_timeout_is_503(monkeypatch):
    monkeypatch.setattr("api.apps.auth.LOOKUP_TIMEOUT_SECONDS", 0.05)

    def slow(credential: str, allowed_types: tuple[str, ...]) -> Principal | None:
        threading.Event().wait(timeout=0.5)  # a dependency that blocks past the gate's lookup timeout
        return None

    app = make_test_app(authenticated=False, resolver=slow)
    resp = await _client(app).get(JWT_PATH, headers=_bearer(_signed()))
    assert resp.status_code == 503
    assert await resp.get_json() == UNAVAILABLE


@pytest.mark.parametrize(
    "exc",
    [
        pytest.param(__import__("peewee").OperationalError(2003, "can't connect"), id="mysql-error"),
        pytest.param(TimeoutError("timed out"), id="timeout"),
        pytest.param(__import__("peewee").InterfaceError("connection already closed"), id="closed-connection"),
        pytest.param(__import__("pymysql").err.InterfaceError(0, ""), id="driver-interface-error"),
    ],
)
async def test_every_store_failure_class_is_503_through_the_real_service(store, exc):
    store.fail_with = exc
    client = _client(_app(store))
    resp = await client.get(JWT_PATH, headers=_bearer(_signed()))
    assert resp.status_code == 503, "never 401 for an infrastructure failure"
    assert await resp.get_json() == UNAVAILABLE


async def test_infrastructure_log_line_carries_only_a_coarse_category(store, caplog):
    store.fail_with = RuntimeError("mysql://user:hunter2@db/secret_schema exploded")
    with caplog.at_level(logging.DEBUG):
        await _client(_app(store)).get(JWT_PATH, headers=_bearer(_signed()))
    text = " ".join(str(getattr(r, "category", "")) + r.getMessage() for r in caplog.records if r.name.startswith(("api", "ragflow")))
    assert "hunter2" not in text and "secret_schema" not in text
    assert any(r.getMessage().startswith("auth gate: infrastructure failure") for r in caplog.records)


# --- service-level behaviour on the shared token vectors ---------------------------------------------


VECTORS = json.loads((ROOT / "test" / "fixtures" / "access_token_vectors.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("vec", VECTORS["vectors"], ids=[v["id"] for v in VECTORS["vectors"]])
def test_service_agrees_with_the_shared_vectors(vec):
    store = FakeStore()
    store.add_user(access_token=VECTORS["inner"])
    got = auth_service.resolve_credential(vec["token"], ("jwt",), secret=VECTORS["secret"], store=store, now=int(vec["now"]))
    accepted = vec["expect"] == "ok" and vec["inner"] == VECTORS["inner"] and vec["inner_valid"]
    assert (got is not None) is accepted, vec["id"]


def test_precheck_is_pure_and_cheap():
    store = FakeStore()
    assert not auth_service.precheck("garbage", ("jwt",), STUB_SECRET)
    assert auth_service.precheck(_signed(), ("jwt",), STUB_SECRET)
    assert auth_service.precheck(API_TOKEN, ("jwt", "api"), STUB_SECRET)
    assert not auth_service.precheck(API_TOKEN, ("jwt",), STUB_SECRET)
    assert auth_service.precheck(BETA_TOKEN, ("beta", "jwt", "api"), STUB_SECRET)
    assert not auth_service.precheck(BETA_TOKEN, ("jwt", "api"), STUB_SECRET)
    assert store.lookups == 0


# --- no secrets in the request log (SEC-09) ----------------------------------------------------------


async def test_request_log_line_never_carries_credentials(store, caplog):
    client = _client(_app(store))
    token = _signed()
    with caplog.at_level(logging.DEBUG):
        await client.get(JWT_PATH, headers={**_bearer(token), "Cookie": f"ragflow_auth={FAKE_COOKIE_SECRET}"})
        await client.get(JWT_PATH, headers=_bearer("garbage-secret-credential"))
        await client.post(JWT_PATH, headers={"Cookie": f"ragflow_auth={FAKE_COOKIE_SECRET}"})
    lines = [r for r in caplog.records if r.name == "ragflow.access"]
    assert len(lines) == 3, "every request, including the denied ones, is logged"
    blob = json.dumps([{**r.__dict__, "args": None, "exc_info": None} for r in caplog.records], default=str)
    for secret in (token, FAKE_COOKIE_SECRET, "garbage-secret-credential", API_TOKEN, BETA_TOKEN):
        assert secret not in blob
    assert [r.status for r in lines] == [200, 401, 403]


# --- OpenAPI schema is authenticated (R-113) -----------------------------------------------------------


async def test_openapi_document_requires_authentication():
    app = make_test_app(authenticated=False)
    unauth = await app.test_client().get("/api/v1/openapi.json")
    assert await _is_401(unauth)
    authed = await make_client(app).get("/api/v1/openapi.json")
    assert authed.status_code == 200
    assert (await authed.get_json())["openapi"].startswith("3.")


async def test_system_status_requires_authentication_but_healthz_is_public():
    app = make_test_app(authenticated=False)
    client = app.test_client()
    for path in ("/api/v1/system/status", "/system/status"):
        assert await _is_401(await client.get(path)), path
    for path in ("/api/v1/system/healthz", "/system/healthz"):
        assert (await client.get(path)).status_code in (200, 503), "the probe answers; it is never 401"
    assert (await make_client(app).get("/api/v1/system/status")).status_code in (200, 503)


# --- the offline-export seam must not become a runtime bypass ---------------------------------------------


def _calls_with_keyword(path: Path, keyword: str) -> list[int]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [node.lineno for node in ast.walk(tree) if isinstance(node, ast.Call) and any(k.arg == keyword for k in node.keywords)]


def test_production_code_never_passes_a_principal_resolver():
    offenders = []
    for path in sorted((ROOT / "api").rglob("*.py")) + [ROOT / "common" / "settings.py"]:
        for line in _calls_with_keyword(path, "principal_resolver"):
            offenders.append(f"{path.relative_to(ROOT)}:{line}")
    assert offenders == [], "principal_resolver is a test and offline-export seam only"


def test_entrypoint_builds_the_app_with_the_default_resolver_only():
    source = (ROOT / "api" / "ragflow_server.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and getattr(n.func, "id", getattr(n.func, "attr", "")) == "create_app"]
    assert calls, "the entrypoint must build the app through create_app"
    for call in calls:
        assert [k.arg for k in call.keywords] == [], "create_app is called with positional settings only"
    assert "principal_resolver" not in source


def test_resolver_is_not_configurable_from_the_environment(monkeypatch):
    monkeypatch.setenv("PRINCIPAL_RESOLVER", "test.helpers.app:StubPrincipalResolver")
    app = create_app(memory_settings())
    assert app.extensions["principal_resolver"] is not StubPrincipalResolver
    assert not isinstance(app.extensions["principal_resolver"], StubPrincipalResolver)


def test_default_resolver_is_the_real_service(monkeypatch):
    app = create_app(memory_settings())
    resolver = app.extensions["principal_resolver"]
    assert getattr(resolver, "__module__", "") == auth_service.__name__


# --- loopback trust rule (R-114, R-115, R-116) -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("addr", "expected"),
    [
        ("127.0.0.1", True),
        ("::1", True),
        ("[::1]", True),
        ("::ffff:127.0.0.1", True),
        ("198.51.100.7", False),
        ("172.18.0.5", False),
        ("", False),
        (None, False),
        ("not-an-address", False),
    ],
)
def test_loopback_peer_rule_matches_the_go_rule(addr, expected):
    from common.security.proxy import is_loopback_peer

    assert is_loopback_peer(addr) is expected


def test_the_api_server_serves_no_static_files():
    assert not any(rule.endpoint == "static" for rule in create_app(memory_settings()).url_map.iter_rules())


# WR-07: auth lookups stuck on a stalled database must not starve the default executor, which the health
# probes and the superuser seed share through asyncio.to_thread.
async def test_stalled_auth_lookups_leave_the_default_executor_free(monkeypatch):
    import asyncio

    monkeypatch.setattr("api.apps.auth.LOOKUP_TIMEOUT_SECONDS", 0.05)
    release = threading.Event()

    def stalled(credential: str, allowed_types: tuple[str, ...]) -> Principal | None:
        release.wait(timeout=20)  # a database that does not answer
        return None

    app = make_test_app(authenticated=False, resolver=stalled)
    client = _client(app)
    default_workers = getattr(asyncio.get_running_loop()._default_executor, "_max_workers", None) or 36
    try:
        replies = await asyncio.gather(*[client.get(JWT_PATH, headers=_bearer(_signed())) for _ in range(default_workers + 8)])
        assert {r.status_code for r in replies} == {503}, "every stalled lookup is the fail-closed 503"
        probe = await asyncio.wait_for(asyncio.to_thread(lambda: "free"), timeout=1.0)
        assert probe == "free", "the shared default executor still serves other callers"
    finally:
        release.set()


def test_auth_lookups_run_on_a_dedicated_bounded_executor():
    from api.apps import auth

    pool = auth.AUTH_LOOKUP_EXECUTOR
    assert pool._max_workers == auth.AUTH_LOOKUP_WORKERS  # noqa: SLF001
    assert 1 <= auth.AUTH_LOOKUP_WORKERS <= 32
