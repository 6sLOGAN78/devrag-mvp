"""Dataset update and delete end to end through Nginx, on the real stack (plan 03-18).

KB-06..09, TEN-13, TEN-16, DOC-14, DOC-15, D-09, D-10, D-20, D-27. Nothing of devRag is replaced: the app, Nginx, MySQL, MinIO, Elasticsearch and Valkey are
the running stack; the recording fake provider is only the third party's end of the wire that a provider save needs. Documents go in through the real upload
route; a delete is proven by the MinIO listing under the tenant's prefix, the table counts and the raw Elasticsearch client.

"Delete the dataset's index" means (decision R-136) that the dataset's rows leave the shared tenant index ``ragflow_{tenant_id}``; the index stays, with the
other datasets' chunks in it.
"""
from __future__ import annotations

import uuid

import httpx
import pytest
from elasticsearch import Elasticsearch

from common.doc_store.doc_store_base import index_name
from common.settings import load_settings
from test.helpers.accounts import Account, AccountRegistry
from test.helpers.fake_provider import FakeProvider, fake_provider_stack  # noqa: F401  (fixture)
from test.helpers.uploads import pdf_bytes, snapshot, sql, tenant_object_keys, tenant_row_counts
from test.testcases.test_dataset_flow import DATASETS, DEFAULTS, DTO_KEYS, EMBED_ID, assert_clean, create, reason_of
from test.testcases.test_provider_flow import CHAT, COMPAT, COMPAT_SLUG, EMBED, NOT_FOUND, PROVIDERS, TOKENS, _bearer, api, join, ok, registry, save_body  # noqa: F401  (registry is a fixture)
from test.testcases.test_upload_flow import one, post_files

pytestmark = pytest.mark.e2e

FORBIDDEN = {"code": 403, "message": "forbidden", "data": None}
SECOND_EMBED = {"name": "fake-embed-two", "type": "embedding"}
SECOND_EMBED_ID = f"fake-embed-two@{COMPAT}"
CHAT_ID = f"fake-chat@{COMPAT}"


@pytest.fixture(scope="module")
def raw_es():
    es = load_settings().es
    client = Elasticsearch(es.hosts, basic_auth=(es.username, es.password), request_timeout=30, max_retries=0)
    yield client
    client.close()


def dataset_path(dataset_id: str) -> str:
    return f"{DATASETS}/{dataset_id}"


def update(ingress: httpx.Client, who: Account, dataset_id: str, body: object) -> httpx.Response:
    return api(ingress, "PUT", dataset_path(dataset_id), who.token, body=body)


def remove(ingress: httpx.Client, who: Account, ids: object, **extra: object) -> httpx.Response:
    return api(ingress, "DELETE", DATASETS, who.token, body={"ids": ids, **extra})


def workspace(ingress: httpx.Client, accounts: AccountRegistry, fake: FakeProvider, prefix: str) -> Account:
    """A fresh owner with the fake chat model and two embedding models; the first is the workspace default."""
    owner = accounts.register(prefix=prefix)
    ok(api(ingress, "PUT", PROVIDERS, owner.token, body=save_body(fake, models=[CHAT, EMBED])))
    ok(api(ingress, "POST", f"{PROVIDERS}/{COMPAT_SLUG}/instances", owner.token, body={"models": [SECOND_EMBED]}))
    ok(api(ingress, "PATCH", DEFAULTS, owner.token, body={"embedding": EMBED_ID}))
    return owner


def create_in(ingress: httpx.Client, who: Account, tenant_id: str, name: str, **body: object) -> dict:
    """A dataset made by ``who`` inside the workspace ``tenant_id`` (a member creating in the owner's workspace)."""
    return ok(api(ingress, "POST", DATASETS, who.token, body={"name": name, "tenant_id": tenant_id, **body}))


def put(ingress: httpx.Client, who: Account, dataset_id: str, name: str, data: bytes) -> dict:
    return ok(post_files(ingress, who.token, dataset_id, [one(name, data)]))[0]


def gallery(ingress: httpx.Client, who: Account, tenant_id: str) -> set[str]:
    return {d["id"] for d in ok(api(ingress, "GET", DATASETS, who.token, params={"tenant_id": tenant_id, "page_size": "100"}))["items"]}


