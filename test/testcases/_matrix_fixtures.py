"""Support for the registry-driven cross-tenant matrix (plan 02-25, TEN-01, TEN-02, success criterion 5).

The rows come from the endpoints registry in ``conf/routes.yaml`` (every row with ``scope: tenant`` and
``implemented: true``); no endpoint list is written down in a test. Every such row must be covered by exactly one of

* ``BUILDERS``: the row has path parameters (a tenant id, a user id, a token). A builder creates tenant A's resource
  through the real API and returns a :class:`Target` that can replay the call with any ids.
* ``NO_ID_CHECKS``: the row has no path parameter (the tenant comes from the credential), so there is no id to swap.
  The entry is a list-isolation check.

A row in neither dict fails the matrix (see ``coverage_problems``). A later phase that adds a scope-tenant endpoint
must therefore extend this file in the same change.
"""
from __future__ import annotations

import json
import re
import secrets
import uuid
from collections.abc import Callable, Collection, Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import yaml

from test.helpers.accounts import Account, AccountRegistry
from test.helpers.fake_provider import FakeProvider
from test.testcases._routes import ROUTES_FILE  # conf/routes.yaml

_PLACEHOLDER = re.compile(r"\{(\w+)\}")
TOKENS = "/api/v1/system/tokens"
PROVIDERS = "/api/v1/providers"
PROVIDER_SLUG = "openai-compatible"
COMPAT = "OpenAI-API-Compatible"
NOT_FOUND = (404, 404, "not found")
CREDENTIAL_KEYS = ("last4", "base_url", "api_version")
# Made-up provider keys, built from parts. Tenant A's key must never appear in any answer to anyone.
A_PROVIDER_KEY = "-".join(("matrix", "a", "provider", "key", "0001"))
B_PROVIDER_KEY = "-".join(("matrix", "b", "provider", "key", "0002"))
# Model names that belong to A's side only (B's own calls use different names, so a name in B's answer is a leak).
A_CHAT_MODEL = "matrix-a-chat-" + uuid.uuid4().hex[:8]
A_EMBED_MODEL = "matrix-a-embed-" + uuid.uuid4().hex[:8]


@dataclass(frozen=True)
class Row:
    """One registry row with ``scope: tenant`` that is implemented."""

    method: str
    path: str
    auth: str
    roles: tuple[str, ...]

    @property
    def key(self) -> str:
        return f"{self.method} {self.path}"

    @property
    def params(self) -> tuple[str, ...]:
        return tuple(_PLACEHOLDER.findall(self.path))


def load_tenant_rows(path: Path = ROUTES_FILE) -> list[Row]:
    """Rows with scope tenant and implemented true, read from the registry file."""
    data: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
    return [
        Row(str(e["method"]).upper(), str(e["path"]), str(e.get("auth", "none")), tuple(e.get("roles") or ()))
        for e in data["endpoints"]
        if e.get("scope") == "tenant" and e.get("implemented") is True
    ]


# --- request plumbing -------------------------------------------------------------------------------------------


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def triple(resp: httpx.Response) -> tuple[int, Any, Any]:
    """(HTTP status, envelope code, envelope message): the tuple the matrix compares byte for byte."""
    try:
        body = resp.json()
    except ValueError:
        return resp.status_code, None, resp.text[:120]
    if not isinstance(body, dict):
        return resp.status_code, None, str(body)[:120]
    return resp.status_code, body.get("code"), body.get("message")


def random_value(name: str) -> list[str]:
    """Nonexistent ids for a placeholder: always a random 32-hex id, and for a token also a well-formed random token."""
    values = [uuid.uuid4().hex]
    if name == "token":
        values.append("ragflow-" + secrets.token_urlsafe(48)[:43])
    return values


