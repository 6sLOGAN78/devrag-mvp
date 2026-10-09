"""Registry-driven role, stranger, token and visibility table over every Phase 3 route (plan 03-19).

D-07, D-08, D-09, D-19, D-20, D-26, D-27; TEN-13, SEC-02, KB-01.

``INVOKERS`` maps each implemented registry row under ``/api/v1/providers``, ``/api/v1/models``, ``/api/v1/datasets`` and
``/api/v1/documents`` to a function that builds one valid request against tenant A's resources. The table tests then replay every
row for every kind of caller: A's owner, admin and normal member (the status the row's ``roles`` promise), strangers (the one
not-found answer), and API tokens (401 on a session-only row, tenant A's data on an ``auth: api`` row, 404 for another
workspace's token). A Phase 3 row with no invoker fails the suite (``test_every_phase3_row_has_an_invoker``).

Rows that delete or change data prepare a disposable resource before each call (``PREPARE``), so the table runs in any order.
A refused call must leave everything of A's untouched (``World.snapshot``) and must never reach the provider.

Provider-test budget (10 per 300 s per workspace): A's workspace spends one save for the world, two for the PUT row, two for the
POST instances row and at most two for the DELETE provider row; every other save of this file uses its own account and workspace.
"""
from __future__ import annotations

import uuid
from collections.abc import Callable, Iterator, Mapping
from pathlib import Path
from typing import Any

import httpx
import pytest
import yaml

from test.helpers.accounts import TEST_PASSWORD, Account, AccountRegistry
from test.helpers.fake_provider import running_stack_fake_provider
from test.testcases._matrix_fixtures import (
    A_CHAT_MODEL,
    A_EMBED_MODEL,
    A_PROVIDER_KEY,
    A_TEAM_DATASET,
    COMPAT,
    DATASETS,
    MODELS,
    MODELS_DEFAULT,
    NOT_FOUND,
    PROVIDER_SLUG,
    PROVIDERS,
    World,
    a_embed_id,
    build_world,
    call,
    triple,
    upload_file,
)
from test.testcases._routes import ROUTES_FILE
from test.testcases.conftest import BASE_URL

PHASE3_PREFIXES = ("/api/v1/providers", "/api/v1/models", "/api/v1/datasets", "/api/v1/documents")
FORBIDDEN = (403, 403, "forbidden")
UNAUTHORIZED = 401


def phase3_rows(path: Path = ROUTES_FILE) -> list[dict[str, Any]]:
    """Every implemented registry row of the Phase 3 route families, whatever its scope."""
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return [
        {"key": f"{str(e['method']).upper()} {e['path']}", "auth": str(e.get("auth", "none")), "roles": tuple(e.get("roles") or ())}
        for e in data["endpoints"]
        if e.get("implemented") is True and str(e["path"]).startswith(PHASE3_PREFIXES)
    ]


# --- requests ------------------------------------------------------------------------------------------------------


Invoker = Callable[[World, "Account | None", str, "str | None"], httpx.Response]


def _query(as_tenant: str | None, **extra: str) -> dict[str, str] | None:
    merged = {**extra, **({"tenant_id": as_tenant} if as_tenant else {})}
    return merged or None


def _body(as_tenant: str | None, **fields: Any) -> dict[str, Any]:
    return {**fields, **({"tenant_id": as_tenant} if as_tenant else {})}


def _team_id(w: World) -> str:
    return str(w.scratch.get("dataset_id") or w.a_team_dataset["id"])