def put_chunk(ingress: httpx.Client, owner: Account, dataset_id: str, count: int) -> None:
    """Chunks go straight into the real index (parsing is a later phase); no vector is needed for the delete to find them."""
    from rag.utils.es_conn import get_doc_store

    rows = [{"id": uuid.uuid4().hex, "doc_id": uuid.uuid4().hex, "content_ltks": f"chunk {n}", "available_int": 1} for n in range(count)]
    assert get_doc_store(load_settings()).insert(rows, index_name(owner.tenant_id), dataset_id) == []


def chunk_count(es: Elasticsearch, tenant_id: str, dataset_id: str) -> int:
    es.indices.refresh(index=index_name(tenant_id))
    return int(es.count(index=index_name(tenant_id), query={"term": {"kb_id": dataset_id}}).body["count"])


# ----------------------------------------------------------------------------- update


def test_the_owner_updates_every_editable_field_and_the_answer_is_the_dataset(ingress: httpx.Client, registry: AccountRegistry, fake_provider_stack: FakeProvider) -> None:  # noqa: F811
    owner = workspace(ingress, registry, fake_provider_stack, "lfup")
    made = ok(create(ingress, owner, "  First  "))
    assert made["name"] == "First"

    body = {"name": "  Renamed  ", "description": "changed", "permission": "team", "avatar": "data:image/png;base64,AAAA", "language": "German", "parser_id": "book"}
    resp = update(ingress, owner, made["id"], body)
    data = ok(resp)
    assert resp.headers["x-api-source"] == "python"
    assert set(data) == DTO_KEYS, "the same dataset body as create, list and detail"
    assert (data["name"], data["description"], data["permission"], data["avatar"], data["language"], data["parser_id"]) == ("Renamed", "changed", "team", body["avatar"], "German", "book")
    assert (data["id"], data["tenant_id"], data["created_by"], data["embd_id"], data["doc_num"]) == (made["id"], made["tenant_id"], made["created_by"], made["embd_id"], 0)
    assert data["update_time"] >= made["update_time"] and data["create_time"] == made["create_time"]
    assert_clean(resp)
    assert ok(api(ingress, "GET", dataset_path(made["id"]), owner.token))["name"] == "Renamed"

    merged = ok(update(ingress, owner, made["id"], {"parser_config": {"chunk_token_num": 256}}))
    again = ok(update(ingress, owner, made["id"], {"parser_config": {"auto_keywords": 3}}))
    assert merged["parser_config"]["chunk_token_num"] == 256 and again["parser_config"]["chunk_token_num"] == 256 and again["parser_config"]["auto_keywords"] == 3
    assert "pages" in again["parser_config"], "the documented defaults stay"
    cleared = ok(update(ingress, owner, made["id"], {"description": None, "avatar": None}))
    assert cleared["description"] == "" and cleared["avatar"] == ""


def test_renaming_checks_duplicates_against_other_datasets_only(ingress: httpx.Client, registry: AccountRegistry, fake_provider_stack: FakeProvider) -> None:  # noqa: F811
    owner = workspace(ingress, registry, fake_provider_stack, "lfdup")
    mine, other = ok(create(ingress, owner, "Mine")), ok(create(ingress, owner, "Other"))
    assert ok(update(ingress, owner, mine["id"], {"name": "MINE"}))["name"] == "MINE", "the case of its own name may change"
    assert ok(update(ingress, owner, mine["id"], {"name": "MINE"}))["name"] == "MINE"
    for clash in ("Other", "other", " OTHER "):
        resp = update(ingress, owner, mine["id"], {"name": clash})
        assert resp.status_code == 409 and reason_of(resp) == "duplicate_name", resp.text
    assert ok(api(ingress, "GET", dataset_path(other["id"]), owner.token))["name"] == "Other"


