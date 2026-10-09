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
from test.helpers.uploads import pdf_bytes, tenant_object_keys
from test.testcases._routes import ROUTES_FILE  # conf/routes.yaml

_PLACEHOLDER = re.compile(r"\{(\w+)\}")
TOKENS = "/api/v1/system/tokens"
PROVIDERS = "/api/v1/providers"
MODELS = "/api/v1/models"
MODELS_DEFAULT = "/api/v1/models/default"
DATASETS = "/api/v1/datasets"
UPLOAD = "/api/v1/documents/upload"
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
# Dataset names that belong to A's side only.
A_TEAM_DATASET = "matrix-a-team-" + uuid.uuid4().hex[:8]
A_PRIVATE_DATASET = "matrix-a-private-" + uuid.uuid4().hex[:8]


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
    registry: AccountRegistry | None = None  # the registry that owns (and cleans up) every account of this world
    a_team_dataset: dict[str, Any] = field(default_factory=dict)  # A's dataset with permission team
    a_private_dataset: dict[str, Any] = field(default_factory=dict)  # A's dataset with permission me

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

    def snapshot_models(self) -> Any:
        """A's configured models as the owner sees them (composite ids, dimensions, usage counters)."""
        resp = call(self.client, "GET", MODELS, self.a.token, {})
        assert resp.status_code == 200, resp.text
        return resp.json()["data"]

    def snapshot_defaults(self) -> Any:
        resp = call(self.client, "GET", MODELS_DEFAULT, self.a.token, {})
        assert resp.status_code == 200, resp.text
        return resp.json()["data"]

    def snapshot_datasets(self) -> Any:
        """A's datasets as their creator, the owner, sees them (both of A's own, with counters and times)."""
        resp = call(self.client, "GET", DATASETS, self.a.token, {}, query={"page_size": "100"})
        assert resp.status_code == 200, resp.text
        return resp.json()["data"]

    def snapshot_objects(self) -> list[str]:
        """Every object A's workspace holds in MinIO (by exact tenant prefix): an upload that crosses the boundary would add one."""
        return tenant_object_keys(self.a.tenant_id)

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
        return {
            "members": self.members(),
            "tokens": self.snapshot_tokens(),
            "memberships": roles,
            "providers": self.snapshot_providers(),
            "models": self.snapshot_models(),
            "defaults": self.snapshot_defaults(),
            "datasets": self.snapshot_datasets(),
            "objects": self.snapshot_objects(),
        }

    def a_identifiers(self) -> list[str]:
        """Values that belong to A's side only; none may ever appear in a response to B."""
        out = [self.a.tenant_id, self.a.user_id, self.a.email, self.a.nickname]
        for acc in (self.admin, self.normal, self.victim, self.pending):
            out += [acc.user_id, acc.email, acc.nickname]
        for tok in self.a_tokens:
            out += [str(tok["token"]), str(tok["beta"])]
        if self.fake is not None:
            out += [A_PROVIDER_KEY, A_CHAT_MODEL, A_EMBED_MODEL]
        for dataset in (self.a_team_dataset, self.a_private_dataset):
            out += [str(dataset.get("id", "")), str(dataset.get("name", ""))]
        return [v for v in out if v]


def a_embed_id() -> str:
    """The composite id of A's embedding model."""
    return f"{A_EMBED_MODEL}@{COMPAT}"


def _ok(resp: httpx.Response, what: str) -> dict[str, Any]:
    assert resp.status_code == 200 and resp.json().get("code") == 0, f"{what} failed: HTTP {resp.status_code}"
    return resp.json()


def resource_of(row: Row) -> str:
    """Which part of ``World.snapshot()`` a row's resource lives in."""
    if "/tokens" in row.path:
        return "tokens"
    if row.path.startswith(PROVIDERS):
        return "providers"
    if row.path.startswith(MODELS):
        return "models"
    if row.path.startswith(DATASETS):
        return "datasets"
    if row.path.startswith(UPLOAD):
        return "objects"
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
    world = World(client, a, b, pending, admin, normal, victim, spare, registry=registry)
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
        _ok(call(client, "PATCH", MODELS_DEFAULT, a.token, {}, body={"embedding": a_embed_id()}), "A chooses its embedding default")
        world.a_team_dataset = _ok(call(client, "POST", DATASETS, a.token, {}, body={"name": A_TEAM_DATASET, "permission": "team"}), "A creates a team dataset")["data"]
        world.a_private_dataset = _ok(call(client, "POST", DATASETS, a.token, {}, body={"name": A_PRIVATE_DATASET}), "A creates a private dataset")["data"]
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


