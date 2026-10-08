"""Model list and default-model routes end to end through Nginx, on the real stack with the recording fake provider (plan 03-13).

LLM-28, LLM-29, TEN-12, TEN-13, D-07, D-17, D-18, D-20, D-26. Nothing of devRag is replaced: the app, Nginx, MySQL and Valkey are the
running stack; the fake provider is only the third party's end of the wire (it answers the connection test a save performs).

Provider-test budget (10 per 300 s per workspace): each test registers its own owner, so a save never competes with another test's.
"""
from __future__ import annotations

import httpx
import pytest

from test.helpers.accounts import AccountRegistry
from test.helpers.fake_provider import FakeProvider, fake_provider_stack  # noqa: F401  (fixture)
from test.testcases.test_provider_flow import (  # noqa: F401  (registry is a fixture)
    COMPAT,
    COMPAT_SLUG,
    KEY_ONE,
    KEY_TWO,
    NOT_FOUND,
    PROVIDERS,
    TOKENS,
    _bearer,
    api,
    join,
    keys_of,
    ok,
    registry,
    save_body,
)

pytestmark = pytest.mark.e2e

MODELS = "/api/v1/models"
DEFAULTS = "/api/v1/models/default"
UNAUTHORIZED = {"code": 401, "message": "unauthorized", "data": None}
CHAT_ID = f"fake-chat@{COMPAT}"
EMBED_ID = f"fake-embed@{COMPAT}"
FOREIGN_CHAT = {"name": "foreign-chat", "type": "chat"}
CREDENTIAL_WORDS = ("api_key", "last4", "base_url", "api_version", "apikey")


def reason_of(resp: httpx.Response) -> object:
    body = resp.json()
    return (body.get("data") or {}).get("reason")


def assert_unavailable(resp: httpx.Response) -> None:
    assert resp.status_code == 400, resp.text
    assert reason_of(resp) == "model_unavailable", resp.text


def assert_no_credentials(fake: FakeProvider, *responses: httpx.Response) -> None:
    for resp in responses:
        text = resp.text
        assert not any(word in text for word in CREDENTIAL_WORDS), text
        assert KEY_ONE not in text and KEY_TWO not in text and fake.stack_base_url not in text, "a credential or address reached a model response"
        assert keys_of(resp.json()).isdisjoint(CREDENTIAL_WORDS)