@pytest.mark.parametrize(
    ("body", "reason"),
    [
        pytest.param({}, "fields_invalid", id="no-changes"),
        pytest.param({"name": ""}, "dataset_invalid", id="empty-name"),
        pytest.param({"name": "n" * 129}, "dataset_invalid", id="long-name"),
        pytest.param({"name": None}, "dataset_invalid", id="null-name"),
        pytest.param({"parser_id": "bogus"}, "dataset_invalid", id="bad-parser"),
        pytest.param({"permission": "all"}, "dataset_invalid", id="bad-permission"),
        pytest.param({"description": "d" * 2001}, "dataset_invalid", id="long-description"),
        pytest.param({"parser_config": {"k": "v" * 4100}}, "dataset_invalid", id="long-parser-config"),
        pytest.param({"embd_id": CHAT_ID}, "model_unavailable", id="chat-model"),
        pytest.param({"embd_id": f"missing@{COMPAT}"}, "model_unavailable", id="unknown-model"),
        pytest.param({"embd_id": "x" * 129}, "model_unavailable", id="over-long-model"),
    ],
)
def test_bad_updates_carry_a_reason_and_change_nothing(ingress: httpx.Client, registry: AccountRegistry, fake_provider_stack: FakeProvider, body: dict, reason: str) -> None:  # noqa: F811
    owner = workspace(ingress, registry, fake_provider_stack, "lfbad")
    made = ok(create(ingress, owner, "Stays"))
    resp = update(ingress, owner, made["id"], body)
    assert resp.status_code == 400 and reason_of(resp) == reason, resp.text
    assert ok(api(ingress, "GET", dataset_path(made["id"]), owner.token))["description"] == made["description"]


@pytest.mark.parametrize("field", ["tenant_id", "created_by", "doc_num", "chunk_num", "token_num", "id", "status", "tenant_embd_id", "source", "unknown"])
def test_server_owned_fields_cannot_be_assigned_by_an_update(ingress: httpx.Client, registry: AccountRegistry, fake_provider_stack: FakeProvider, field: str) -> None:  # noqa: F811
    owner = workspace(ingress, registry, fake_provider_stack, "lfmass")
    made = ok(create(ingress, owner, "Fixed"))
    before = ok(api(ingress, "GET", dataset_path(made["id"]), owner.token))
    resp = update(ingress, owner, made["id"], {"description": "x", field: 99 if field.endswith("_num") else uuid.uuid4().hex})
    assert resp.status_code == 400, resp.text
    assert ok(api(ingress, "GET", dataset_path(made["id"]), owner.token)) == before, "nothing in the refused request was applied"


def test_only_the_creator_the_owner_and_admins_update_and_a_private_dataset_stays_invisible(ingress: httpx.Client, registry: AccountRegistry, fake_provider_stack: FakeProvider) -> None:  # noqa: F811
    owner = workspace(ingress, registry, fake_provider_stack, "lfwho")
    creator, admin, plain, stranger = (registry.register(prefix=p) for p in ("lfcre", "lfadm", "lfpla", "lfstr"))
    join(ingress, owner, creator)
    join(ingress, owner, admin, "admin")
    join(ingress, owner, plain)
    team = create_in(ingress, creator, owner.tenant_id, "creator-team", permission="team")
    private = create_in(ingress, creator, owner.tenant_id, "creator-private")

    assert ok(update(ingress, creator, team["id"], {"description": "creator"}))["description"] == "creator"
    assert ok(update(ingress, owner, team["id"], {"description": "owner"}))["description"] == "owner"
    assert ok(update(ingress, admin, team["id"], {"description": "admin"}))["description"] == "admin"

    resp = update(ingress, plain, team["id"], {"description": "plain"})
    assert resp.status_code == 403 and resp.json() == FORBIDDEN, resp.text
    assert ok(api(ingress, "GET", dataset_path(team["id"]), owner.token))["description"] == "admin"

    for who in (owner, admin, plain, stranger):
        assert update(ingress, who, private["id"], {"description": "x"}).json() == NOT_FOUND, "the creator's private dataset does not exist for anyone else"
    assert update(ingress, stranger, team["id"], {"description": "x"}).json() == NOT_FOUND
    assert update(ingress, owner, uuid.uuid4().hex, {"description": "x"}).json() == NOT_FOUND
    assert update(ingress, owner, "not-an-id", {"description": "x"}).json() == NOT_FOUND
    assert ok(update(ingress, creator, private["id"], {"description": "mine"}))["description"] == "mine"


