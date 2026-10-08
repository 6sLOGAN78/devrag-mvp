"""Provider credential routes end to end through Nginx, against the real stack and the recording fake provider (plan 03-12).

LLM-23..27, SEC-02, SEC-03, D-07, D-16, D-17, D-19, D-20, D-26. The fake provider is the third party's end of the wire: it binds
every interface on an ephemeral port for the lifetime of a test and the dockerised app reaches it as ``host.docker.internal``.
Nothing of devRag is replaced: the app, Nginx, MySQL and Valkey are the running stack.

Provider-test budget (10 per 300 s per workspace): every test below that saves registers its own accounts, so the limiter is never the
reason a case fails; the rate-limit case has a dedicated account and spends it on purpose.
"""
from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import httpx
import pytest

from test.helpers.accounts import Account, AccountRegistry
from test.helpers.db import root_connection
from test.helpers.fake_provider import FakeProvider, fake_provider_stack  # noqa: F401  (fixture)
from test.testcases.conftest import BASE_URL

pytestmark = pytest.mark.e2e

PROVIDERS = "/api/v1/providers"
TOKENS = "/api/v1/system/tokens"
COMPAT = "OpenAI-API-Compatible"
COMPAT_SLUG = "openai-compatible"
NOT_FOUND = {"code": 404, "message": "not found", "data": None}
UNAUTHORIZED = {"code": 401, "message": "unauthorized", "data": None}
KEY_ONE = "-".join(("flow", "provider", "key", "one", "0001"))
KEY_TWO = "-".join(("flow", "provider", "key", "two", "0002"))
CHAT = {"name": "fake-chat", "type": "chat"}
EMBED = {"name": "fake-embed", "type": "embedding"}
CREDENTIAL_KEYS = ("last4", "base_url", "api_version")


@pytest.fixture
def registry(ingress: httpx.Client) -> Iterator[AccountRegistry]:
    accounts = AccountRegistry(BASE_URL)
    try:
        yield accounts
    finally:
        accounts.cleanup()


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def api(ingress: httpx.Client, method: str, path: str, token: str, *, body: Any = None, params: dict[str, str] | None = None) -> httpx.Response:
    """One call through Nginx. Provider tests can take seconds, so the 5 s client default is raised; the answer must come from Python."""
    ingress.cookies.clear()
    resp = ingress.request(method, path, headers=_bearer(token), json=body, params=params, timeout=60.0)
    assert resp.headers.get("x-api-source") == "python", (method, path, resp.status_code)
    return resp


def ok(resp: httpx.Response) -> Any:
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["code"] == 0, body
    return body["data"]