def _dataset_detail(w: World) -> Target:
    return Target({"dataset_id": str(w.a_team_dataset["id"])}, _sender("GET", DATASETS + "/{dataset_id}", extra_fields=set()), w.snapshot_datasets)


BUILDERS: dict[str, Builder] = {
    "GET /api/v1/datasets/{dataset_id}": _dataset_detail,
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


def _refused_as_unavailable(resp: httpx.Response, what: str) -> None:
    assert resp.status_code == 400, f"{what}: HTTP {resp.status_code}"
    assert resp.json()["data"]["reason"] == "model_unavailable", what


def check_models_list(w: World) -> None:
    """GET /api/v1/models: the list is the caller's workspace's whatever workspace id the request carries; no credential field, ever."""
    before = w.snapshot_models()
    smuggle = {"tenant_id": w.a.tenant_id, "user_id": w.a.user_id, "owner_id": w.a.user_id}
    own_b = call(w.client, "GET", MODELS, w.b.token, {})
    assert own_b.status_code == 200, own_b.text
    _assert_no_a_data(own_b.text, w, "B's own model list")
    for who, label in ((w.b, "B"), (w.pending, "the pending invitee")):
        resp = call(w.client, "GET", MODELS, who.token, {}, query=smuggle)
        assert triple(resp) == NOT_FOUND, f"{label} naming tenant A's workspace must get the one not-found answer: {triple(resp)}"
        _assert_no_a_data(resp.text, w, f"the model list {label} asked for in A's name")
        plain = call(w.client, "GET", MODELS, who.token, {}, query={"type": "embedding"})
        assert plain.status_code == 200, plain.text
        _assert_no_a_data(plain.text, w, f"the embedding models of {label}")
    assert call(w.client, "GET", MODELS, w.b.token, {}).text == own_b.text, "B's own list is unchanged by the smuggled requests"
    for member in (w.normal, w.admin, w.victim):
        resp = call(w.client, "GET", MODELS, member.token, {}, query={"tenant_id": w.a.tenant_id})
        assert resp.status_code == 200, resp.text
        assert A_CHAT_MODEL in resp.text and A_EMBED_MODEL in resp.text, "a member of A sees A's models"
        assert _credential_free(resp.text) and A_PROVIDER_KEY not in resp.text
    a_token = str(w.a_tokens[0]["token"])
    as_token = call(w.client, "GET", MODELS, a_token, {})
    assert as_token.status_code == 200 and A_CHAT_MODEL in as_token.text and _credential_free(as_token.text)
    assert triple(call(w.client, "GET", MODELS, a_token, {}, query={"tenant_id": w.b.tenant_id})) == NOT_FOUND, "a token is pinned to its own workspace"
    assert triple(call(w.client, "GET", MODELS, w.b_api_token, {}, query={"tenant_id": w.a.tenant_id})) == NOT_FOUND
    assert w.snapshot_models() == before


def check_models_default_get(w: World) -> None:
    """GET /api/v1/models/default: another workspace's defaults are the one not-found answer; B's own hold none of A's ids."""
    before = w.snapshot_defaults()
    assert before["embedding"] == a_embed_id(), "A chose its embedding default when the world was built"
    smuggle = {"tenant_id": w.a.tenant_id, "user_id": w.a.user_id, "owner_id": w.a.user_id}
    for who, label in ((w.b, "B"), (w.pending, "the pending invitee")):
        resp = call(w.client, "GET", MODELS_DEFAULT, who.token, {}, query=smuggle)
        assert triple(resp) == NOT_FOUND, f"{label}: {triple(resp)}"
        _assert_no_a_data(resp.text, w, f"the defaults {label} asked for in A's name")
        own = call(w.client, "GET", MODELS_DEFAULT, who.token, {})
        assert own.status_code == 200, own.text
        _assert_no_a_data(own.text, w, f"the defaults of {label}")
        assert a_embed_id() not in own.text
    for member in (w.normal, w.admin, w.victim):
        resp = call(w.client, "GET", MODELS_DEFAULT, member.token, {}, query={"tenant_id": w.a.tenant_id})
        assert resp.status_code == 200 and resp.json()["data"] == before, resp.text
    a_token = str(w.a_tokens[0]["token"])
    assert call(w.client, "GET", MODELS_DEFAULT, a_token, {}).json()["data"] == before
    assert triple(call(w.client, "GET", MODELS_DEFAULT, w.b_api_token, {}, query={"tenant_id": w.a.tenant_id})) == NOT_FOUND
    assert w.snapshot_defaults() == before


def check_models_default_patch(w: World) -> None:
    """PATCH /api/v1/models/default: B cannot write into A's workspace, cannot adopt A's model, and a token cannot write at all."""
    before, snapshot = w.snapshot_defaults(), w.snapshot()
    for who, label in ((w.b, "B"), (w.pending, "the pending invitee")):
        resp = call(w.client, "PATCH", MODELS_DEFAULT, who.token, {}, body={"chat": None, "embedding": None, "tenant_id": w.a.tenant_id})
        assert triple(resp) == NOT_FOUND, f"{label}: {triple(resp)}"
        _assert_no_a_data(resp.text, w, f"the refused write of {label}")
    assert w.snapshot_defaults() == before, "a refused foreign write changed nothing"

    # A's composite ids are unavailable in B's own workspace, whatever else the body carries.
    for slot, value in (("embedding", a_embed_id()), ("chat", f"{A_CHAT_MODEL}@{COMPAT}")):
        resp = call(w.client, "PATCH", MODELS_DEFAULT, w.b.token, {}, body={slot: value})
        _refused_as_unavailable(resp, f"B adopts A's {slot} model")
        _assert_no_a_data(resp.text, w, "the refusal of B's attempt to adopt A's model")
    unknown = call(w.client, "PATCH", MODELS_DEFAULT, w.b.token, {}, body={"chat": None, "user_id": w.a.user_id})
    assert unknown.status_code == 400, "an unknown body field is refused, not ignored"
    assert w.snapshot_defaults() == before

    own = call(w.client, "PATCH", MODELS_DEFAULT, w.b.token, {}, body={"chat": None})
    assert _ok(own, "B clears its own chat default")["data"]["chat"] == ""
    _assert_no_a_data(own.text, w, "B's own defaults write")

    denied = call(w.client, "PATCH", MODELS_DEFAULT, w.normal.token, {}, body={"chat": None, "tenant_id": w.a.tenant_id})
    assert denied.status_code == 403, "a normal member of A may read the defaults, not change them"
    for token, label in ((w.b_api_token, "B's API token"), (str(w.a_tokens[0]["token"]), "A's API token")):
        resp = call(w.client, "PATCH", MODELS_DEFAULT, token, {}, body={"chat": None})
        assert resp.status_code == 401, f"{label} must not change defaults"
    assert w.snapshot_defaults() == before
    assert w.snapshot() == snapshot


def check_datasets_list(w: World) -> None:
    """GET /api/v1/datasets: the list is the acting workspace's; a private dataset is its creator's alone, for A's owner-level members too."""
    before = w.snapshot_datasets()
    smuggle = {"tenant_id": w.a.tenant_id, "user_id": w.a.user_id, "owner_id": w.a.user_id}
    own_b = call(w.client, "GET", DATASETS, w.b.token, {})
    assert own_b.status_code == 200, own_b.text
    _assert_no_a_data(own_b.text, w, "B's own dataset list")
    for who, label in ((w.b, "B"), (w.pending, "the pending invitee")):
        resp = call(w.client, "GET", DATASETS, who.token, {}, query=smuggle)
        assert triple(resp) == NOT_FOUND, f"{label} naming tenant A's workspace must get the one not-found answer: {triple(resp)}"
        _assert_no_a_data(resp.text, w, f"the dataset list {label} asked for in A's name")
        plain = call(w.client, "GET", DATASETS, who.token, {}, query={"page_size": "100", "keywords": "matrix"})
        assert plain.status_code == 200, plain.text
        _assert_no_a_data(plain.text, w, f"the dataset list of {label}")
    assert call(w.client, "GET", DATASETS, w.b.token, {}).text == own_b.text, "B's own list is unchanged by the smuggled requests"
    # A's members see the team dataset and never the owner's private one (D-27: no override for anyone).
    for member in (w.normal, w.admin, w.victim):
        resp = call(w.client, "GET", DATASETS, member.token, {}, query={"tenant_id": w.a.tenant_id, "page_size": "100"})
        assert resp.status_code == 200, resp.text
        assert A_TEAM_DATASET in resp.text, "a member of A sees A's team dataset"
        assert A_PRIVATE_DATASET not in resp.text and str(w.a_private_dataset["id"]) not in resp.text, "nobody but its creator sees a private dataset"
    token = str(w.a_tokens[0]["token"])
    as_token = call(w.client, "GET", DATASETS, token, {})
    assert as_token.status_code == 200 and A_TEAM_DATASET in as_token.text, as_token.text
    assert triple(call(w.client, "GET", DATASETS, token, {}, query={"tenant_id": w.b.tenant_id})) == NOT_FOUND, "a token is pinned to its own workspace"
    assert triple(call(w.client, "GET", DATASETS, w.b_api_token, {}, query={"tenant_id": w.a.tenant_id})) == NOT_FOUND
    # A member cannot open the owner's private dataset by its real id either: the one 404 of an absent id.
    absent = triple(call(w.client, "GET", DATASETS + "/{dataset_id}", w.normal.token, {"dataset_id": uuid.uuid4().hex}))
    assert absent == NOT_FOUND
    assert triple(call(w.client, "GET", DATASETS + "/{dataset_id}", w.normal.token, {"dataset_id": str(w.a_private_dataset["id"])})) == absent
    assert triple(call(w.client, "GET", DATASETS + "/{dataset_id}", w.admin.token, {"dataset_id": str(w.a_private_dataset["id"])})) == absent
    assert w.snapshot_datasets() == before


def check_datasets_create(w: World) -> None:
    """POST /api/v1/datasets: B creates nowhere near A, cannot adopt A's embedding model, and nothing mass-assigns; A's datasets do not change."""
    before, snapshot = w.snapshot_datasets(), w.snapshot()
    for who, label in ((w.b, "B"), (w.pending, "the pending invitee")):
        resp = call(w.client, "POST", DATASETS, who.token, {}, body={"name": "matrix-intruder", "tenant_id": w.a.tenant_id})
        assert triple(resp) == NOT_FOUND, f"{label}: {triple(resp)}"
        _assert_no_a_data(resp.text, w, f"the refused creation of {label}")
    resp = call(w.client, "POST", DATASETS, w.b.token, {}, body={"name": "matrix-b-adopts", "embd_id": a_embed_id()})
    _refused_as_unavailable(resp, "B uses A's embedding model")
    _assert_no_a_data(resp.text, w, "the refusal of B's attempt to use A's model")
    nothing = call(w.client, "POST", DATASETS, w.b.token, {}, body={"name": "matrix-b-nodefault"})
    assert nothing.status_code == 400 and nothing.json()["data"]["reason"] == "no_default_embedding", "B has no default; A's is not borrowed"
    _assert_no_a_data(nothing.text, w, "B's creation without a default")
    for field_name in ("created_by", "tenant_embd_id", "doc_num", "id"):
        mass = call(w.client, "POST", DATASETS, w.b.token, {}, body={"name": "matrix-b-mass", field_name: w.a.user_id})
        assert mass.status_code == 400, f"{field_name} cannot be assigned: HTTP {mass.status_code}"
    same_name = call(w.client, "POST", DATASETS, w.b.token, {}, body={"name": A_TEAM_DATASET})
    assert same_name.status_code == 400, "A's dataset names are not visible to B: B's own rules apply (no default model here)"
    for token, label in ((w.b_api_token, "B's API token"),):
        resp = call(w.client, "POST", DATASETS, token, {}, body={"name": "matrix-token", "tenant_id": w.a.tenant_id})
        assert triple(resp) == NOT_FOUND, f"{label} is pinned to B's workspace: {triple(resp)}"
    assert call(w.client, "GET", DATASETS, w.b.token, {}).json()["data"] == {"items": [], "total": 0}, "none of B's refused requests stored a dataset"
    assert w.snapshot_datasets() == before
    assert w.snapshot() == snapshot


def upload_file(w: World, token: str, dataset_id: str, *, query: Mapping[str, str] | None = None, name: str = "matrix-note.pdf") -> httpx.Response:
    """One multipart upload with the bearer under test. The dataset id travels in the query, where the route reads it."""
    w.client.cookies.clear()
    params = {"dataset_id": dataset_id, **(query or {})}
    return w.client.post(UPLOAD, headers=bearer(token), params=params, files=[("file", (name, pdf_bytes("matrix"), "application/pdf"))], timeout=60.0)


def check_documents_upload(w: World) -> None:
    """POST /api/v1/documents/upload: nobody outside A reaches A's datasets, nothing appears under A's prefix, and a workspace uploads into its own."""
    before = w.snapshot()
    assert before["objects"] == [], "A starts empty"
    smuggle = {"tenant_id": w.a.tenant_id, "user_id": w.a.user_id}
    for dataset in (w.a_team_dataset, w.a_private_dataset):
        dataset_id = str(dataset["id"])
        for token, label in ((w.b.token, "B"), (w.pending.token, "the pending invitee"), (w.b_api_token, "B's API token")):
            for query in (None, smuggle):
                resp = upload_file(w, token, dataset_id, query=query)
                assert triple(resp) == NOT_FOUND, f"{label}: {triple(resp)}"
                _assert_no_a_data(resp.text, w, f"the refused upload of {label}")
    absent = triple(upload_file(w, w.b.token, uuid.uuid4().hex))
    assert absent == NOT_FOUND
    for member in (w.normal, w.admin, w.victim):
        assert triple(upload_file(w, member.token, str(w.a_private_dataset["id"]))) == absent, "nobody but the creator reaches a private dataset (D-27)"
    assert triple(upload_file(w, w.b.token, "not-an-id")) == absent
    assert w.snapshot_objects() == [] and w.snapshot_datasets() == before["datasets"], "no object appeared under A's prefix and no counter moved"

    # A workspace uploads into its own dataset, with a session and with its API token; neither credential reaches the other workspace.
    assert w.registry is not None and w.fake is not None
    own = w.registry.register(prefix="mxu")
    embed = "matrix-u-embed-" + uuid.uuid4().hex[:8]
    saved = {"provider": COMPAT, "base_url": w.fake.stack_base_url, "api_key": "-".join(("matrix", "u", "provider", "key", "0003")), "models": [{"name": embed, "type": "embedding"}]}
    _ok(call(w.client, "PUT", PROVIDERS, own.token, {}, body=saved), "the extra workspace saves a provider")
    made = _ok(call(w.client, "POST", DATASETS, own.token, {}, body={"name": "matrix-own-" + uuid.uuid4().hex[:8], "embd_id": f"{embed}@{COMPAT}"}), "it creates a dataset")["data"]
    uploaded = upload_file(w, own.token, str(made["id"]))
    assert uploaded.status_code == 200 and uploaded.json()["data"][0]["dataset_id"] == made["id"], uploaded.text
    own_token = str(_ok(call(w.client, "POST", TOKENS, own.token, {}), "it creates an API token")["data"]["token"])
    assert upload_file(w, own_token, str(made["id"]), name="by-token.pdf").status_code == 200
    assert len(tenant_object_keys(own.tenant_id)) == 2
    assert triple(upload_file(w, own_token, str(w.a_team_dataset["id"]))) == NOT_FOUND, "a token is pinned to its own workspace"
    assert triple(upload_file(w, str(w.a_tokens[0]["token"]), str(made["id"]))) == NOT_FOUND, "A's token cannot reach another workspace's dataset"
    assert w.snapshot() == before


NO_ID_CHECKS: dict[str, NoIdCheck] = {
    "POST /api/v1/documents/upload": check_documents_upload,
    "GET /api/v1/datasets": check_datasets_list,
    "POST /api/v1/datasets": check_datasets_create,
    "GET /api/v1/providers": check_providers_list,
    "PUT /api/v1/providers": check_providers_save,
    "GET /api/v1/models": check_models_list,
    "GET /api/v1/models/default": check_models_default_get,
    "PATCH /api/v1/models/default": check_models_default_patch,
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