def test_an_api_token_is_not_elevated_for_datasets_it_owner_did_not_create(ingress: httpx.Client, registry: AccountRegistry, fake_provider_stack: FakeProvider) -> None:  # noqa: F811
    owner = workspace(ingress, registry, fake_provider_stack, "lftok")
    creator = registry.register(prefix="lftcr")
    join(ingress, owner, creator)
    theirs = create_in(ingress, creator, owner.tenant_id, "creator-team", permission="team")
    mine = ok(create(ingress, owner, "owner-own"))
    created = ingress.post(TOKENS, headers=_bearer(owner.token))
    assert created.status_code == 200, created.text
    token = created.json()["data"]["token"]

    denied = api(ingress, "PUT", dataset_path(theirs["id"]), token, body={"description": "by token"})
    assert denied.status_code == 403 and denied.json() == FORBIDDEN, denied.text
    assert api(ingress, "DELETE", DATASETS, token, body={"ids": [theirs["id"]]}).json() == FORBIDDEN
    assert ok(api(ingress, "PUT", dataset_path(mine["id"]), token, body={"description": "by token"}))["description"] == "by token"
    assert ok(api(ingress, "DELETE", DATASETS, token, body={"ids": [mine["id"]]}))["deleted"] == [mine["id"]]


def test_narrowing_the_permission_hides_the_dataset_from_other_members_and_keeps_their_documents(ingress: httpx.Client, registry: AccountRegistry, fake_provider_stack: FakeProvider) -> None:  # noqa: F811
    owner = workspace(ingress, registry, fake_provider_stack, "lfnar")
    member = registry.register(prefix="lfnam")
    join(ingress, owner, member)
    shared = ok(create(ingress, owner, "shared", permission="team"))
    doc = put(ingress, member, shared["id"], "member.pdf", pdf_bytes("m"))
    assert shared["id"] in gallery(ingress, member, owner.tenant_id)

    assert ok(update(ingress, owner, shared["id"], {"permission": "me"}))["permission"] == "me"
    assert shared["id"] not in gallery(ingress, member, owner.tenant_id), "the member's gallery loses it at once"
    assert api(ingress, "GET", dataset_path(shared["id"]), member.token).json() == NOT_FOUND
    assert ok(api(ingress, "GET", f"{dataset_path(shared['id'])}/documents", owner.token))["items"][0]["id"] == doc["id"], "the member's document is still in it"

    assert ok(update(ingress, owner, shared["id"], {"permission": "team"}))["permission"] == "team"
    assert shared["id"] in gallery(ingress, member, owner.tenant_id)


def test_the_embedding_model_changes_while_the_dataset_is_empty_and_is_locked_after_the_first_document(ingress: httpx.Client, registry: AccountRegistry, fake_provider_stack: FakeProvider) -> None:  # noqa: F811
    owner = workspace(ingress, registry, fake_provider_stack, "lfemb")
    made = ok(create(ingress, owner, "Embedded"))
    assert made["embd_id"] == EMBED_ID

    changed = ok(update(ingress, owner, made["id"], {"embd_id": SECOND_EMBED_ID}))
    assert changed["embd_id"] == SECOND_EMBED_ID and changed["embedding_dimension"] == fake_provider_stack.embedding_dim
    assert ok(update(ingress, owner, made["id"], {"embd_id": EMBED_ID}))["embd_id"] == EMBED_ID, "and back, while it is still empty"

    put(ingress, owner, made["id"], "first.pdf", pdf_bytes("lock"))
    locked = update(ingress, owner, made["id"], {"embd_id": SECOND_EMBED_ID, "description": "must not land"})
    assert locked.status_code == 409 and reason_of(locked) == "embedding_locked", locked.text
    detail = ok(api(ingress, "GET", dataset_path(made["id"]), owner.token))
    assert detail["embd_id"] == EMBED_ID and detail["description"] == made["description"]
    assert ok(update(ingress, owner, made["id"], {"embd_id": EMBED_ID, "description": "same model is no change"}))["description"] == "same model is no change"


# ----------------------------------------------------------------------------- delete