def keys_of(node: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(node, dict):
        for key, value in node.items():
            found.add(str(key))
            found |= keys_of(value)
    elif isinstance(node, list):
        for item in node:
            found |= keys_of(item)
    return found


def join(ingress: httpx.Client, owner: Account, member: Account, role: str | None = None) -> None:
    """Invite, accept and (for admin) promote through the real team API."""
    ingress.cookies.clear()
    users = f"/api/v1/tenants/{owner.tenant_id}/users"
    assert ingress.post(users, headers=_bearer(owner.token), json={"email": member.email}).status_code == 200
    accepted = ingress.patch(f"/api/v1/tenants/{owner.tenant_id}", headers=_bearer(member.token), json={"action": "accept"})
    assert accepted.status_code == 200, accepted.text
    if role:
        promoted = ingress.patch(f"{users}/{member.user_id}", headers=_bearer(owner.token), json={"role": role})
        assert promoted.status_code == 200, promoted.text


def sql(query: str, params: tuple[Any, ...]) -> list[tuple[Any, ...]]:
    conn = root_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("USE `rag_flow`")
            cur.execute(query, params)
            return list(cur.fetchall())
    finally:
        conn.close()


def envelopes(tenant_id: str, factory: str = COMPAT) -> dict[str, str]:
    rows = sql("SELECT `llm_name`, `api_key` FROM `tenant_llm` WHERE `tenant_id` = %s AND `llm_factory` = %s", (tenant_id, factory))
    return {str(name): str(key) for name, key in rows}


def provider_rows(tenant_id: str) -> int:
    return int(sql("SELECT COUNT(*) FROM `tenant_model_provider` WHERE `tenant_id` = %s", (tenant_id,))[0][0])


def model_rows(tenant_id: str) -> int:
    query = "SELECT COUNT(*) FROM `tenant_model` m JOIN `tenant_model_provider` p ON m.`provider_id` = p.`id` WHERE p.`tenant_id` = %s"
    return int(sql(query, (tenant_id,))[0][0])


def save_body(fake: FakeProvider, key: str | None = KEY_ONE, models: list[dict[str, str]] | None = None, **extra: Any) -> dict[str, Any]:
    body: dict[str, Any] = {"provider": COMPAT, "base_url": fake.stack_base_url, "models": models or [CHAT, EMBED], **extra}
    if key is not None:
        body["api_key"] = key
    return body


def chat_hits(fake: FakeProvider) -> list[Any]:
    return [r for r in fake.requests if r.path == "/v1/chat/completions"]


# --- roles, masking and the happy path -------------------------------------------------------------------------------


def test_owner_saves_and_reads_back_a_masked_provider_and_the_key_is_sealed_at_rest(ingress: httpx.Client, registry: AccountRegistry, fake_provider_stack: FakeProvider) -> None:  # noqa: F811
    fake = fake_provider_stack
    owner = registry.register(prefix="pfowner")
    saved = ok(api(ingress, "PUT", PROVIDERS, owner.token, body=save_body(fake)))
    assert saved["name"] == COMPAT and saved["configured"] is True
    (instance,) = saved["instances"]
    assert instance["last4"] == KEY_ONE[-4:] and instance["base_url"] == fake.stack_base_url and instance["configured"] is True
    assert {m["name"]: m["type"] for m in saved["models"]} == {"fake-chat": "chat", "fake-embed": "embedding"}
    dimensions = {m["name"]: m["dimension"] for m in saved["models"]}
    assert dimensions["fake-embed"] == fake.embedding_dim and dimensions["fake-chat"] is None

    listed = api(ingress, "GET", PROVIDERS, owner.token)
    assert KEY_ONE not in listed.text
    mine = next(p for p in ok(listed) if p["name"] == COMPAT)
    assert mine["instances"][0]["last4"] == KEY_ONE[-4:] and mine["configured"] is True
    assert [p["name"] for p in ok(listed)][:2] == ["OpenAI", "Azure-OpenAI"], "every supported provider is listed, configured or not"

    stored = envelopes(owner.tenant_id)
    assert set(stored) == {"fake-chat", "fake-embed"}
    for envelope in stored.values():
        assert envelope.startswith("v1:") and KEY_ONE not in envelope
    assert {r.path for r in fake.requests} >= {"/v1/chat/completions", "/v1/embeddings"}, "both models were tested for real before saving"
    assert sorted(m["name"] for m in ok(api(ingress, "GET", f"{PROVIDERS}/{COMPAT_SLUG}/models", owner.token))) == ["fake-chat", "fake-embed"]


def test_a_normal_member_sees_no_address_and_no_last4_and_cannot_write(ingress: httpx.Client, registry: AccountRegistry, fake_provider_stack: FakeProvider) -> None:  # noqa: F811
    fake = fake_provider_stack
    owner, normal = registry.register(prefix="pfown"), registry.register(prefix="pfnrm")
    join(ingress, owner, normal)
    ok(api(ingress, "PUT", PROVIDERS, owner.token, body=save_body(fake)))
    scope = {"tenant_id": owner.tenant_id}

    as_owner = api(ingress, "GET", PROVIDERS, owner.token)
    as_member = api(ingress, "GET", PROVIDERS, normal.token, params=scope)
    assert all(k in keys_of(ok(as_owner)) for k in CREDENTIAL_KEYS), "the owner's list holds the address and last4"
    member_view = ok(as_member)
    assert member_view and next(p for p in member_view if p["name"] == COMPAT)["configured"] is True
    assert keys_of(member_view).isdisjoint(CREDENTIAL_KEYS)
    assert fake.stack_base_url not in as_member.text and KEY_ONE[-4:] not in as_member.text
    models = ok(api(ingress, "GET", f"{PROVIDERS}/{COMPAT_SLUG}/models", normal.token, params=scope))
    assert sorted(m["name"] for m in models) == ["fake-chat", "fake-embed"] and keys_of(models).isdisjoint(CREDENTIAL_KEYS)

    before = envelopes(owner.tenant_id)
    for method, path, body in [
        ("PUT", PROVIDERS, save_body(fake, KEY_TWO, [CHAT], tenant_id=owner.tenant_id)),
        ("DELETE", f"{PROVIDERS}/{COMPAT_SLUG}", None),
        ("POST", f"{PROVIDERS}/{COMPAT_SLUG}/instances", {"models": [{"name": "fake-chat-2", "type": "chat"}], "tenant_id": owner.tenant_id}),
        ("GET", f"{PROVIDERS}/{COMPAT_SLUG}/instances/default", None),
    ]:
        resp = api(ingress, method, path, normal.token, body=body, params=scope if body is None else None)
        assert resp.status_code == 403 and resp.json()["code"] == 403, (method, path, resp.text)
    assert envelopes(owner.tenant_id) == before, "a forbidden write changed nothing"
    assert next(p for p in ok(api(ingress, "GET", PROVIDERS, owner.token)) if p["name"] == COMPAT)["configured"] is True


def test_an_api_token_can_list_without_credentials_but_never_reaches_the_key_routes(ingress: httpx.Client, registry: AccountRegistry, fake_provider_stack: FakeProvider) -> None:  # noqa: F811
    fake = fake_provider_stack
    owner = registry.register(prefix="pftok")
    ok(api(ingress, "PUT", PROVIDERS, owner.token, body=save_body(fake)))
    created = ingress.post(TOKENS, headers=_bearer(owner.token))
    assert created.status_code == 200, created.text
    token = created.json()["data"]["token"]

    as_token = api(ingress, "GET", PROVIDERS, token)
    assert as_token.status_code == 200
    view = ok(as_token)
    assert next(p for p in view if p["name"] == COMPAT)["configured"] is True
    assert keys_of(view).isdisjoint(CREDENTIAL_KEYS), "a token inherits the owner's role, but its subject is api_token"
    assert fake.stack_base_url not in as_token.text and KEY_ONE[-4:] not in as_token.text
    assert all(k in keys_of(ok(api(ingress, "GET", PROVIDERS, owner.token))) for k in CREDENTIAL_KEYS), "the same GET as the owner holds them"
    assert ok(api(ingress, "GET", f"{PROVIDERS}/{COMPAT_SLUG}/models", token))

    before = envelopes(owner.tenant_id)
    for method, path, body in [
        ("PUT", PROVIDERS, save_body(fake, KEY_TWO, [CHAT])),
        ("DELETE", f"{PROVIDERS}/{COMPAT_SLUG}", None),
        ("POST", f"{PROVIDERS}/{COMPAT_SLUG}/instances", {"models": [{"name": "fake-chat-2", "type": "chat"}]}),
        ("GET", f"{PROVIDERS}/{COMPAT_SLUG}/instances/default", None),
    ]:
        resp = api(ingress, method, path, token, body=body)
        assert resp.status_code == 401 and resp.json() == UNAUTHORIZED, (method, path)
    assert envelopes(owner.tenant_id) == before


def test_a_stranger_acting_in_another_workspace_gets_the_one_not_found_answer(ingress: httpx.Client, registry: AccountRegistry, fake_provider_stack: FakeProvider) -> None:  # noqa: F811
    fake = fake_provider_stack
    owner, stranger = registry.register(prefix="pfa"), registry.register(prefix="pfb")
    ok(api(ingress, "PUT", PROVIDERS, owner.token, body=save_body(fake)))
    fake.reset()
    foreign = api(ingress, "PUT", PROVIDERS, stranger.token, body=save_body(fake, KEY_TWO, [CHAT], tenant_id=owner.tenant_id))
    assert foreign.status_code == 404 and foreign.json() == NOT_FOUND
    unknown_workspace = api(ingress, "PUT", PROVIDERS, stranger.token, body=save_body(fake, KEY_TWO, [CHAT], tenant_id="0" * 32))
    assert unknown_workspace.status_code == 404 and unknown_workspace.json() == NOT_FOUND
    assert api(ingress, "GET", PROVIDERS, stranger.token, params={"tenant_id": owner.tenant_id}).json() == NOT_FOUND
    assert api(ingress, "GET", PROVIDERS, stranger.token, params={"tenant_id": "not-an-id"}).json() == NOT_FOUND
    assert api(ingress, "DELETE", f"{PROVIDERS}/{COMPAT_SLUG}", stranger.token, params={"tenant_id": owner.tenant_id}).json() == NOT_FOUND
    assert fake.requests == [], "the foreign write never reached the provider"
    assert provider_rows(stranger.tenant_id) == 0
    assert next(p for p in ok(api(ingress, "GET", PROVIDERS, owner.token)) if p["name"] == COMPAT)["configured"] is True


def test_instance_detail_and_delete(ingress: httpx.Client, registry: AccountRegistry, fake_provider_stack: FakeProvider) -> None:  # noqa: F811
    fake = fake_provider_stack
    owner = registry.register(prefix="pfdel")
    ok(api(ingress, "PUT", PROVIDERS, owner.token, body=save_body(fake)))
    detail = ok(api(ingress, "GET", f"{PROVIDERS}/{COMPAT_SLUG}/instances/default", owner.token))
    assert detail["name"] == "default" and detail["last4"] == KEY_ONE[-4:] and len(detail["models"]) == 2
    assert KEY_ONE not in str(detail)
    for missing in (f"{PROVIDERS}/{COMPAT_SLUG}/instances/nope", f"{PROVIDERS}/openai/instances/default", f"{PROVIDERS}/no-such-provider/instances/default"):
        assert api(ingress, "GET", missing, owner.token).json() == NOT_FOUND, missing

    deleted = api(ingress, "DELETE", f"{PROVIDERS}/{COMPAT_SLUG}", owner.token)
    assert deleted.status_code == 200 and deleted.json()["code"] == 0
    assert envelopes(owner.tenant_id) == {} and provider_rows(owner.tenant_id) == 0 and model_rows(owner.tenant_id) == 0
    assert api(ingress, "DELETE", f"{PROVIDERS}/{COMPAT_SLUG}", owner.token).json() == NOT_FOUND
    assert api(ingress, "GET", f"{PROVIDERS}/{COMPAT_SLUG}/instances/default", owner.token).json() == NOT_FOUND
    assert api(ingress, "GET", f"{PROVIDERS}/{COMPAT_SLUG}/models", owner.token).json() == NOT_FOUND
    assert api(ingress, "DELETE", f"{PROVIDERS}/openai", owner.token).json() == NOT_FOUND, "an unconfigured provider"
    assert api(ingress, "DELETE", f"{PROVIDERS}/no-such-provider", owner.token).json() == NOT_FOUND, "an unknown provider"


# --- changing a key and an address ----------------------------------------------------------------------------------


def test_key_rotation_by_an_admin_reseals_every_model_and_add_model_uses_the_new_key(ingress: httpx.Client, registry: AccountRegistry, fake_provider_stack: FakeProvider) -> None:  # noqa: F811
    fake = fake_provider_stack
    owner, admin = registry.register(prefix="pfrot"), registry.register(prefix="pfadm")
    join(ingress, owner, admin, "admin")
    ok(api(ingress, "PUT", PROVIDERS, owner.token, body=save_body(fake, KEY_ONE)))
    first = envelopes(owner.tenant_id)
    assert model_rows(owner.tenant_id) == 2

    fake.reset()
    rotated = ok(api(ingress, "PUT", PROVIDERS, admin.token, body=save_body(fake, KEY_TWO, [CHAT], tenant_id=owner.tenant_id)))
    assert rotated["instances"][0]["last4"] == KEY_TWO[-4:] and len(rotated["models"]) == 2, "no model was lost or duplicated"
    assert model_rows(owner.tenant_id) == 2 and set(envelopes(owner.tenant_id)) == {"fake-chat", "fake-embed"}
    (call,) = chat_hits(fake)
    assert call.headers["authorization"] == f"Bearer {KEY_TWO}" and len(fake.requests) == 1, "exactly one test call, with the new key"
    second = envelopes(owner.tenant_id)
    for name in ("fake-chat", "fake-embed"):
        assert second[name] != first[name] and second[name].startswith("v1:")
        assert KEY_ONE not in second[name] and KEY_TWO not in second[name]

    again = api(ingress, "PUT", PROVIDERS, admin.token, body=save_body(fake, KEY_TWO, [CHAT], tenant_id=owner.tenant_id))
    assert again.status_code == 200, "re-saving an unchanged provider is never model_exists"

    fake.reset()
    extra = {"name": "fake-chat-2", "type": "chat"}
    added = ok(api(ingress, "POST", f"{PROVIDERS}/{COMPAT_SLUG}/instances", owner.token, body={"models": [extra]}))
    assert sorted(m["name"] for m in added["models"]) == ["fake-chat", "fake-chat-2", "fake-embed"]
    (added_call,) = chat_hits(fake)
    assert added_call.headers["authorization"] == f"Bearer {KEY_TWO}", "the new model was tested with the rotated key"
    assert model_rows(owner.tenant_id) == 3

    duplicate = api(ingress, "POST", f"{PROVIDERS}/{COMPAT_SLUG}/instances", owner.token, body={"models": [extra]})
    assert duplicate.status_code == 409 and duplicate.json()["data"]["reason"] == "model_exists"
    assert api(ingress, "POST", f"{PROVIDERS}/openai/instances", owner.token, body={"models": [CHAT]}).json() == NOT_FOUND, "unconfigured provider"
    assert api(ingress, "POST", f"{PROVIDERS}/no-such-provider/instances", owner.token, body={"models": [CHAT]}).json() == NOT_FOUND
    assert model_rows(owner.tenant_id) == 3


def test_a_keyless_ollama_address_can_be_changed_and_the_new_address_is_the_one_tested(ingress: httpx.Client, registry: AccountRegistry, fake_provider_stack: FakeProvider) -> None:  # noqa: F811
    fake = fake_provider_stack
    owner = registry.register(prefix="pfoll")
    body = {"provider": "Ollama", "base_url": fake.stack_ollama_url, "models": [CHAT]}
    first = ok(api(ingress, "PUT", PROVIDERS, owner.token, body=body))
    assert first["instances"][0]["base_url"] == fake.stack_ollama_url
    assert fake.requests_on(fake.port) and not fake.requests_on(fake.secondary.port)  # type: ignore[union-attr]

    fake.reset()
    moved = api(ingress, "PUT", PROVIDERS, owner.token, body={**body, "base_url": fake.stack_ollama_url_b})
    assert moved.status_code == 200, moved.text
    assert fake.requests_on(fake.secondary.port) and not fake.requests_on(fake.port), "only the secondary listener saw the test"  # type: ignore[union-attr]
    listed = next(p for p in ok(api(ingress, "GET", PROVIDERS, owner.token)) if p["name"] == "Ollama")
    assert listed["instances"][0]["base_url"] == fake.stack_ollama_url_b
    assert model_rows(owner.tenant_id) == 1


# --- refusals --------------------------------------------------------------------------------------------------------


def test_a_refused_provider_is_400_and_the_session_stays_valid(ingress: httpx.Client, registry: AccountRegistry, fake_provider_stack: FakeProvider) -> None:  # noqa: F811
    fake = fake_provider_stack
    owner = registry.register(prefix="pfref")
    refused = api(ingress, "PUT", PROVIDERS, owner.token, body=save_body(fake, KEY_ONE, [{"name": "fake-401", "type": "chat"}]))
    body = refused.json()
    assert refused.status_code == 400 and body["code"] != 401 and body["data"]["reason"] == "provider_refused", refused.text
    assert KEY_ONE not in refused.text and fake.stack_base_url not in refused.text
    session = ingress.get("/v1/user/info", headers=_bearer(owner.token))
    assert session.status_code == 200 and session.json()["code"] == 0, "a provider refusal never ends the user's session"
    assert provider_rows(owner.tenant_id) == 0 and envelopes(owner.tenant_id) == {}
    assert next(p for p in ok(api(ingress, "GET", PROVIDERS, owner.token)) if p["name"] == COMPAT)["configured"] is False


def test_addresses_models_and_fields_that_must_be_refused(ingress: httpx.Client, registry: AccountRegistry, fake_provider_stack: FakeProvider) -> None:  # noqa: F811
    fake = fake_provider_stack
    owner = registry.register(prefix="pfbad")
    for address in ("http://169.254.169.254/v1", "http://es01:9200"):
        resp = api(ingress, "PUT", PROVIDERS, owner.token, body={**save_body(fake), "base_url": address})
        assert resp.status_code == 400 and resp.json()["data"]["reason"] == "base_url_refused", address
        assert address not in resp.text
    bad_ollama = api(ingress, "PUT", PROVIDERS, owner.token, body={"provider": "Ollama", "base_url": fake.stack_ollama_url + "/v1", "models": [CHAT]})
    assert bad_ollama.status_code == 400 and bad_ollama.json()["data"]["reason"] == "base_url_invalid"
    unknown = api(ingress, "PUT", PROVIDERS, owner.token, body={**save_body(fake), "provider": "No-Such-Provider"})
    assert unknown.status_code == 400 and unknown.json()["data"]["reason"] == "provider_unknown"
    for extra in ({"tenant_llm_id": "x"}, {"created_by": owner.user_id}, {"used_tokens": 5}):
        mass = api(ingress, "PUT", PROVIDERS, owner.token, body={**save_body(fake), **extra})
        assert mass.status_code == 400 and mass.json()["code"] == 101, extra
        assert KEY_ONE not in mass.text
    for models in ([], [CHAT, CHAT, EMBED], [{"name": "has space", "type": "chat"}], [{"name": "x", "type": "rerank"}]):
        resp = api(ingress, "PUT", PROVIDERS, owner.token, body=save_body(fake, models=models))
        assert resp.status_code == 400, models
    assert provider_rows(owner.tenant_id) == 0, "nothing refused was stored"
    assert fake.requests == [], "none of the refusals reached the provider"


def test_changing_the_address_of_a_keyed_provider_needs_the_key_again(ingress: httpx.Client, registry: AccountRegistry, fake_provider_stack: FakeProvider) -> None:  # noqa: F811
    fake = fake_provider_stack
    owner = registry.register(prefix="pfaddr")
    ok(api(ingress, "PUT", PROVIDERS, owner.token, body=save_body(fake, KEY_ONE, [CHAT])))
    fake.reset()
    moved = api(ingress, "PUT", PROVIDERS, owner.token, body={**save_body(fake, key=None, models=[CHAT]), "base_url": fake.secondary.stack_base_url})  # type: ignore[union-attr]
    assert moved.status_code == 400 and moved.json()["data"]["reason"] == "key_required_for_new_address"
    assert fake.requests == []
    kept = next(p for p in ok(api(ingress, "GET", PROVIDERS, owner.token)) if p["name"] == COMPAT)
    assert kept["instances"][0]["base_url"] == fake.stack_base_url
    with_key = api(ingress, "PUT", PROVIDERS, owner.token, body={**save_body(fake, KEY_TWO, [CHAT]), "base_url": fake.secondary.stack_base_url})  # type: ignore[union-attr]
    assert with_key.status_code == 200, with_key.text
    assert next(p for p in ok(api(ingress, "GET", PROVIDERS, owner.token)) if p["name"] == COMPAT)["instances"][0]["base_url"] == fake.secondary.stack_base_url  # type: ignore[union-attr]


def test_the_eleventh_provider_test_in_a_window_is_429_with_retry_after(ingress: httpx.Client, registry: AccountRegistry, fake_provider_stack: FakeProvider) -> None:  # noqa: F811
    fake = fake_provider_stack
    owner = registry.register(prefix="pflim")
    body = {"provider": "Ollama", "base_url": fake.stack_ollama_url, "models": [CHAT]}
    for attempt in range(10):
        resp = api(ingress, "PUT", PROVIDERS, owner.token, body=body)
        assert resp.status_code == 200, (attempt, resp.text)
    limited = api(ingress, "PUT", PROVIDERS, owner.token, body=body)
    assert limited.status_code == 429 and limited.json()["data"]["reason"] == "provider_test_rate_limited", limited.text
    assert limited.json()["code"] != 401
    retry = int(limited.headers["Retry-After"])
    assert 1 <= retry <= 300
    assert api(ingress, "GET", PROVIDERS, owner.token).status_code == 200, "reading is not limited"