def call(
    client: httpx.Client,
    method: str,
    template: str,
    token: str,
    ids: Mapping[str, str],
    *,
    body: Mapping[str, Any] | None = None,
    query: Mapping[str, str] | None = None,
    extra_body: Mapping[str, Any] | None = None,
) -> httpx.Response:
    """Send one request. ``extra_body`` is smuggled in underneath the route's own fields (ids in other positions)."""
    path = template.format(**ids)
    merged = {**(extra_body or {}), **(body or {})}
    # A fresh cookie jar per request: only the bearer under test authenticates, never a leftover session cookie.
    client.cookies.clear()
    return client.request(method, path, headers=bearer(token), params=dict(query) if query else None, json=merged if merged else None)


# --- the two-tenant world ---------------------------------------------------------------------------------------


@dataclass
class World:
    """Tenant A with a populated workspace, plus every kind of outsider that must not reach it."""

    client: httpx.Client
    a: Account  # owner of the workspace under test
    b: Account  # an unrelated tenant (the attacker)
    pending: Account  # B2: has only a pending invitation to A
    admin: Account  # member of A, role admin
    normal: Account  # member of A, role normal
    victim: Account  # member of A, role normal; the target of removal and role changes
    spare: Account  # registered, not in A; the target of an invitation
    a_tokens: list[dict[str, Any]] = field(default_factory=list)
    b_api_token: str = ""
    fake: FakeProvider | None = None  # the stack-mode fake provider A's provider points at
    provider_url: str = ""

    # reads performed as A -----------------------------------------------------------------------------------------
    def list_tokens(self, who: Account) -> list[dict[str, Any]]:
        resp = call(self.client, "GET", TOKENS, who.token, {}, query={"page_size": "100"})
        assert resp.status_code == 200, resp.text
        return list(resp.json()["data"])

    def members(self) -> list[dict[str, Any]]:
        resp = call(self.client, "GET", "/api/v1/tenants/{tenant_id}/users", self.a.token, {"tenant_id": self.a.tenant_id}, query={"page_size": "100"})
        assert resp.status_code == 200, resp.text
        return sorted(resp.json()["data"], key=lambda m: m["id"])

    def list_providers(self, who: Account, **query: str) -> httpx.Response:
        return call(self.client, "GET", PROVIDERS, who.token, {}, query=query or None)

    def snapshot_providers(self) -> Any:
        """A's provider list as the owner sees it (address, last4, models, dimensions, usage counters)."""
        resp = self.list_providers(self.a)
        assert resp.status_code == 200, resp.text
        return resp.json()["data"]

    def snapshot_tokens(self) -> Any:
        return sorted(self.list_tokens(self.a), key=lambda t: t["token"])

    def snapshot_members(self) -> Any:
        return self.members()

    def snapshot(self) -> dict[str, Any]:
        """Everything of A's that a cross-tenant call could touch, read as A and as the invited and joined users."""
        roles: dict[str, Any] = {}
        for name in ("pending", "admin", "normal", "victim"):
            who: Account = getattr(self, name)
            resp = call(self.client, "GET", "/v1/tenant/list", who.token, {})
            assert resp.status_code == 200, resp.text
            roles[name] = sorted((m["tenant_id"], m["role"]) for m in resp.json()["data"])
        return {"members": self.members(), "tokens": self.snapshot_tokens(), "memberships": roles, "providers": self.snapshot_providers()}

    def a_identifiers(self) -> list[str]:
        """Values that belong to A's side only; none may ever appear in a response to B."""
        out = [self.a.tenant_id, self.a.user_id, self.a.email, self.a.nickname]
        for acc in (self.admin, self.normal, self.victim, self.pending):
            out += [acc.user_id, acc.email, acc.nickname]
        for tok in self.a_tokens:
            out += [str(tok["token"]), str(tok["beta"])]
        if self.fake is not None:
            out += [A_PROVIDER_KEY, A_CHAT_MODEL, A_EMBED_MODEL]
        return [v for v in out if v]


def _ok(resp: httpx.Response, what: str) -> dict[str, Any]:
    assert resp.status_code == 200 and resp.json().get("code") == 0, f"{what} failed: HTTP {resp.status_code}"
    return resp.json()