def test_the_owner_lists_models_and_chooses_defaults_explicitly(ingress: httpx.Client, registry: AccountRegistry, fake_provider_stack: FakeProvider) -> None:  # noqa: F811
    fake = fake_provider_stack
    owner = registry.register(prefix="mdowner")
    other = registry.register(prefix="mdother")
    ok(api(ingress, "PUT", PROVIDERS, owner.token, body=save_body(fake)))
    ok(api(ingress, "PUT", PROVIDERS, other.token, body=save_body(fake, KEY_TWO, [FOREIGN_CHAT])))
    seen: list[httpx.Response] = []

    def call(method: str, path: str, **kw: object) -> httpx.Response:
        resp = api(ingress, method, path, owner.token, **kw)  # type: ignore[arg-type]
        seen.append(resp)
        return resp

    listed = ok(call("GET", MODELS))
    assert {m["id"] for m in listed} == {CHAT_ID, EMBED_ID}
    by_name = {m["name"]: m for m in listed}
    assert by_name["fake-embed"]["dimension"] == fake.embedding_dim and by_name["fake-chat"]["dimension"] is None
    assert by_name["fake-chat"]["type"] == "chat" and by_name["fake-embed"]["type"] == "embedding"
    assert {"name", "provider", "type", "dimension", "max_tokens", "used_tokens", "instance"} <= set(by_name["fake-chat"])
    only_embedding = ok(call("GET", MODELS, params={"type": "embedding"}))
    assert [m["id"] for m in only_embedding] == [EMBED_ID]
    assert [m["id"] for m in ok(call("GET", MODELS, params={"type": "chat"}))] == [CHAT_ID]
    bad_type = call("GET", MODELS, params={"type": "image"})
    assert bad_type.status_code == 400 and reason_of(bad_type) == "models_invalid"

    assert ok(call("GET", DEFAULTS)) == {"chat": "", "embedding": ""}, "nothing is auto-picked after a save"

    assert ok(call("PATCH", DEFAULTS, body={"embedding": EMBED_ID})) == {"chat": "", "embedding": EMBED_ID}
    assert ok(call("GET", DEFAULTS)) == {"chat": "", "embedding": EMBED_ID}
    # An absent key never changes a value, a null clears it (T-03-13-05).
    assert ok(call("PATCH", DEFAULTS, body={"chat": CHAT_ID})) == {"chat": CHAT_ID, "embedding": EMBED_ID}
    assert ok(call("PATCH", DEFAULTS, body={"chat": None})) == {"chat": "", "embedding": EMBED_ID}
    assert ok(call("GET", DEFAULTS)) == {"chat": "", "embedding": EMBED_ID}

    # Refusals change nothing.
    too_long = "x" * (129 - len(f"@{COMPAT}")) + f"@{COMPAT}"
    assert len(too_long) == 129
    foreign = f"foreign-chat@{COMPAT}"
    for slot, value in [
        ("embedding", CHAT_ID),  # wrong type for the slot
        ("chat", EMBED_ID),
        ("chat", f"no-such-model@{COMPAT}"),
        ("chat", "fake-chat@no-such-provider"),
        ("chat", "not-a-composite-id"),
        ("chat", "a@b@c@d"),
        ("chat", ""),
        ("chat", too_long),
        ("embedding", too_long),
        ("chat", foreign),  # a model that exists, in another workspace
    ]:
        assert_unavailable(call("PATCH", DEFAULTS, body={slot: value}))
    mixed = call("PATCH", DEFAULTS, body={"chat": CHAT_ID, "embedding": CHAT_ID})
    assert_unavailable(mixed)
    assert ok(call("GET", DEFAULTS)) == {"chat": "", "embedding": EMBED_ID}, "a refused change, even half of a valid pair, writes nothing"

    empty = call("PATCH", DEFAULTS, body={})
    assert empty.status_code == 400 and reason_of(empty) == "models_invalid"
    assert call("PATCH", DEFAULTS, body={"chat": CHAT_ID, "unknown_field": 1}).status_code == 400
    assert call("PATCH", DEFAULTS, body={"chat": 5}).status_code == 400
    assert call("PATCH", DEFAULTS, body={"chat": CHAT_ID, "tenant_id": "not-an-id"}).status_code == 400
    assert ok(call("GET", DEFAULTS)) == {"chat": "", "embedding": EMBED_ID}

    assert_no_credentials(fake, *seen)
    assert all("foreign-chat" not in r.text for r in seen if r.status_code == 200), "the other workspace's model never shows"


def test_members_read_only_owners_and_admins_write_and_a_token_can_only_read(ingress: httpx.Client, registry: AccountRegistry, fake_provider_stack: FakeProvider) -> None:  # noqa: F811
    fake = fake_provider_stack
    owner, admin, normal = registry.register(prefix="mdown"), registry.register(prefix="mdadm"), registry.register(prefix="mdnrm")
    join(ingress, owner, admin, "admin")
    join(ingress, owner, normal)
    ok(api(ingress, "PUT", PROVIDERS, owner.token, body=save_body(fake)))
    scope = {"tenant_id": owner.tenant_id}
    ok(api(ingress, "PATCH", DEFAULTS, owner.token, body={"embedding": EMBED_ID}))

    # The admin acts in the owner's workspace through tenant_id: reads and writes.
    seen = [api(ingress, "GET", MODELS, admin.token, params=scope), api(ingress, "GET", DEFAULTS, admin.token, params=scope)]
    assert {m["id"] for m in ok(seen[0])} == {CHAT_ID, EMBED_ID}
    assert ok(seen[1]) == {"chat": "", "embedding": EMBED_ID}
    patched = api(ingress, "PATCH", DEFAULTS, admin.token, body={"chat": CHAT_ID, "tenant_id": owner.tenant_id})
    seen.append(patched)
    assert ok(patched) == {"chat": CHAT_ID, "embedding": EMBED_ID}

    # A normal member reads, never writes.
    member_models = api(ingress, "GET", MODELS, normal.token, params=scope)
    member_defaults = api(ingress, "GET", DEFAULTS, normal.token, params=scope)
    seen += [member_models, member_defaults]
    assert {m["id"] for m in ok(member_models)} == {CHAT_ID, EMBED_ID}
    assert ok(member_defaults) == {"chat": CHAT_ID, "embedding": EMBED_ID}
    denied = api(ingress, "PATCH", DEFAULTS, normal.token, body={"chat": None, "tenant_id": owner.tenant_id})
    assert denied.status_code == 403 and denied.json()["code"] == 403, denied.text
    assert ok(api(ingress, "GET", DEFAULTS, owner.token)) == {"chat": CHAT_ID, "embedding": EMBED_ID}, "the forbidden write changed nothing"

    # An API token reads (the list is `auth: api`) but the default write is session-only.
    created = ingress.post(TOKENS, headers=_bearer(owner.token))
    assert created.status_code == 200, created.text
    token = created.json()["data"]["token"]
    token_models, token_defaults = api(ingress, "GET", MODELS, token), api(ingress, "GET", DEFAULTS, token)
    seen += [token_models, token_defaults]
    assert {m["id"] for m in ok(token_models)} == {CHAT_ID, EMBED_ID} and ok(token_defaults)["embedding"] == EMBED_ID
    refused = api(ingress, "PATCH", DEFAULTS, token, body={"chat": None})
    assert refused.status_code == 401 and refused.json() == UNAUTHORIZED
    assert ok(api(ingress, "GET", DEFAULTS, owner.token)) == {"chat": CHAT_ID, "embedding": EMBED_ID}

    assert_no_credentials(fake, *seen)