def test_a_delete_removes_its_content_and_unshared_blobs_and_nothing_else(ingress: httpx.Client, registry: AccountRegistry, fake_provider_stack: FakeProvider, raw_es: Elasticsearch) -> None:  # noqa: F811
    owner = workspace(ingress, registry, fake_provider_stack, "lfdel")
    doomed, keep = ok(create(ingress, owner, "Doomed")), ok(create(ingress, owner, "Keep"))
    inner, cross = pdf_bytes("inner", 400), pdf_bytes("cross", 400)
    put(ingress, owner, doomed["id"], "d1.pdf", inner)
    put(ingress, owner, doomed["id"], "d2.pdf", inner)
    put(ingress, owner, doomed["id"], "d3.pdf", cross)
    kept_doc = put(ingress, owner, keep["id"], "k1.pdf", cross)
    assert len(tenant_object_keys(owner.tenant_id)) == 2, "two blobs: the inner one and the one shared across datasets"
    put_chunk(ingress, owner, doomed["id"], 3)
    put_chunk(ingress, owner, keep["id"], 2)
    assert chunk_count(raw_es, owner.tenant_id, doomed["id"]) == 3

    resp = remove(ingress, owner, [doomed["id"]])
    assert resp.status_code == 200 and resp.json() == {"code": 0, "message": "", "data": {"deleted": [doomed["id"]]}}, resp.text
    assert resp.headers["x-api-source"] == "python"

    assert api(ingress, "GET", dataset_path(doomed["id"]), owner.token).json() == NOT_FOUND
    assert gallery(ingress, owner, owner.tenant_id) == {keep["id"]}
    assert len(tenant_object_keys(owner.tenant_id)) == 1, "the inner blob is gone; the blob keep's document still uses stays"
    assert tenant_row_counts(owner.tenant_id) == {"file": 1, "document": 1, "file2document": 1, "doc_num": 1}
    assert ok(api(ingress, "GET", f"{dataset_path(keep['id'])}/documents", owner.token))["items"][0]["id"] == kept_doc["id"]
    assert sql("SELECT COUNT(*) FROM `document` WHERE `kb_id` = %s", (doomed["id"],)) == [(0,)]

    assert raw_es.indices.exists(index=index_name(owner.tenant_id)).body is True, "the shared tenant index is not dropped (R-136)"
    assert chunk_count(raw_es, owner.tenant_id, doomed["id"]) == 0, "the dataset's rows left the index"
    assert chunk_count(raw_es, owner.tenant_id, keep["id"]) == 2, "the other dataset's chunks are untouched"

    again = remove(ingress, owner, [doomed["id"]])
    assert again.status_code == 404 and again.json() == NOT_FOUND, "a repeated delete"
    assert ok(remove(ingress, owner, [keep["id"]])) == {"deleted": [keep["id"]]}
    assert tenant_object_keys(owner.tenant_id) == [] and raw_es.indices.exists(index=index_name(owner.tenant_id)).body is True


def test_several_datasets_go_at_once_and_a_workspace_can_be_named(ingress: httpx.Client, registry: AccountRegistry, fake_provider_stack: FakeProvider) -> None:  # noqa: F811
    owner = workspace(ingress, registry, fake_provider_stack, "lfmany")
    ids = [ok(create(ingress, owner, f"many-{n}"))["id"] for n in range(3)]
    survivor = ok(create(ingress, owner, "survivor"))["id"]
    resp = remove(ingress, owner, [*ids, ids[0]], tenant_id=owner.tenant_id)
    assert ok(resp) == {"deleted": ids}, "repeated ids are one, answered in request order"
    assert gallery(ingress, owner, owner.tenant_id) == {survivor}


def test_a_list_with_one_unmanageable_or_unknown_id_changes_nothing(ingress: httpx.Client, registry: AccountRegistry, fake_provider_stack: FakeProvider) -> None:  # noqa: F811
    owner = workspace(ingress, registry, fake_provider_stack, "lfref")
    plain, creator = registry.register(prefix="lfrpl"), registry.register(prefix="lfrcr")
    join(ingress, owner, plain)
    join(ingress, owner, creator)
    mine = create_in(ingress, plain, owner.tenant_id, "plain-mine", permission="team")
    theirs = create_in(ingress, creator, owner.tenant_id, "creator-team", permission="team")
    private = create_in(ingress, creator, owner.tenant_id, "creator-private")
    put(ingress, plain, mine["id"], "m.pdf", pdf_bytes("m"))
    put(ingress, plain, theirs["id"], "t.pdf", pdf_bytes("t"))
    before = snapshot(owner.tenant_id)

    for ids in ([theirs["id"]], [mine["id"], theirs["id"]]):
        resp = api(ingress, "DELETE", DATASETS, plain.token, body={"ids": ids, "tenant_id": owner.tenant_id})
        assert resp.status_code == 403 and resp.json() == FORBIDDEN, resp.text
        assert snapshot(owner.tenant_id) == before
    for ids in ([uuid.uuid4().hex], [mine["id"], uuid.uuid4().hex], [private["id"]], [mine["id"], private["id"]]):
        resp = api(ingress, "DELETE", DATASETS, plain.token, body={"ids": ids, "tenant_id": owner.tenant_id})
        assert resp.status_code == 404 and resp.json() == NOT_FOUND, (ids, resp.text)
        assert snapshot(owner.tenant_id) == before
    assert gallery(ingress, owner, owner.tenant_id) == {mine["id"], theirs["id"]}