def resource_of(row: Row) -> str:
    """Which part of ``World.snapshot()`` a row's resource lives in."""
    if "/tokens" in row.path:
        return "tokens"
    if row.path.startswith(PROVIDERS):
        return "providers"
    return "members"


def build_world(client: httpx.Client, registry: AccountRegistry, fake: FakeProvider | None = None) -> World:
    """Register the accounts through the real endpoints and build A's workspace through the real API.

    With ``fake`` (the stack-mode fake provider) A also gets a configured provider, saved through the real PUT.
    """
    a = registry.register(prefix="mxa")
    b = registry.register(prefix="mxb")
    pending = registry.register(prefix="mxp")
    admin = registry.register(prefix="mxm")
    normal = registry.register(prefix="mxn")
    victim = registry.register(prefix="mxv")
    spare = registry.register(prefix="mxs")
    world = World(client, a, b, pending, admin, normal, victim, spare)
    users = "/api/v1/tenants/{tenant_id}/users"
    ids = {"tenant_id": a.tenant_id}
    for member in (admin, normal, victim, pending):
        _ok(call(client, "POST", users, a.token, ids, body={"email": member.email}), "invite")
    for member in (admin, normal, victim):
        _ok(call(client, "PATCH", "/api/v1/tenants/{tenant_id}", member.token, ids, body={"action": "accept"}), "accept")
    _ok(call(client, "PATCH", users + "/{user_id}", a.token, {**ids, "user_id": admin.user_id}, body={"role": "admin"}), "promote")
    for _ in range(2):
        world.a_tokens.append(_ok(call(client, "POST", TOKENS, a.token, {}), "create token")["data"])
    world.b_api_token = str(_ok(call(client, "POST", TOKENS, b.token, {}), "create B token")["data"]["token"])
    if fake is not None:
        world.fake, world.provider_url = fake, fake.stack_base_url
        body = {
            "provider": COMPAT,
            "base_url": fake.stack_base_url,
            "api_key": A_PROVIDER_KEY,
            "models": [{"name": A_CHAT_MODEL, "type": "chat"}, {"name": A_EMBED_MODEL, "type": "embedding"}],
        }
        _ok(call(client, "PUT", PROVIDERS, a.token, {}, body=body), "A saves a provider")
    return world


# --- targets and builders (rows with path parameters) -----------------------------------------------------------


@dataclass
class Target:
    """How to replay one row against A's resource with arbitrary ids."""

    real: dict[str, str]  # placeholder -> the id of A's real resource
    send: Callable[..., httpx.Response]  # (client, token, ids, *, query=None, extra_body=None) -> response
    snapshot: Callable[[], Any]  # reads the resource back as A


Builder = Callable[[World], Target]
NoIdCheck = Callable[[World], None]


def _sender(
    method: str, template: str, body: Mapping[str, Any] | None = None, *, extra_fields: Collection[str] | None = None
) -> Callable[..., httpx.Response]:
    """``extra_fields`` limits the smuggled body fields to those the route's request model accepts (the Python provider routes
    answer 400 to an unknown field, by design: mass assignment is refused before any lookup). ``None`` passes everything."""

    def send(client: httpx.Client, token: str, ids: Mapping[str, str], *, query: Mapping[str, str] | None = None, extra_body: Mapping[str, Any] | None = None) -> httpx.Response:
        if extra_body is not None and extra_fields is not None:
            extra_body = {k: v for k, v in extra_body.items() if k in extra_fields}
        return call(client, method, template, token, ids, body=body, query=query, extra_body=extra_body)

    return send


def _delete_token(w: World) -> Target:
    return Target({"token": str(w.a_tokens[0]["token"])}, _sender("DELETE", TOKENS + "/{token}"), w.snapshot_tokens)


def _list_members(w: World) -> Target:
    return Target({"tenant_id": w.a.tenant_id}, _sender("GET", "/api/v1/tenants/{tenant_id}/users"), w.snapshot_members)