def test_a_stranger_acting_in_another_workspace_gets_the_one_not_found_answer(ingress: httpx.Client, registry: AccountRegistry, fake_provider_stack: FakeProvider) -> None:  # noqa: F811
    fake = fake_provider_stack
    owner, stranger = registry.register(prefix="mdoa"), registry.register(prefix="mdob")
    ok(api(ingress, "PUT", PROVIDERS, owner.token, body=save_body(fake)))
    ok(api(ingress, "PATCH", DEFAULTS, owner.token, body={"embedding": EMBED_ID}))
    scope = {"tenant_id": owner.tenant_id}

    for path in (MODELS, DEFAULTS):
        assert api(ingress, "GET", path, stranger.token, params=scope).json() == NOT_FOUND, path
        assert api(ingress, "GET", path, stranger.token, params={"tenant_id": "0" * 32}).json() == NOT_FOUND, path
        assert api(ingress, "GET", path, stranger.token, params={"tenant_id": "not-an-id"}).json() == NOT_FOUND, path
    assert api(ingress, "PATCH", DEFAULTS, stranger.token, body={"chat": None, "tenant_id": owner.tenant_id}).json() == NOT_FOUND
    assert api(ingress, "PATCH", DEFAULTS, stranger.token, body={"chat": CHAT_ID, "tenant_id": "0" * 32}).json() == NOT_FOUND

    # The stranger's own workspace holds nothing, and A's id is unavailable there.
    assert ok(api(ingress, "GET", MODELS, stranger.token)) == []
    assert ok(api(ingress, "GET", DEFAULTS, stranger.token)) == {"chat": "", "embedding": ""}
    assert_unavailable(api(ingress, "PATCH", DEFAULTS, stranger.token, body={"embedding": EMBED_ID}))
    assert ok(api(ingress, "GET", DEFAULTS, owner.token)) == {"chat": "", "embedding": EMBED_ID}


def test_deleting_the_provider_clears_the_default_that_pointed_at_it(ingress: httpx.Client, registry: AccountRegistry, fake_provider_stack: FakeProvider) -> None:  # noqa: F811
    fake = fake_provider_stack
    owner = registry.register(prefix="mddel")
    ok(api(ingress, "PUT", PROVIDERS, owner.token, body=save_body(fake)))
    assert ok(api(ingress, "PATCH", DEFAULTS, owner.token, body={"chat": CHAT_ID, "embedding": EMBED_ID})) == {"chat": CHAT_ID, "embedding": EMBED_ID}
    deleted = api(ingress, "DELETE", f"{PROVIDERS}/{COMPAT_SLUG}", owner.token)
    assert deleted.status_code == 200
    assert ok(api(ingress, "GET", DEFAULTS, owner.token)) == {"chat": "", "embedding": ""}
    assert ok(api(ingress, "GET", MODELS, owner.token)) == []
    assert_unavailable(api(ingress, "PATCH", DEFAULTS, owner.token, body={"chat": CHAT_ID}))
