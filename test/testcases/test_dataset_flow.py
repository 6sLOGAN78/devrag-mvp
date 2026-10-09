"""Dataset create, list and detail routes end to end through Nginx, on the real stack (plan 03-14).

KB-01..05, KB-08, KB-09, TEN-13, TEN-16, SEC-02, D-08, D-18, D-19, D-20, D-26, D-27. Nothing of devRag is replaced: the app, Nginx, MySQL,
Elasticsearch and Valkey are the running stack; the recording fake provider is only the third party's end of the wire (it answers the
connection test a provider save performs). Each test registers its own accounts, so the provider-test budget (10 per 300 s per workspace)
and the dataset names never collide between tests.
"""
from __future__ import annotations

import uuid
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest

from test.helpers.accounts import Account, AccountRegistry, unique_name
from test.helpers.fake_provider import FakeProvider, fake_provider_stack  # noqa: F401  (fixture)
from test.testcases.conftest import BASE_URL
from test.testcases.test_provider_flow import (  # noqa: F401  (registry is a fixture)
    COMPAT,
    KEY_ONE,
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

DATASETS = "/api/v1/datasets"
DEFAULTS = "/api/v1/models/default"
CHAT_ID = f"fake-chat@{COMPAT}"
EMBED_ID = f"fake-embed@{COMPAT}"
BANNED_KEYS = {"status", "source", "location", "api_key", "last4", "base_url", "api_version", "token", "secret", "password"}
DTO_KEYS = {
    "id", "name", "description", "avatar", "language", "permission", "embd_id", "embedding_dimension", "parser_id", "parser_config",
    "doc_num", "chunk_num", "token_num", "tenant_id", "created_by", "create_time", "update_time",
}  # fmt: skip


def reason_of(resp: httpx.Response) -> object:
    return (resp.json().get("data") or {}).get("reason")


def workspace(ingress: httpx.Client, accounts: AccountRegistry, fake: FakeProvider, prefix: str, *, default: bool = True) -> Account:
    """A fresh owner whose workspace has the fake chat and embedding model and, unless told otherwise, the embedding default."""
    owner = accounts.register(prefix=prefix)
    ok(api(ingress, "PUT", PROVIDERS, owner.token, body=save_body(fake)))
    if default:
        ok(api(ingress, "PATCH", DEFAULTS, owner.token, body={"embedding": EMBED_ID}))
    return owner


def create(ingress: httpx.Client, who: Account, name: str | None = None, **body: object) -> httpx.Response:
    return api(ingress, "POST", DATASETS, who.token, body={"name": name or unique_name("flow"), **body})


def assert_clean(*responses: httpx.Response) -> None:
    for resp in responses:
        found = keys_of(resp.json())
        assert found.isdisjoint(BANNED_KEYS), (found & BANNED_KEYS, resp.text)
        assert KEY_ONE not in resp.text


def test_an_owner_creates_lists_and_opens_a_dataset(ingress: httpx.Client, registry: AccountRegistry, fake_provider_stack: FakeProvider) -> None:  # noqa: F811
    fake = fake_provider_stack
    owner = workspace(ingress, registry, fake, "dsown")
    made = create(ingress, owner, "  Handbook  ", description="what we know")
    data = ok(made)
    assert set(data) == DTO_KEYS
    assert data["name"] == "Handbook", "the name is trimmed"
    assert data["permission"] == "me" and data["parser_id"] == "naive" and data["language"] == "English"
    assert data["embd_id"] == EMBED_ID and data["embedding_dimension"] == fake.embedding_dim, "the workspace default was used and its dimension recorded"
    assert data["doc_num"] == 0 and data["chunk_num"] == 0 and data["token_num"] == 0
    assert data["tenant_id"] == owner.tenant_id and data["created_by"] == owner.user_id
    assert data["parser_config"]["chunk_token_num"] == 512 and "pages" in data["parser_config"] and data["description"] == "what we know"

    listed = api(ingress, "GET", DATASETS, owner.token)
    page = ok(listed)
    assert page["total"] == 1 and [d["id"] for d in page["items"]] == [data["id"]]
    assert set(page["items"][0]) == DTO_KEYS

    detail_resp = api(ingress, "GET", f"{DATASETS}/{data['id']}", owner.token)
    detail = ok(detail_resp)
    assert detail["id"] == data["id"] and detail["embedding_dimension"] == fake.embedding_dim
    assert set(detail["upload_limits"]) == {"max_file_bytes", "max_files_per_request", "max_documents", "allowed_extensions"}
    assert detail["upload_limits"]["max_file_bytes"] > 0 and ".pdf" in detail["upload_limits"]["allowed_extensions"]
    assert detail["parser_config"]["chunk_token_num"] == 512
    assert_clean(made, listed, detail_resp)


def test_the_team_permission_is_chosen_at_creation_and_everything_else_is_refused(ingress: httpx.Client, registry: AccountRegistry, fake_provider_stack: FakeProvider) -> None:  # noqa: F811
    owner = workspace(ingress, registry, fake_provider_stack, "dsperm")
    assert ok(create(ingress, owner, permission="team"))["permission"] == "team"
    for bad in ("all", "ME", "", "private", 1):
        resp = create(ingress, owner, permission=bad)
        assert resp.status_code == 400, (bad, resp.text)


def test_list_pages_and_filters_by_keywords(ingress: httpx.Client, registry: AccountRegistry, fake_provider_stack: FakeProvider) -> None:  # noqa: F811
    owner = workspace(ingress, registry, fake_provider_stack, "dspage")
    for name in ("Alpha_One", "AlphaTwo", "Beta 100%", "Gamma"):
        ok(create(ingress, owner, name))
    everything = ok(api(ingress, "GET", DATASETS, owner.token, params={"page_size": "100"}))
    assert everything["total"] == 4 and len(everything["items"]) == 4
    assert [d["name"] for d in everything["items"]] == ["Gamma", "Beta 100%", "AlphaTwo", "Alpha_One"], "newest first"
    second = ok(api(ingress, "GET", DATASETS, owner.token, params={"page": "2", "page_size": "3"}))
    assert second["total"] == 4 and [d["name"] for d in second["items"]] == ["Alpha_One"]
    default_page = ok(api(ingress, "GET", DATASETS, owner.token))
    assert default_page["total"] == 4 and len(default_page["items"]) == 4
    assert {d["name"] for d in ok(api(ingress, "GET", DATASETS, owner.token, params={"keywords": "ALPHA"}))["items"]} == {"Alpha_One", "AlphaTwo"}
    assert [d["name"] for d in ok(api(ingress, "GET", DATASETS, owner.token, params={"keywords": "a_o"}))["items"]] == ["Alpha_One"], "underscore is literal"
    assert [d["name"] for d in ok(api(ingress, "GET", DATASETS, owner.token, params={"keywords": "%"}))["items"]] == ["Beta 100%"], "percent is literal"
    assert ok(api(ingress, "GET", DATASETS, owner.token, params={"keywords": "zzz"})) == {"items": [], "total": 0}

    for params in ({"page": "0"}, {"page": "-1"}, {"page": "x"}, {"page_size": "0"}, {"page_size": "101"}, {"page_size": "x"}, {"keywords": "k" * 129}):
        resp = api(ingress, "GET", DATASETS, owner.token, params=params)
        assert resp.status_code == 400, (params, resp.text)


def test_creation_errors_carry_distinguishable_reasons(ingress: httpx.Client, registry: AccountRegistry, fake_provider_stack: FakeProvider) -> None:  # noqa: F811
    owner = workspace(ingress, registry, fake_provider_stack, "dserr")
    no_default = workspace(ingress, registry, fake_provider_stack, "dsnodef", default=False)
    ok(create(ingress, owner, "Docs"))

    for variant in ("Docs", "docs", " DOCS "):
        dup = create(ingress, owner, variant)
        assert dup.status_code == 409 and reason_of(dup) == "duplicate_name", dup.text
    assert ok(api(ingress, "GET", DATASETS, owner.token))["total"] == 1

    too_long = "x" * (129 - len(f"@{COMPAT}")) + f"@{COMPAT}"
    assert len(too_long) == 129
    for bad in (CHAT_ID, f"missing@{COMPAT}", "not-a-composite-id", too_long, "fake-embed@no-such-provider"):
        resp = create(ingress, owner, embd_id=bad)
        assert resp.status_code == 400 and reason_of(resp) == "model_unavailable", (bad, resp.text)

    missing = create(ingress, no_default)
    assert missing.status_code == 400 and reason_of(missing) == "no_default_embedding", missing.text
    assert ok(api(ingress, "GET", DATASETS, no_default.token))["total"] == 0, "nothing was auto-picked and nothing was stored"
    explicit = ok(create(ingress, no_default, embd_id=EMBED_ID))
    assert explicit["embd_id"] == EMBED_ID, "an explicit model works without a default"

    invalid = [{"name": ""}, {"name": "   "}, {"name": "n" * 129}, {"parser_id": "bogus"}, {"description": "d" * 2001}, {"parser_config": {"k": "v" * 4100}}]
    for body in invalid:
        resp = api(ingress, "POST", DATASETS, owner.token, body={"name": unique_name("bad"), **body})
        assert resp.status_code == 400 and reason_of(resp) == "dataset_invalid", (body, resp.text)
    assert api(ingress, "POST", DATASETS, owner.token, body={}).status_code == 400, "a name is required"
    assert api(ingress, "POST", DATASETS, owner.token, body={"name": 5}).status_code == 400
    assert api(ingress, "POST", DATASETS, owner.token, body={"name": "ok", "parser_config": "text"}).status_code == 400
    assert ok(api(ingress, "GET", DATASETS, owner.token))["total"] == 1


def test_server_owned_fields_cannot_be_assigned_by_the_client(ingress: httpx.Client, registry: AccountRegistry, fake_provider_stack: FakeProvider) -> None:  # noqa: F811
    owner = workspace(ingress, registry, fake_provider_stack, "dsmass")
    for field, value in [
        ("created_by", uuid.uuid4().hex), ("tenant_id_x", uuid.uuid4().hex), ("doc_num", 99), ("chunk_num", 1), ("token_num", 1),
        ("status", "0"), ("id", uuid.uuid4().hex), ("tenant_embd_id", uuid.uuid4().hex), ("source", "x"), ("unknown", 1),
    ]:  # fmt: skip
        resp = create(ingress, owner, **{field: value})
        assert resp.status_code == 400, (field, resp.text)
    assert ok(api(ingress, "GET", DATASETS, owner.token))["total"] == 0, "no refused create stored anything"


def test_two_concurrent_creates_with_one_name_give_one_dataset_and_one_conflict(ingress: httpx.Client, registry: AccountRegistry, fake_provider_stack: FakeProvider) -> None:  # noqa: F811
    owner = workspace(ingress, registry, fake_provider_stack, "dsrace")
    name = unique_name("race")

    def attempt(_: int) -> httpx.Response:
        with httpx.Client(base_url=BASE_URL, timeout=60.0) as client:
            return client.post(DATASETS, headers=_bearer(owner.token), json={"name": name})

    with ThreadPoolExecutor(max_workers=2) as pool:
        answers = list(pool.map(attempt, range(2)))
    assert sorted(a.status_code for a in answers) == [200, 409], [a.text for a in answers]
    assert next(a for a in answers if a.status_code == 409).json()["data"]["reason"] == "duplicate_name"
    assert ok(api(ingress, "GET", DATASETS, owner.token))["total"] == 1


def test_a_private_dataset_is_visible_to_its_creator_alone_even_for_owners_and_admins(ingress: httpx.Client, registry: AccountRegistry, fake_provider_stack: FakeProvider) -> None:  # noqa: F811
    owner = workspace(ingress, registry, fake_provider_stack, "dsvis")
    admin, member, stranger = registry.register(prefix="dsvadm"), registry.register(prefix="dsvmem"), registry.register(prefix="dsvstr")
    join(ingress, owner, admin, "admin")
    join(ingress, owner, member)
    scope = {"tenant_id": owner.tenant_id}

    mine = ok(create(ingress, owner, "owner-private"))
    shared = ok(create(ingress, owner, "owner-team", permission="team"))
    made = api(ingress, "POST", DATASETS, member.token, body={"name": "member-private", "tenant_id": owner.tenant_id})
    theirs = ok(made)
    assert theirs["tenant_id"] == owner.tenant_id and theirs["created_by"] == member.user_id and theirs["permission"] == "me"
    also = ok(api(ingress, "POST", DATASETS, member.token, body={"name": "member-team", "permission": "team", "tenant_id": owner.tenant_id}))

    def names(who: Account) -> set[str]:
        return {d["name"] for d in ok(api(ingress, "GET", DATASETS, who.token, params={**scope, "page_size": "100"}))["items"]}

    assert names(owner) == {"owner-private", "owner-team", "member-team"}, "the workspace owner has no override"
    assert names(admin) == {"owner-team", "member-team"}, "nor has an admin"
    assert names(member) == {"owner-team", "member-private", "member-team"}

    def detail(who: Account, dataset_id: str) -> httpx.Response:
        return api(ingress, "GET", f"{DATASETS}/{dataset_id}", who.token)

    assert ok(detail(owner, mine["id"]))["id"] == mine["id"] and ok(detail(owner, shared["id"]))["id"] == shared["id"]
    assert ok(detail(member, shared["id"]))["id"] == shared["id"] and ok(detail(admin, also["id"]))["id"] == also["id"]
    for who, dataset in [(owner, theirs), (admin, theirs), (member, mine), (admin, mine), (stranger, shared), (stranger, mine), (stranger, theirs)]:
        assert detail(who, dataset["id"]).json() == NOT_FOUND, (who.email, dataset["name"])
    assert detail(owner, uuid.uuid4().hex).json() == NOT_FOUND
    assert detail(owner, "not-an-id").json() == NOT_FOUND
    assert detail(owner, "x" * 300).json() == NOT_FOUND

    assert api(ingress, "GET", DATASETS, stranger.token, params=scope).json() == NOT_FOUND, "a non-member naming the workspace learns nothing"
    assert api(ingress, "POST", DATASETS, stranger.token, body={"name": "intruder", "tenant_id": owner.tenant_id}).json() == NOT_FOUND
    assert api(ingress, "POST", DATASETS, stranger.token, body={"name": "intruder", "tenant_id": "0" * 32}).json() == NOT_FOUND
    assert api(ingress, "POST", DATASETS, stranger.token, body={"name": "intruder", "tenant_id": "not-an-id"}).json() == NOT_FOUND
    assert names(owner) == {"owner-private", "owner-team", "member-team"}


def test_an_api_token_creates_only_in_its_own_workspace(ingress: httpx.Client, registry: AccountRegistry, fake_provider_stack: FakeProvider) -> None:  # noqa: F811
    owner = workspace(ingress, registry, fake_provider_stack, "dstok")
    other = workspace(ingress, registry, fake_provider_stack, "dstok2")
    created = ingress.post(TOKENS, headers=_bearer(owner.token))
    assert created.status_code == 200, created.text
    token = created.json()["data"]["token"]

    made = api(ingress, "POST", DATASETS, token, body={"name": "by-token"})
    assert ok(made)["tenant_id"] == owner.tenant_id
    assert api(ingress, "POST", DATASETS, token, body={"name": "by-token-too", "tenant_id": owner.tenant_id}).status_code == 200
    foreign = api(ingress, "POST", DATASETS, token, body={"name": "elsewhere", "tenant_id": other.tenant_id})
    assert foreign.json() == NOT_FOUND
    assert api(ingress, "GET", DATASETS, token, params={"tenant_id": other.tenant_id}).json() == NOT_FOUND
    assert {d["name"] for d in ok(api(ingress, "GET", DATASETS, token))["items"]} == {"by-token", "by-token-too"}
    assert ok(api(ingress, "GET", DATASETS, other.token))["total"] == 0, "nothing reached the other workspace"
    assert_clean(made)


def test_a_foreign_embedding_model_is_unavailable_in_my_workspace(ingress: httpx.Client, registry: AccountRegistry, fake_provider_stack: FakeProvider) -> None:  # noqa: F811
    fake = fake_provider_stack
    mine = workspace(ingress, registry, fake, "dsfm1", default=False)
    other = registry.register(prefix="dsfm2")
    ok(api(ingress, "PUT", PROVIDERS, other.token, body=save_body(fake, models=[{"name": "foreign-embed", "type": "embedding"}])))
    resp = create(ingress, mine, embd_id=f"foreign-embed@{COMPAT}")
    assert resp.status_code == 400 and reason_of(resp) == "model_unavailable", resp.text
    assert ok(create(ingress, other, embd_id=f"foreign-embed@{COMPAT}"))["embd_id"] == f"foreign-embed@{COMPAT}"