def _invite(w: World) -> Target:
    return Target({"tenant_id": w.a.tenant_id}, _sender("POST", "/api/v1/tenants/{tenant_id}/users", {"email": w.spare.email}), w.snapshot_members)


def _remove(w: World) -> Target:
    return Target({"tenant_id": w.a.tenant_id}, _sender("DELETE", "/api/v1/tenants/{tenant_id}/users", {"user_id": w.victim.user_id}), w.snapshot_members)


def _respond(w: World) -> Target:
    return Target({"tenant_id": w.a.tenant_id}, _sender("PATCH", "/api/v1/tenants/{tenant_id}", {"action": "accept"}), w.snapshot_members)


def _change_role(w: World) -> Target:
    return Target(
        {"tenant_id": w.a.tenant_id, "user_id": w.victim.user_id},
        _sender("PATCH", "/api/v1/tenants/{tenant_id}/users/{user_id}", {"role": "admin"}),
        w.snapshot_members,
    )


def _provider_target(w: World, method: str, template: str, body: Mapping[str, Any] | None = None, instance: bool = False) -> Target:
    real = {"provider": PROVIDER_SLUG, **({"instance": "default"} if instance else {})}
    return Target(real, _sender(method, template, body, extra_fields={"tenant_id"}), w.snapshot_providers)


def _delete_provider(w: World) -> Target:
    return _provider_target(w, "DELETE", PROVIDERS + "/{provider}")


def _provider_models(w: World) -> Target:
    return _provider_target(w, "GET", PROVIDERS + "/{provider}/models")


def _add_instance(w: World) -> Target:
    return _provider_target(w, "POST", PROVIDERS + "/{provider}/instances", {"models": [{"name": "matrix-extra-chat", "type": "chat"}]})


def _provider_instance(w: World) -> Target:
    return _provider_target(w, "GET", PROVIDERS + "/{provider}/instances/{instance}", instance=True)


BUILDERS: dict[str, Builder] = {
    "DELETE /api/v1/providers/{provider}": _delete_provider,
    "GET /api/v1/providers/{provider}/models": _provider_models,
    "POST /api/v1/providers/{provider}/instances": _add_instance,
    "GET /api/v1/providers/{provider}/instances/{instance}": _provider_instance,
    "DELETE /api/v1/system/tokens/{token}": _delete_token,
    "GET /api/v1/tenants/{tenant_id}/users": _list_members,
    "POST /api/v1/tenants/{tenant_id}/users": _invite,
    "DELETE /api/v1/tenants/{tenant_id}/users": _remove,
    "PATCH /api/v1/tenants/{tenant_id}": _respond,
    "PATCH /api/v1/tenants/{tenant_id}/users/{user_id}": _change_role,
}


# --- list-isolation checks (rows without a path parameter) -------------------------------------------------------


def _assert_no_a_data(text: str, w: World, what: str) -> None:
    leaked = [v for v in w.a_identifiers() if v in text]
    assert not leaked, f"{what} contains {len(leaked)} value(s) that belong to tenant A"


def check_tokens_list(w: World) -> None:
    """GET /api/v1/system/tokens: the list is the caller's tenant's, whatever id the request carries."""
    before = w.snapshot_tokens()
    created_b = _ok(call(w.client, "POST", TOKENS, w.b.token, {}), "B creates a token")["data"]
    smuggle = {"tenant_id": w.a.tenant_id, "user_id": w.a.user_id, "owner_id": w.a.user_id}
    for who, label in ((w.b, "B"), (w.pending, "the pending invitee"), (w.victim, "a member of A (their own tenant)"), (w.admin, "an admin of A (their own tenant)")):
        for query in (None, smuggle):
            resp = call(w.client, "GET", TOKENS, who.token, {}, query={"page_size": "100", **(query or {})})
            assert resp.status_code == 200, resp.text
            _assert_no_a_data(resp.text, w, f"the token list of {label}")
    listed_b = [t["token"] for t in w.list_tokens(w.b)]
    assert created_b["token"] in listed_b
    assert call(w.client, "GET", TOKENS, w.b_api_token, {}).status_code == 401, "an API token cannot manage tokens"
    assert w.snapshot_tokens() == before