def test_the_creator_the_owner_and_an_admin_delete_a_team_dataset_and_a_private_one_stays_untouchable(ingress: httpx.Client, registry: AccountRegistry, fake_provider_stack: FakeProvider) -> None:  # noqa: F811
    owner = workspace(ingress, registry, fake_provider_stack, "lfwho2")
    creator, admin, plain = (registry.register(prefix=p) for p in ("lfdcr", "lfdad", "lfdpl"))
    join(ingress, owner, creator)
    join(ingress, owner, admin, "admin")
    join(ingress, owner, plain)
    scope = {"tenant_id": owner.tenant_id}
    private = create_in(ingress, creator, owner.tenant_id, "creator-private")

    for who in (creator, owner, admin):
        team = create_in(ingress, creator, owner.tenant_id, f"team-{uuid.uuid4().hex[:6]}", permission="team")
        denied = remove(ingress, plain, [team["id"]], **scope)
        assert denied.status_code == 403 and denied.json() == FORBIDDEN
        assert ok(remove(ingress, who, [team["id"]], **scope)) == {"deleted": [team["id"]]}

    for who in (owner, admin, plain):
        assert remove(ingress, who, [private["id"]], **scope).json() == NOT_FOUND
    assert ok(remove(ingress, creator, [private["id"]], **scope)) == {"deleted": [private["id"]]}


@pytest.mark.parametrize(
    ("body", "reason"),
    [
        pytest.param({"ids": []}, "ids_invalid", id="empty-list"),
        pytest.param({"ids": ["not-hex"]}, "ids_invalid", id="not-hex"),
        pytest.param({"ids": ["A" * 32]}, "ids_invalid", id="uppercase"),
        pytest.param({"ids": [f"{n:032x}" for n in range(21)]}, "ids_invalid", id="over-20"),
        pytest.param({"ids": "0" * 32}, None, id="a-bare-string"),
        pytest.param({"ids": [5]}, None, id="not-text"),
        pytest.param({}, None, id="no-ids"),
        pytest.param({"ids": ["0" * 32], "created_by": "x"}, None, id="unknown-field"),
        pytest.param({"ids": ["0" * 32], "tenant_id": "not-an-id"}, None, id="bad-tenant-id"),
    ],
)
def test_malformed_delete_bodies_are_400_and_touch_nothing(ingress: httpx.Client, registry: AccountRegistry, fake_provider_stack: FakeProvider, body: dict, reason: str | None) -> None:  # noqa: F811
    owner = workspace(ingress, registry, fake_provider_stack, "lfmal")
    made = ok(create(ingress, owner, "Safe"))
    resp = api(ingress, "DELETE", DATASETS, owner.token, body=body)
    assert resp.status_code == 400, resp.text
    assert reason_of(resp) == reason
    assert gallery(ingress, owner, owner.tenant_id) == {made["id"]}


def test_a_stranger_and_an_unauthenticated_caller_delete_nothing(ingress: httpx.Client, registry: AccountRegistry, fake_provider_stack: FakeProvider) -> None:  # noqa: F811
    owner = workspace(ingress, registry, fake_provider_stack, "lfstr2")
    stranger = registry.register(prefix="lfstx")
    made = ok(create(ingress, owner, "Theirs", permission="team"))
    for ids, extra in (([made["id"]], {}), ([made["id"]], {"tenant_id": owner.tenant_id})):
        assert remove(ingress, stranger, ids, **extra).json() == NOT_FOUND
    ingress.cookies.clear()
    bare = ingress.request("DELETE", DATASETS, json={"ids": [made["id"]]})
    assert bare.status_code == 401, bare.text
    assert gallery(ingress, owner, owner.tenant_id) == {made["id"]}