def _unique(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _provider_save_body(w: World, as_tenant: str | None) -> dict[str, Any]:
    assert w.fake is not None
    models = [{"name": A_CHAT_MODEL, "type": "chat"}, {"name": A_EMBED_MODEL, "type": "embedding"}]
    return _body(as_tenant, provider=COMPAT, base_url=w.fake.stack_base_url, api_key=A_PROVIDER_KEY, models=models)


def _inv_list_providers(w: World, who: Account | None, token: str, as_tenant: str | None) -> httpx.Response:
    return call(w.client, "GET", PROVIDERS, token, {}, query=_query(as_tenant))


def _inv_save_provider(w: World, who: Account | None, token: str, as_tenant: str | None) -> httpx.Response:
    return call(w.client, "PUT", PROVIDERS, token, {}, body=_provider_save_body(w, as_tenant))


def _inv_delete_provider(w: World, who: Account | None, token: str, as_tenant: str | None) -> httpx.Response:
    return call(w.client, "DELETE", PROVIDERS + "/ollama", token, {}, query=_query(as_tenant))


def _inv_provider_models(w: World, who: Account | None, token: str, as_tenant: str | None) -> httpx.Response:
    return call(w.client, "GET", f"{PROVIDERS}/{PROVIDER_SLUG}/models", token, {}, query=_query(as_tenant))


def _inv_add_instance(w: World, who: Account | None, token: str, as_tenant: str | None) -> httpx.Response:
    body = _body(as_tenant, models=[{"name": _unique("iso-chat"), "type": "chat"}])
    return call(w.client, "POST", f"{PROVIDERS}/{PROVIDER_SLUG}/instances", token, {}, body=body)


def _inv_provider_instance(w: World, who: Account | None, token: str, as_tenant: str | None) -> httpx.Response:
    return call(w.client, "GET", f"{PROVIDERS}/{PROVIDER_SLUG}/instances/default", token, {}, query=_query(as_tenant))


def _inv_list_models(w: World, who: Account | None, token: str, as_tenant: str | None) -> httpx.Response:
    return call(w.client, "GET", MODELS, token, {}, query=_query(as_tenant))


def _inv_defaults(w: World, who: Account | None, token: str, as_tenant: str | None) -> httpx.Response:
    return call(w.client, "GET", MODELS_DEFAULT, token, {}, query=_query(as_tenant))


def _inv_set_defaults(w: World, who: Account | None, token: str, as_tenant: str | None) -> httpx.Response:
    return call(w.client, "PATCH", MODELS_DEFAULT, token, {}, body=_body(as_tenant, embedding=a_embed_id()))


def _inv_create_dataset(w: World, who: Account | None, token: str, as_tenant: str | None) -> httpx.Response:
    return call(w.client, "POST", DATASETS, token, {}, body=_body(as_tenant, name=_unique("iso-created"), permission="team"))


def _inv_list_datasets(w: World, who: Account | None, token: str, as_tenant: str | None) -> httpx.Response:
    return call(w.client, "GET", DATASETS, token, {}, query=_query(as_tenant, page_size="100"))


def _inv_dataset(w: World, who: Account | None, token: str, as_tenant: str | None) -> httpx.Response:
    return call(w.client, "GET", f"{DATASETS}/{_team_id(w)}", token, {})


def _inv_update_dataset(w: World, who: Account | None, token: str, as_tenant: str | None) -> httpx.Response:
    return call(w.client, "PUT", f"{DATASETS}/{_team_id(w)}", token, {}, body={"description": "isolation-table"})


def _inv_delete_datasets(w: World, who: Account | None, token: str, as_tenant: str | None) -> httpx.Response:
    return call(w.client, "DELETE", DATASETS, token, {}, body=_body(as_tenant, ids=[_team_id(w)]))


def _inv_upload(w: World, who: Account | None, token: str, as_tenant: str | None) -> httpx.Response:
    return upload_file(w, token, _team_id(w), query=_query(as_tenant), name=_unique("iso") + ".pdf")


def _inv_list_documents(w: World, who: Account | None, token: str, as_tenant: str | None) -> httpx.Response:
    return call(w.client, "GET", f"{DATASETS}/{_team_id(w)}/documents", token, {}, query={"page_size": "100"})


def _inv_delete_documents(w: World, who: Account | None, token: str, as_tenant: str | None) -> httpx.Response:
    document = str(w.scratch.get("document_id") or w.a_team_documents[0]["id"])
    return call(w.client, "DELETE", f"{DATASETS}/{_team_id(w)}/documents", token, {}, body={"ids": [document]})


INVOKERS: dict[str, Invoker] = {
    "GET /api/v1/providers": _inv_list_providers,
    "PUT /api/v1/providers": _inv_save_provider,
    "DELETE /api/v1/providers/{provider}": _inv_delete_provider,
    "GET /api/v1/providers/{provider}/models": _inv_provider_models,
    "POST /api/v1/providers/{provider}/instances": _inv_add_instance,
    "GET /api/v1/providers/{provider}/instances/{instance}": _inv_provider_instance,
    "GET /api/v1/models": _inv_list_models,
    "GET /api/v1/models/default": _inv_defaults,
    "PATCH /api/v1/models/default": _inv_set_defaults,
    "POST /api/v1/datasets": _inv_create_dataset,
    "GET /api/v1/datasets": _inv_list_datasets,
    "GET /api/v1/datasets/{dataset_id}": _inv_dataset,
    "PUT /api/v1/datasets/{dataset_id}": _inv_update_dataset,
    "DELETE /api/v1/datasets": _inv_delete_datasets,
    "POST /api/v1/documents/upload": _inv_upload,
    "GET /api/v1/datasets/{dataset_id}/documents": _inv_list_documents,
    "DELETE /api/v1/datasets/{dataset_id}/documents": _inv_delete_documents,
}

# Rows whose registry roles let a normal member in, but whose object-level rule refuses a member for A's dataset or document
# (settings and delete are for the creator, an owner or an admin; a document is removed by its uploader or those).
NORMAL_IS_REFUSED_ON_A_RESOURCE = frozenset({"PUT /api/v1/datasets/{dataset_id}", "DELETE /api/v1/datasets", "DELETE /api/v1/datasets/{dataset_id}/documents"})
# Rows whose resource is addressed by a dataset id: a stranger reaches nothing even without naming the workspace.
ID_ROWS = frozenset(
    {
        "GET /api/v1/datasets/{dataset_id}",
        "PUT /api/v1/datasets/{dataset_id}",
        "DELETE /api/v1/datasets",
        "POST /api/v1/documents/upload",
        "GET /api/v1/datasets/{dataset_id}/documents",
        "DELETE /api/v1/datasets/{dataset_id}/documents",
    }
)
# Rows that call the model provider with the stored key: a refused request must never reach it.
PROVIDER_CALLING_ROWS = frozenset({"PUT /api/v1/providers", "POST /api/v1/providers/{provider}/instances"})


def invoker_problems(rows: list[dict[str, Any]], invokers: Mapping[str, Invoker] = INVOKERS) -> list[str]:
    """One message per Phase 3 row with no invoker and per invoker (or override) that matches no row."""
    keys = {r["key"] for r in rows}
    problems = [f"{r['key']}: Phase 3 row has no invoker; add one to INVOKERS in test/testcases/test_phase3_isolation.py" for r in rows if r["key"] not in invokers]
    problems += [f"{k}: invoker matches no implemented Phase 3 row of conf/routes.yaml; fix or remove the key" for k in invokers if k not in keys]
    for name, table in (("NORMAL_IS_REFUSED_ON_A_RESOURCE", NORMAL_IS_REFUSED_ON_A_RESOURCE), ("ID_ROWS", ID_ROWS), ("PROVIDER_CALLING_ROWS", PROVIDER_CALLING_ROWS), ("PREPARE", PREPARE)):
        problems += [f"{k}: {name} matches no implemented Phase 3 row" for k in table if k not in keys]
    return problems


# --- the disposable resources a row needs before each call ----------------------------------------------------------


def _ok_data(resp: httpx.Response, what: str) -> Any:
    assert resp.status_code == 200 and resp.json().get("code") == 0, f"{what} failed: HTTP {resp.status_code}"
    return resp.json()["data"]


def _prepare_provider(w: World) -> None:
    """A configured Ollama provider for the delete row (a save only when it is not there: the budget is small)."""
    assert w.fake is not None
    if call(w.client, "GET", f"{PROVIDERS}/ollama/models", w.a.token, {}).status_code == 200:
        return
    body = {"provider": "Ollama", "base_url": w.fake.stack_ollama_url, "models": [{"name": "iso-ollama-chat", "type": "chat"}]}
    _ok_data(call(w.client, "PUT", PROVIDERS, w.a.token, {}, body=body), "A configures a disposable Ollama provider")


def _prepare_dataset(w: World) -> None:
    made = _ok_data(call(w.client, "POST", DATASETS, w.a.token, {}, body={"name": _unique("iso-disposable"), "permission": "team"}), "A creates a disposable dataset")
    w.scratch["dataset_id"] = str(made["id"])


def _prepare_document(w: World) -> None:
    w.scratch["document_id"] = str(_ok_data(upload_file(w, w.a.token, str(w.a_team_dataset["id"]), name=_unique("iso") + ".pdf"), "A uploads a disposable document")[0]["id"])


PREPARE: dict[str, Callable[[World], None]] = {
    "DELETE /api/v1/providers/{provider}": _prepare_provider,
    "DELETE /api/v1/datasets": _prepare_dataset,
    "DELETE /api/v1/datasets/{dataset_id}/documents": _prepare_document,
}


def run(w: World, key: str, who: Account | None, token: str, as_tenant: str | None, *, random_id: bool = False) -> tuple[httpx.Response, dict[str, Any] | None]:
    """Prepare the row's disposable resource, snapshot A, send the call. Returns the response and A's snapshot taken just before."""
    w.scratch.clear()
    PREPARE.get(key, lambda _w: None)(w)
    if random_id:
        w.scratch["dataset_id"] = uuid.uuid4().hex
        w.scratch["document_id"] = uuid.uuid4().hex
    before = w.snapshot()
    if w.fake is not None:
        w.fake.reset()
    return INVOKERS[key](w, who, token, as_tenant), before


def succeeded(resp: httpx.Response) -> bool:
    return resp.status_code == 200 and resp.json().get("code") == 0


# --- the world ------------------------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def world(ingress: httpx.Client) -> Iterator[World]:
    registry = AccountRegistry(BASE_URL)
    with running_stack_fake_provider() as fake, httpx.Client(base_url=BASE_URL, timeout=60.0, follow_redirects=False) as client:
        try:
            yield build_world(client, registry, fake)
        finally:
            registry.cleanup()


ROWS = phase3_rows()
ROW_PARAMS = [pytest.param(r, id=r["key"]) for r in ROWS]


# --- the guard (no stack needed) ------------------------------------------------------------------------------------


@pytest.mark.unit
def test_every_phase3_row_has_an_invoker() -> None:
    assert len(ROWS) >= 17, "the registry should list the seventeen Phase 3 rows"
    assert invoker_problems(ROWS) == []


@pytest.mark.unit
def test_the_guard_fails_a_row_without_an_invoker_and_an_invoker_without_a_row() -> None:
    extra = [*ROWS, {"key": "GET /api/v1/datasets/{dataset_id}/synthetic", "auth": "api", "roles": ("owner",)}]
    problems = invoker_problems(extra)
    assert len(problems) == 1 and "GET /api/v1/datasets/{dataset_id}/synthetic" in problems[0] and "no invoker" in problems[0]
    stale = invoker_problems(ROWS, {**INVOKERS, "GET /gone": _inv_list_providers})
    assert len(stale) == 1 and "GET /gone" in stale[0]


@pytest.mark.unit
def test_the_registry_rows_carry_the_roles_and_credential_kinds_the_table_assumes() -> None:
    by_key = {r["key"]: r for r in ROWS}
    for key in NORMAL_IS_REFUSED_ON_A_RESOURCE:
        assert "normal" in by_key[key]["roles"], f"{key}: the override is only needed when the registry lets a normal member in"
    jwt_rows = {k for k, r in by_key.items() if r["auth"] == "jwt"}
    assert jwt_rows == {
        "PUT /api/v1/providers",
        "DELETE /api/v1/providers/{provider}",
        "POST /api/v1/providers/{provider}/instances",
        "GET /api/v1/providers/{provider}/instances/{instance}",
        "PATCH /api/v1/models/default",
    }, "the session-only rows are the key-writing and credential-reading ones"
    assert all(r["auth"] in ("jwt", "api") for r in ROWS)


# --- roles ----------------------------------------------------------------------------------------------------------


def _role_callers(w: World) -> list[tuple[str, Account, str | None]]:
    return [("owner", w.a, None), ("admin", w.admin, w.a.tenant_id), ("normal", w.normal, w.a.tenant_id)]


@pytest.mark.e2e
@pytest.mark.parametrize("row", ROW_PARAMS)
def test_owner_admin_and_normal_get_the_status_the_row_promises(world: World, row: dict[str, Any]) -> None:
    key, roles = row["key"], row["roles"]
    for role, who, as_tenant in _role_callers(world):
        allowed = role in roles and not (role == "normal" and key in NORMAL_IS_REFUSED_ON_A_RESOURCE)
        resp, before = run(world, key, who, who.token, as_tenant)
        if allowed:
            assert succeeded(resp), f"{key} as {role}: HTTP {resp.status_code}, expected success"
            continue
        assert triple(resp) == FORBIDDEN, f"{key} as {role}: {triple(resp)}, expected 403"
        assert world.snapshot() == before, f"{key} as {role}: a refused call changed tenant A's data"
        if key in PROVIDER_CALLING_ROWS:
            assert world.fake is not None and world.fake.requests == [], f"{key} as {role}: a refused call reached the model provider"


# --- strangers ------------------------------------------------------------------------------------------------------


@pytest.mark.e2e
@pytest.mark.parametrize("row", ROW_PARAMS)
def test_strangers_get_the_one_not_found_answer_and_change_nothing(world: World, row: dict[str, Any]) -> None:
    key = row["key"]
    callers = [("stranger", world.b, world.a.tenant_id), ("pending invitee", world.pending, world.a.tenant_id), ("registered spare", world.spare, world.a.tenant_id)]
    if key in ID_ROWS:  # a dataset id reaches nothing even when the stranger does not name the workspace
        callers += [("stranger without the workspace", world.b, None)]
    for label, who, as_tenant in callers:
        resp, before = run(world, key, who, who.token, as_tenant)
        assert triple(resp) == NOT_FOUND, f"{key} as {label}: {triple(resp)}, expected the not-found answer"
        assert world.snapshot() == before, f"{key} as {label}: a refused call changed tenant A's data"
        leaked = [v for v in world.a_identifiers() if v in resp.text]
        assert not leaked, f"{key} as {label}: the answer holds {len(leaked)} value(s) of tenant A"
        if key in PROVIDER_CALLING_ROWS:
            assert world.fake is not None and world.fake.requests == [], f"{key} as {label}: a refused call reached the model provider"


@pytest.mark.e2e
@pytest.mark.parametrize("row", [pytest.param(r, id=r["key"]) for r in ROWS if r["key"] in ID_ROWS])
def test_a_real_dataset_id_is_answered_exactly_like_a_random_one(world: World, row: dict[str, Any]) -> None:
    key = row["key"]
    for who in (world.b, world.pending, world.spare):
        real, _ = run(world, key, who, who.token, world.a.tenant_id)
        absent, _ = run(world, key, who, who.token, world.a.tenant_id, random_id=True)
        assert triple(real) == triple(absent) == NOT_FOUND, f"{key}: the answer for A's real id differs from the answer for a random id"
        assert real.text == absent.text, f"{key}: the bodies differ"


# --- API tokens -----------------------------------------------------------------------------------------------------


@pytest.mark.e2e
@pytest.mark.parametrize("row", ROW_PARAMS)
def test_api_tokens_are_refused_on_session_rows_and_pinned_to_their_workspace_on_api_rows(world: World, row: dict[str, Any]) -> None:
    key, session_only = row["key"], row["auth"] == "jwt"
    a_token, b_token = str(world.a_tokens[0]["token"]), world.b_api_token
    if session_only:
        for label, token, as_tenant in (("A's token", a_token, None), ("A's token naming A", a_token, world.a.tenant_id), ("B's token naming A", b_token, world.a.tenant_id)):
            resp, before = run(world, key, None, token, as_tenant)
            assert resp.status_code == UNAUTHORIZED, f"{key} with {label}: HTTP {resp.status_code}, expected 401"
            assert world.snapshot() == before, f"{key} with {label}: a refused call changed tenant A's data"
            if key in PROVIDER_CALLING_ROWS:
                assert world.fake is not None and world.fake.requests == [], f"{key} with {label}: a refused call reached the model provider"
        return
    for label, as_tenant in (("A's token", None), ("A's token naming A", world.a.tenant_id)):
        resp, _ = run(world, key, None, a_token, as_tenant)
        assert succeeded(resp), f"{key} with {label}: HTTP {resp.status_code}, expected success in A's workspace"
        assert "last4" not in resp.text and "base_url" not in resp.text and "api_version" not in resp.text, f"{key} with {label}: a token sees credential fields"
    for label, token in (("B's token naming A", b_token),):
        resp, before = run(world, key, None, token, world.a.tenant_id)
        assert triple(resp) == NOT_FOUND, f"{key} with {label}: {triple(resp)}, expected the not-found answer"
        assert world.snapshot() == before, f"{key} with {label}: a refused call changed tenant A's data"
    if key in ID_ROWS:
        resp, before = run(world, key, None, b_token, None)
        assert triple(resp) == NOT_FOUND, f"{key} with B's token and A's dataset id: {triple(resp)}"
        assert world.snapshot() == before


@pytest.mark.e2e
def test_a_token_is_judged_as_its_user_not_elevated_to_the_workspace_role(world: World) -> None:
    """A's API token manages what A created, but is not elevated to A's owner role over a member's team dataset or document (D-26)."""
    w = world
    token = str(w.a_tokens[1]["token"])
    scope = {"tenant_id": w.a.tenant_id}
    shared = _ok_data(call(w.client, "POST", DATASETS, w.normal.token, {}, body={"name": _unique("iso-member-team"), "permission": "team", "tenant_id": w.a.tenant_id}), "the member creates a team dataset")
    dataset_id = str(shared["id"])
    # another member's document in the member's team dataset: the owner's session may manage both, the owner's token may not
    member_doc = _ok_data(upload_file(w, w.victim.token, dataset_id, query=scope), "another member uploads into the team dataset")[0]
    assert triple(call(w.client, "PUT", f"{DATASETS}/{dataset_id}", token, {}, body={"description": "elevated?"})) == FORBIDDEN
    assert triple(call(w.client, "DELETE", DATASETS, token, {}, body={"ids": [dataset_id]})) == FORBIDDEN
    team_docs = f"{DATASETS}/{dataset_id}/documents"
    assert triple(call(w.client, "DELETE", team_docs, token, {}, body={"ids": [member_doc["id"]]})) == FORBIDDEN
    assert succeeded(call(w.client, "GET", f"{DATASETS}/{dataset_id}", token, {})), "reading is not management"
    still = {d["id"] for d in _ok_data(call(w.client, "GET", team_docs, w.a.token, {}, query={"page_size": "100"}), "list")["items"]}
    assert member_doc["id"] in still, "the refused removal deleted nothing"
    # the owner's session is elevated; the token manages what its user created
    assert succeeded(call(w.client, "PUT", f"{DATASETS}/{dataset_id}", w.a.token, {}, body={"description": "by the owner session"}))
    assert succeeded(call(w.client, "DELETE", team_docs, w.a.token, {}, body={"ids": [member_doc["id"]]}))
    assert succeeded(call(w.client, "DELETE", DATASETS, w.a.token, {}, body={"ids": [dataset_id], "tenant_id": w.a.tenant_id}))
    mine = _ok_data(call(w.client, "POST", DATASETS, token, {}, body={"name": _unique("iso-token-own"), "permission": "team"}), "the token creates a dataset")
    assert mine["created_by"] == w.a.user_id
    assert succeeded(call(w.client, "PUT", f"{DATASETS}/{mine['id']}", token, {}, body={"description": "by the token"}))
    assert succeeded(call(w.client, "DELETE", DATASETS, token, {}, body={"ids": [mine["id"]]}))
    # a token never writes keys
    assert call(w.client, "PUT", PROVIDERS, token, {}, body=_provider_save_body(w, None)).status_code == UNAUTHORIZED


# --- visibility: team versus me (D-26, D-27) ---------------------------------------------------------------------------


def _names(resp: httpx.Response) -> set[str]:
    return {str(d["name"]) for d in _ok_data(resp, "list datasets")["items"]}


def _list_as(w: World, who: Account, as_tenant: str | None) -> httpx.Response:
    return call(w.client, "GET", DATASETS, who.token, {}, query=_query(as_tenant, page_size="100"))


@pytest.mark.e2e
def test_a_member_sees_a_team_dataset_but_not_the_private_dataset_of_the_same_creator(world: World) -> None:
    w = world
    for who in (w.normal, w.admin, w.victim):
        names = _names(_list_as(w, who, w.a.tenant_id))
        assert A_TEAM_DATASET in names, f"{who.nickname} sees the team dataset"
        assert str(w.a_private_dataset["name"]) not in names, "A's owner-created `me` dataset is the owner's alone"
        assert succeeded(call(w.client, "GET", f"{DATASETS}/{w.a_team_dataset['id']}", who.token, {}))
    # the owner and the admin never see the normal member's `me` dataset, and the normal member sees its own and not the owner's
    assert str(w.a_normal_private_dataset["name"]) in _names(_list_as(w, w.normal, w.a.tenant_id))
    assert str(w.a_normal_private_dataset["name"]) not in _names(_list_as(w, w.a, None)), "the workspace owner has no override"
    assert str(w.a_normal_private_dataset["name"]) not in _names(_list_as(w, w.admin, w.a.tenant_id)), "nor has an admin"
    assert str(w.a_private_dataset["name"]) in _names(_list_as(w, w.a, None))
    assert str(w.a_private_dataset["name"]) not in _names(_list_as(w, w.normal, w.a.tenant_id))


def _me_routes(w: World, token: str, dataset_id: str, document_id: str) -> list[tuple[str, httpx.Response]]:
    """Every dataset and document route aimed at one dataset id, with the workspace named wherever the route takes it."""
    scope = w.a.tenant_id
    return [
        ("GET dataset", call(w.client, "GET", f"{DATASETS}/{dataset_id}", token, {})),
        ("PUT dataset", call(w.client, "PUT", f"{DATASETS}/{dataset_id}", token, {}, body={"description": "should not apply"})),
        ("DELETE datasets", call(w.client, "DELETE", DATASETS, token, {}, body={"ids": [dataset_id], "tenant_id": scope})),
        ("upload", upload_file(w, token, dataset_id, query={"tenant_id": scope}, name=_unique("iso-me") + ".pdf")),
        ("GET documents", call(w.client, "GET", f"{DATASETS}/{dataset_id}/documents", token, {})),
        ("DELETE documents", call(w.client, "DELETE", f"{DATASETS}/{dataset_id}/documents", token, {}, body={"ids": [document_id]})),
    ]


@pytest.mark.e2e
def test_a_private_dataset_is_the_one_404_on_every_dataset_and_document_route_for_everyone_but_its_creator(world: World) -> None:
    w = world
    mine = _ok_data(call(w.client, "POST", DATASETS, w.normal.token, {}, body={"name": _unique("iso-me-doc"), "tenant_id": w.a.tenant_id}), "the normal member creates a `me` dataset")
    dataset_id = str(mine["id"])
    document = _ok_data(upload_file(w, w.normal.token, dataset_id, query={"tenant_id": w.a.tenant_id}), "the creator uploads")[0]
    state = {"documents": _ok_data(call(w.client, "GET", f"{DATASETS}/{dataset_id}/documents", w.normal.token, {}), "creator's list")}
    objects = w.snapshot_objects()

    cases: list[tuple[str, Account, str, str]] = [
        ("the workspace owner", w.a, w.a.token, dataset_id),
        ("an admin", w.admin, w.admin.token, dataset_id),
        ("another normal member", w.victim, w.victim.token, dataset_id),
        ("A's normal member on the owner's `me` dataset", w.normal, w.normal.token, str(w.a_private_dataset["id"])),
        ("an admin on the owner's `me` dataset", w.admin, w.admin.token, str(w.a_private_dataset["id"])),
        ("another normal member on the owner's `me` dataset", w.victim, w.victim.token, str(w.a_private_dataset["id"])),
    ]
    absent = triple(call(w.client, "GET", f"{DATASETS}/{uuid.uuid4().hex}", w.a.token, {}))
    assert absent == NOT_FOUND
    for label, _who, token, target in cases:
        doc = str(document["id"]) if target == dataset_id else str(w.a_private_documents[0]["id"])
        for route, resp in _me_routes(w, token, target, doc):
            assert triple(resp) == absent, f"{label}: {route} gave {triple(resp)} instead of the one not-found answer"
    # an admin acting through the workspace selector is no different
    for route, resp in _me_routes(w, w.admin.token, dataset_id, str(document["id"])):
        assert triple(resp) == absent, f"admin with tenant_id: {route}"
    # none of it changed anything: the creator still has the dataset, its document and its description, and no object appeared
    assert call(w.client, "GET", f"{DATASETS}/{dataset_id}", w.normal.token, {}).json()["data"]["description"] in (None, "")
    assert _ok_data(call(w.client, "GET", f"{DATASETS}/{dataset_id}/documents", w.normal.token, {}), "creator's list") == state["documents"]
    assert w.snapshot_objects() == objects
    assert succeeded(call(w.client, "GET", f"{DATASETS}/{w.a_private_dataset['id']}", w.a.token, {}))
    # lists name neither
    for who, as_tenant in ((w.a, None), (w.admin, w.a.tenant_id), (w.victim, w.a.tenant_id)):
        assert dataset_id not in _list_as(w, who, as_tenant).text
    # the creator manages it end to end
    assert succeeded(call(w.client, "PUT", f"{DATASETS}/{dataset_id}", w.normal.token, {}, body={"description": "by its creator"}))
    again = _ok_data(upload_file(w, w.normal.token, dataset_id, query={"tenant_id": w.a.tenant_id}, name=_unique("iso-me2") + ".pdf"), "the creator uploads again")[0]
    listed = _ok_data(call(w.client, "GET", f"{DATASETS}/{dataset_id}/documents", w.normal.token, {}), "creator's list")
    assert {d["id"] for d in listed["items"]} == {document["id"], again["id"]}
    assert succeeded(call(w.client, "DELETE", f"{DATASETS}/{dataset_id}/documents", w.normal.token, {}, body={"ids": [document["id"]]}))
    assert succeeded(call(w.client, "DELETE", DATASETS, w.normal.token, {}, body={"ids": [dataset_id], "tenant_id": w.a.tenant_id}))
    assert triple(call(w.client, "GET", f"{DATASETS}/{dataset_id}", w.normal.token, {})) == NOT_FOUND, "deleted"
    assert dataset_id not in _list_as(w, w.normal, w.a.tenant_id).text


@pytest.mark.e2e
def test_a_normal_member_uploads_and_removes_its_own_documents_in_a_team_dataset_and_no_one_elses(world: World) -> None:
    w = world
    team = str(w.a_team_dataset["id"])
    mine = _ok_data(upload_file(w, w.normal.token, team, query={"tenant_id": w.a.tenant_id}), "a normal member uploads into a team dataset")[0]
    others = str(w.a_team_documents[1]["id"])
    assert triple(call(w.client, "DELETE", f"{DATASETS}/{team}/documents", w.normal.token, {}, body={"ids": [others]})) == FORBIDDEN
    # all-or-nothing: one non-removable id gives 403 and nothing is deleted
    assert triple(call(w.client, "DELETE", f"{DATASETS}/{team}/documents", w.normal.token, {}, body={"ids": [mine["id"], others]})) == FORBIDDEN
    listed = {d["id"] for d in _ok_data(call(w.client, "GET", f"{DATASETS}/{team}/documents", w.a.token, {}, query={"page_size": "100"}), "list")["items"]}
    assert {mine["id"], others} <= listed
    # an absent id wins over a forbidden one
    assert triple(call(w.client, "DELETE", f"{DATASETS}/{team}/documents", w.normal.token, {}, body={"ids": [others, uuid.uuid4().hex]})) == NOT_FOUND
    assert succeeded(call(w.client, "DELETE", f"{DATASETS}/{team}/documents", w.normal.token, {}, body={"ids": [mine["id"]]}))
    # settings and delete of A's team dataset are for the creator, an owner or an admin
    assert triple(call(w.client, "PUT", f"{DATASETS}/{team}", w.normal.token, {}, body={"description": "member rewrite"})) == FORBIDDEN
    assert triple(call(w.client, "DELETE", DATASETS, w.normal.token, {}, body={"ids": [team], "tenant_id": w.a.tenant_id})) == FORBIDDEN
    assert triple(call(w.client, "DELETE", DATASETS, w.normal.token, {}, body={"ids": [team, str(w.a_private_dataset["id"])], "tenant_id": w.a.tenant_id})) == NOT_FOUND


# --- a member of another workspace --------------------------------------------------------------------------------------


@pytest.mark.e2e
def test_a_member_reaches_the_other_workspace_only_through_its_tenant_id_or_a_resource_id(world: World) -> None:
    w = world
    team = str(w.a_team_dataset["id"])
    own = call(w.client, "GET", DATASETS, w.normal.token, {}, query={"page_size": "100"})
    assert A_TEAM_DATASET not in own.text and str(w.a_private_dataset["id"]) not in own.text, "without a workspace selector the member acts in its own workspace"
    own_models = call(w.client, "GET", MODELS, w.normal.token, {})
    assert A_CHAT_MODEL not in own_models.text, "A's models are not the member's own"
    assert A_TEAM_DATASET in call(w.client, "GET", DATASETS, w.normal.token, {}, query={"tenant_id": w.a.tenant_id}).text
    assert A_CHAT_MODEL in call(w.client, "GET", MODELS, w.normal.token, {}, query={"tenant_id": w.a.tenant_id}).text
    assert succeeded(call(w.client, "GET", f"{DATASETS}/{team}", w.normal.token, {})), "a resource id reaches the dataset without the selector"
    assert succeeded(call(w.client, "GET", f"{DATASETS}/{team}/documents", w.normal.token, {}))
    # a member of A does not reach a workspace it does not belong to by naming it
    assert triple(call(w.client, "GET", DATASETS, w.normal.token, {}, query={"tenant_id": w.b.tenant_id})) == NOT_FOUND
    assert triple(call(w.client, "GET", MODELS, w.normal.token, {}, query={"tenant_id": w.b.tenant_id})) == NOT_FOUND


def _login(w: World, who: Account) -> str:
    resp = w.client.post("/api/v1/auth/login", json={"email": who.email, "password": TEST_PASSWORD})
    assert resp.status_code == 200, resp.text
    return str(resp.json()["data"]["token"])


@pytest.mark.e2e
def test_a_member_acting_from_another_session_lists_models_and_only_an_admin_changes_them(world: World) -> None:
    w = world
    w.client.cookies.clear()
    normal_session, admin_session = _login(w, w.normal), _login(w, w.admin)
    w.client.cookies.clear()
    scope = {"tenant_id": w.a.tenant_id}
    for token in (normal_session, admin_session):
        providers = call(w.client, "GET", PROVIDERS, token, {}, query=scope)
        assert succeeded(providers) and A_CHAT_MODEL in providers.text
        assert A_PROVIDER_KEY not in providers.text
        assert succeeded(call(w.client, "GET", MODELS, token, {}, query=scope))
    assert "last4" not in call(w.client, "GET", PROVIDERS, normal_session, {}, query=scope).text, "a normal member never sees last4"
    assert "last4" in call(w.client, "GET", PROVIDERS, admin_session, {}, query=scope).text, "an admin does"
    assert w.fake is not None
    w.fake.reset()
    assert triple(call(w.client, "PUT", PROVIDERS, normal_session, {}, body=_provider_save_body(w, w.a.tenant_id))) == FORBIDDEN
    assert triple(call(w.client, "PATCH", MODELS_DEFAULT, normal_session, {}, body=_body(w.a.tenant_id, embedding=a_embed_id()))) == FORBIDDEN
    assert w.fake.requests == []
    assert succeeded(call(w.client, "PATCH", MODELS_DEFAULT, admin_session, {}, body=_body(w.a.tenant_id, embedding=a_embed_id())))


# --- membership ends -------------------------------------------------------------------------------------------------------


@pytest.mark.e2e
def test_a_removed_member_loses_the_workspace_and_its_datasets_at_once(world: World) -> None:
    w = world
    assert w.registry is not None
    leaver = w.registry.register(prefix="mxl")
    users = "/api/v1/tenants/{tenant_id}/users"
    ids = {"tenant_id": w.a.tenant_id}
    assert succeeded(call(w.client, "POST", users, w.a.token, ids, body={"email": leaver.email}))
    assert succeeded(call(w.client, "PATCH", "/api/v1/tenants/{tenant_id}", leaver.token, ids, body={"action": "accept"}))
    scope = {"tenant_id": w.a.tenant_id}
    private = _ok_data(call(w.client, "POST", DATASETS, leaver.token, {}, body={"name": _unique("iso-leaver"), "tenant_id": w.a.tenant_id}), "the member creates a `me` dataset")
    shared = _ok_data(call(w.client, "POST", DATASETS, leaver.token, {}, body={"name": _unique("iso-leaver-team"), "permission": "team", "tenant_id": w.a.tenant_id}), "and a team dataset")
    kept = _ok_data(upload_file(w, leaver.token, str(shared["id"]), query=scope), "and uploads a document")[0]
    assert succeeded(call(w.client, "GET", f"{DATASETS}/{private['id']}", leaver.token, {}))
    tenants = call(w.client, "GET", "/v1/tenant/list", leaver.token, {}).json()["data"]
    assert w.a.tenant_id in {t["tenant_id"] for t in tenants}, "the member holds A while it is a member"

    removed = call(w.client, "DELETE", users, w.a.token, ids, body={"user_id": leaver.user_id})
    assert succeeded(removed), removed.text

    tenants = call(w.client, "GET", "/v1/tenant/list", leaver.token, {}).json()["data"]
    assert w.a.tenant_id not in {t["tenant_id"] for t in tenants}, "the workspace selector no longer holds A"
    gone = [
        call(w.client, "GET", DATASETS, leaver.token, {}, query=scope),
        call(w.client, "GET", PROVIDERS, leaver.token, {}, query=scope),
        call(w.client, "GET", MODELS, leaver.token, {}, query=scope),
        call(w.client, "GET", MODELS_DEFAULT, leaver.token, {}, query=scope),
        call(w.client, "POST", DATASETS, leaver.token, {}, body={"name": _unique("iso-after"), "tenant_id": w.a.tenant_id}),
        call(w.client, "GET", f"{DATASETS}/{private['id']}", leaver.token, {}),
        call(w.client, "GET", f"{DATASETS}/{shared['id']}", leaver.token, {}),
        call(w.client, "PUT", f"{DATASETS}/{shared['id']}", leaver.token, {}, body={"description": "after removal"}),
        call(w.client, "GET", f"{DATASETS}/{shared['id']}/documents", leaver.token, {}),
        call(w.client, "DELETE", f"{DATASETS}/{shared['id']}/documents", leaver.token, {}, body={"ids": [kept["id"]]}),
        call(w.client, "DELETE", DATASETS, leaver.token, {}, body={"ids": [shared["id"]], "tenant_id": w.a.tenant_id}),
        upload_file(w, leaver.token, str(shared["id"]), query=scope),
    ]
    assert [triple(r) for r in gone] == [NOT_FOUND] * len(gone), [triple(r) for r in gone]
    # the leaver's own workspace still works and holds nothing of A's
    own = call(w.client, "GET", DATASETS, leaver.token, {})
    assert succeeded(own) and A_TEAM_DATASET not in own.text
    # the team dataset the leaver made stays with the workspace; its document is still there for the owner
    assert succeeded(call(w.client, "GET", f"{DATASETS}/{shared['id']}", w.a.token, {}))
    assert {d["id"] for d in _ok_data(call(w.client, "GET", f"{DATASETS}/{shared['id']}/documents", w.a.token, {}), "owner's list")["items"]} == {kept["id"]}
    # the owner's own routes are unaffected
    assert succeeded(call(w.client, "GET", DATASETS, w.a.token, {}))