def check_tokens_create(w: World) -> None:
    """POST /api/v1/system/tokens: B creates in B's tenant only, whatever B sends; A's list does not change."""
    before = w.snapshot_tokens()
    forced = "ragflow-" + "Z" * 43
    for extra in (None, {"tenant_id": w.a.tenant_id, "token": forced, "beta": "0" * 32, "dialog_id": w.a.user_id}):
        resp = call(w.client, "POST", TOKENS, w.b.token, {}, extra_body=extra, query={"tenant_id": w.a.tenant_id} if extra else None)
        created = _ok(resp, "B creates a token")["data"]
        assert created["token"] != forced, "a client-chosen token value must be ignored"
        assert created["token"] in [t["token"] for t in w.list_tokens(w.b)]
        assert created["token"] not in [t["token"] for t in w.list_tokens(w.a)]
        assert w.a.tenant_id not in resp.text
    assert call(w.client, "POST", TOKENS, w.b_api_token, {}).status_code == 401, "an API token cannot create tokens"
    assert w.snapshot_tokens() == before


def _credential_free(text: str) -> bool:
    keys = _keys_of(json.loads(text))
    return keys.isdisjoint(CREDENTIAL_KEYS)


def _keys_of(node: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(node, dict):
        for key, value in node.items():
            found.add(str(key))
            found |= _keys_of(value)
    elif isinstance(node, list):
        for item in node:
            found |= _keys_of(item)
    return found


def check_providers_list(w: World) -> None:
    """GET /api/v1/providers: the list is the caller's workspace's, whatever workspace id the request carries; credentials are role-gated."""
    before = w.snapshot_providers()
    smuggle = {"tenant_id": w.a.tenant_id, "user_id": w.a.user_id, "owner_id": w.a.user_id}
    own_b = w.list_providers(w.b)
    assert own_b.status_code == 200, own_b.text
    for who, label in ((w.b, "B"), (w.pending, "the pending invitee")):
        resp = w.list_providers(who, **smuggle)
        assert triple(resp) == NOT_FOUND, f"{label} naming tenant A's workspace must get the one not-found answer: {triple(resp)}"
        _assert_no_a_data(resp.text, w, f"the provider list {label} asked for in A's name")
        plain = w.list_providers(who, page_size="100")
        assert plain.status_code == 200, plain.text
        _assert_no_a_data(plain.text, w, f"the provider list of {label}")
    assert w.list_providers(w.b).text == own_b.text, "B's own list is unchanged by the smuggled requests"
    # A's members read A's list without credentials; the owner's holds them.
    for member in (w.normal, w.admin, w.victim):
        resp = w.list_providers(member, tenant_id=w.a.tenant_id)
        assert resp.status_code == 200, resp.text
        assert A_CHAT_MODEL in resp.text, "a member of A sees A's models"
        if member is w.admin:
            assert not _credential_free(resp.text), "an admin sees the address and last4"
        else:
            assert _credential_free(resp.text), "a normal member sees no address and no last4"
        assert A_PROVIDER_KEY not in resp.text
    # an API token reads the list, but never the credentials, although it inherits the owner's role (D-26)
    as_token = call(w.client, "GET", PROVIDERS, str(w.a_tokens[0]["token"]), {})
    assert as_token.status_code == 200 and A_CHAT_MODEL in as_token.text, as_token.text
    assert _credential_free(as_token.text), "an API token's list carries no address and no last4"
    assert not _credential_free(w.list_providers(w.a).text), "the same list as the owner holds them"
    assert triple(call(w.client, "GET", PROVIDERS, str(w.a_tokens[0]["token"]), {}, query={"tenant_id": w.b.tenant_id})) == NOT_FOUND, "a token is pinned to its own workspace"
    assert w.snapshot_providers() == before


def _provider_body(w: World, models: list[str], key: str, **extra: Any) -> dict[str, Any]:
    assert w.fake is not None
    return {"provider": COMPAT, "base_url": w.fake.stack_base_url, "api_key": key, "models": [{"name": m, "type": "chat"} for m in models], **extra}


def check_providers_save(w: World) -> None:
    """PUT /api/v1/providers: B can neither write into A's workspace nor change what A has; an API token cannot write keys at all."""
    assert w.fake is not None
    before, snapshot = w.snapshot_providers(), w.snapshot()
    w.fake.reset()
    for who, label in ((w.b, "B"), (w.pending, "the pending invitee")):
        resp = call(w.client, "PUT", PROVIDERS, who.token, {}, body=_provider_body(w, ["matrix-b-chat"], B_PROVIDER_KEY, tenant_id=w.a.tenant_id))
        assert triple(resp) == NOT_FOUND, f"{label}: {triple(resp)}"
        _assert_no_a_data(resp.text, w, f"the refused write of {label}")
    assert w.fake.requests == [], "a refused foreign write never reaches the provider"
    assert w.snapshot_providers() == before

    own = call(w.client, "PUT", PROVIDERS, w.b.token, {}, body=_provider_body(w, ["matrix-b-chat"], B_PROVIDER_KEY, user_id=w.a.user_id))
    assert own.status_code == 400, "an unknown body field is refused, not ignored"
    own = call(w.client, "PUT", PROVIDERS, w.b.token, {}, body=_provider_body(w, ["matrix-b-chat"], B_PROVIDER_KEY))
    created = _ok(own, "B saves in B's own workspace")["data"]
    assert created["configured"] is True and B_PROVIDER_KEY not in own.text
    _assert_no_a_data(own.text, w, "B's own save")
    listed_b = w.list_providers(w.b)
    assert "matrix-b-chat" in listed_b.text
    _assert_no_a_data(listed_b.text, w, "B's list after saving")
    assert w.snapshot_providers() == before, "B's save changed nothing of A's"
    assert w.snapshot()["providers"] == snapshot["providers"]

    for token, label in ((w.b_api_token, "B's API token"), (str(w.a_tokens[0]["token"]), "A's API token")):
        resp = call(w.client, "PUT", PROVIDERS, token, {}, body=_provider_body(w, ["matrix-api-chat"], B_PROVIDER_KEY))
        assert resp.status_code == 401, f"{label} must not write keys"
    assert w.snapshot_providers() == before


NO_ID_CHECKS: dict[str, NoIdCheck] = {
    "GET /api/v1/providers": check_providers_list,
    "PUT /api/v1/providers": check_providers_save,
    "GET /api/v1/system/tokens": check_tokens_list,
    "POST /api/v1/system/tokens": check_tokens_create,
}


# --- the guard --------------------------------------------------------------------------------------------------


def coverage_problems(rows: Iterable[Row], builders: Mapping[str, Builder] = BUILDERS, no_id_checks: Mapping[str, NoIdCheck] = NO_ID_CHECKS) -> list[str]:
    """One message per registry row that no fixture covers, and per fixture entry that matches no row."""
    problems: list[str] = []
    keys: set[str] = set()
    for row in rows:
        keys.add(row.key)
        if row.params:
            if row.key not in builders:
                problems.append(f"{row.key}: scope tenant with path parameters {list(row.params)} has no fixture builder; add one to BUILDERS in test/testcases/_matrix_fixtures.py")
        elif row.key not in no_id_checks:
            problems.append(f"{row.key}: scope tenant with no path parameter has no isolation check; add one to NO_ID_CHECKS in test/testcases/_matrix_fixtures.py")
    for key in [*builders, *no_id_checks]:
        if key not in keys:
            problems.append(f"{key}: fixture entry matches no implemented scope-tenant row of conf/routes.yaml; fix or remove the key")
    return problems
