"""Document list and delete end to end through Nginx, on the real stack (plan 03-17; E2E-04, DOC-08, DOC-14, DOC-15, DOC-16, TEN-13, D-09, D-20).

Nothing of devRag is replaced: the app, Nginx, MySQL, MinIO, Elasticsearch and Valkey are the running stack; the recording fake provider is only the
third party's end of the wire that a provider save needs. Documents are made through the real upload route. A change is proven the same way each
time: the MinIO listing under the tenant's prefix and the table counts are read before and after.
"""
from __future__ import annotations

import re
import uuid

import httpx
import pytest

from test.helpers.accounts import Account, AccountRegistry
from test.helpers.fake_provider import FakeProvider, fake_provider_stack  # noqa: F401  (fixture)
from test.helpers.uploads import pdf_bytes, snapshot, tenant_object_keys, tenant_row_counts, text_bytes
from test.testcases.test_dataset_flow import DATASETS, assert_clean, create, workspace
from test.testcases.test_provider_flow import NOT_FOUND, TOKENS, _bearer, api, join, keys_of, ok, registry  # noqa: F401  (registry is a fixture)
from test.testcases.test_upload_flow import one, post_files

pytestmark = pytest.mark.e2e

DOC_KEYS = {"id", "name", "size", "type", "suffix", "run", "progress", "dataset_id", "created_by", "parser_id", "chunk_num", "token_num", "create_time", "update_time"}
BANNED = {"status", "source", "location", "thumbnail", "bucket", "key"}
STORAGE_KEY = re.compile(r"[0-9a-f]{32}/[0-9a-f]{32}")
FORBIDDEN = {"code": 403, "message": "forbidden", "data": None}


def documents_path(dataset_id: str) -> str:
    return f"{DATASETS}/{dataset_id}/documents"


def list_docs(ingress: httpx.Client, who: Account, dataset_id: str, **params: object) -> httpx.Response:
    return api(ingress, "GET", documents_path(dataset_id), who.token, params={k: str(v) for k, v in params.items()})


def delete_docs(ingress: httpx.Client, who: Account, dataset_id: str, ids: object) -> httpx.Response:
    return api(ingress, "DELETE", documents_path(dataset_id), who.token, body={"ids": ids})


def reason_of(resp: httpx.Response) -> object:
    return (resp.json().get("data") or {}).get("reason")


def assert_no_storage_detail(resp: httpx.Response, tenant_id: str) -> None:
    assert keys_of(resp.json()).isdisjoint(BANNED), (keys_of(resp.json()) & BANNED, resp.text)
    assert STORAGE_KEY.search(resp.text) is None and f"{tenant_id}/" not in resp.text
    assert_clean(resp)


def put(ingress: httpx.Client, who: Account, dataset_id: str, name: str, data: bytes, mime: str = "application/pdf") -> dict:
    return ok(post_files(ingress, who.token, dataset_id, [one(name, data, mime)]))[0]


def doc_num(ingress: httpx.Client, who: Account, dataset_id: str) -> int:
    return int(ok(api(ingress, "GET", f"{DATASETS}/{dataset_id}", who.token))["doc_num"])


@pytest.fixture
def space(ingress: httpx.Client, registry: AccountRegistry, fake_provider_stack: FakeProvider) -> tuple[Account, str]:  # noqa: F811
    owner = workspace(ingress, registry, fake_provider_stack, "docflow")
    return owner, ok(create(ingress, owner))["id"]


# ----------------------------------------------------------------------------- list


def test_a_member_lists_documents_with_paging_and_a_total(ingress: httpx.Client, space) -> None:
    owner, dataset_id = space
    for index in range(3):
        put(ingress, owner, dataset_id, f"file{index}.pdf", pdf_bytes(f"f{index}"))
    resp = list_docs(ingress, owner, dataset_id)
    page = ok(resp)
    assert set(page) == {"items", "total"} and page["total"] == 3 and len(page["items"]) == 3
    assert all(set(d) == DOC_KEYS for d in page["items"])
    assert all(d["dataset_id"] == dataset_id and d["created_by"] == owner.user_id and d["run"] == "0" for d in page["items"])
    assert_no_storage_detail(resp, owner.tenant_id)

    first = ok(list_docs(ingress, owner, dataset_id, page=1, page_size=2))
    last = ok(list_docs(ingress, owner, dataset_id, page=2, page_size=2))
    assert first["total"] == 3 and len(first["items"]) == 2 and len(last["items"]) == 1
    assert {d["id"] for d in first["items"]}.isdisjoint({d["id"] for d in last["items"]})
    assert ok(list_docs(ingress, owner, dataset_id, page=9, page_size=2)) == {"items": [], "total": 3}


def test_keywords_filter_by_name_with_literal_wildcards(ingress: httpx.Client, space) -> None:
    owner, dataset_id = space
    put(ingress, owner, dataset_id, "Budget_2026.txt", text_bytes("a"), "text/plain")
    put(ingress, owner, dataset_id, "BudgetX2026.txt", text_bytes("b"), "text/plain")
    put(ingress, owner, dataset_id, "100%.txt", text_bytes("c"), "text/plain")
    put(ingress, owner, dataset_id, "1000.txt", text_bytes("d"), "text/plain")

    def names(word: str) -> list[str]:
        return sorted(d["name"] for d in ok(list_docs(ingress, owner, dataset_id, keywords=word))["items"])

    assert names("budget") == ["BudgetX2026.txt", "Budget_2026.txt"]
    assert names("t_2") == ["Budget_2026.txt"]
    assert names("100%") == ["100%.txt"]


@pytest.mark.parametrize(
    "params",
    [
        pytest.param({"page": "0"}, id="page-zero"),
        pytest.param({"page": "abc"}, id="page-text"),
        pytest.param({"page": "-1"}, id="page-negative"),
        pytest.param({"page_size": "0"}, id="size-zero"),
        pytest.param({"page_size": "101"}, id="size-over-100"),
        pytest.param({"page_size": "1.5"}, id="size-fraction"),
        pytest.param({"keywords": "k" * 129}, id="keywords-too-long"),
    ],
)
def test_bad_list_parameters_are_400_query_invalid(ingress: httpx.Client, space, params: dict[str, str]) -> None:
    owner, dataset_id = space
    resp = api(ingress, "GET", documents_path(dataset_id), owner.token, params=params)
    assert resp.status_code == 400 and reason_of(resp) == "query_invalid", resp.text[:200]
    assert ok(list_docs(ingress, owner, dataset_id, page_size=100)) == {"items": [], "total": 0}, "100 is the largest page"


# ----------------------------------------------------------------------------- delete


def test_a_delete_answers_the_count_and_a_shared_blob_is_removed_only_with_its_last_document(ingress: httpx.Client, space) -> None:
    owner, dataset_id = space
    shared = pdf_bytes("shared", 400)
    a = put(ingress, owner, dataset_id, "a.pdf", shared)
    b = put(ingress, owner, dataset_id, "b.pdf", shared)
    c = put(ingress, owner, dataset_id, "c.pdf", pdf_bytes("own", 400))
    assert len(tenant_object_keys(owner.tenant_id)) == 2 and doc_num(ingress, owner, dataset_id) == 3

    resp = delete_docs(ingress, owner, dataset_id, [a["id"]])
    assert resp.status_code == 200 and resp.json() == {"code": 0, "message": "", "data": {"deleted": 1}}, resp.text
    assert resp.headers["x-api-source"] == "python"
    assert len(tenant_object_keys(owner.tenant_id)) == 2, "b still uses the shared blob"
    left = ok(list_docs(ingress, owner, dataset_id))
    assert left["total"] == 2 and {d["id"] for d in left["items"]} == {b["id"], c["id"]}
    assert doc_num(ingress, owner, dataset_id) == 2

    assert ok(delete_docs(ingress, owner, dataset_id, [b["id"], c["id"]])) == {"deleted": 2}
    assert tenant_object_keys(owner.tenant_id) == [], "the last reference is gone, so is the blob"
    assert tenant_row_counts(owner.tenant_id) == {"file": 0, "document": 0, "file2document": 0, "doc_num": 0}
    assert ok(list_docs(ingress, owner, dataset_id)) == {"items": [], "total": 0}
    assert doc_num(ingress, owner, dataset_id) == 0


def test_a_blob_shared_across_two_datasets_survives_the_first_delete(ingress: httpx.Client, space) -> None:
    owner, first_set = space
    second_set = ok(create(ingress, owner))["id"]
    data = pdf_bytes("across", 400)
    a = put(ingress, owner, first_set, "a.pdf", data)
    b = put(ingress, owner, second_set, "b.pdf", data)
    assert len(tenant_object_keys(owner.tenant_id)) == 1
    assert ok(delete_docs(ingress, owner, first_set, [a["id"]])) == {"deleted": 1}
    assert len(tenant_object_keys(owner.tenant_id)) == 1 and ok(list_docs(ingress, owner, second_set))["total"] == 1
    assert ok(delete_docs(ingress, owner, second_set, [b["id"]])) == {"deleted": 1}
    assert tenant_object_keys(owner.tenant_id) == []


def test_a_member_deletes_their_own_document_and_is_forbidden_for_anothers(ingress: httpx.Client, registry: AccountRegistry, fake_provider_stack: FakeProvider) -> None:  # noqa: F811
    owner = workspace(ingress, registry, fake_provider_stack, "docperm")
    alice, bob = registry.register(prefix="docali"), registry.register(prefix="docbob")
    join(ingress, owner, alice)
    join(ingress, owner, bob)
    team = ok(create(ingress, owner, "shared", permission="team"))["id"]
    mine = put(ingress, alice, team, "alice.pdf", pdf_bytes("al"))
    theirs = put(ingress, bob, team, "bob.pdf", pdf_bytes("bo"))
    before = snapshot(owner.tenant_id)

    for ids in ([theirs["id"]], [mine["id"], theirs["id"]]):
        resp = delete_docs(ingress, alice, team, ids)
        assert resp.status_code == 403 and resp.json() == FORBIDDEN, resp.text
    assert snapshot(owner.tenant_id) == before, "a refused list changes nothing, not even the caller's own document"
    assert ok(list_docs(ingress, alice, team))["total"] == 2, "members see the team's documents"

    assert ok(delete_docs(ingress, alice, team, [mine["id"]])) == {"deleted": 1}
    assert ok(delete_docs(ingress, owner, team, [theirs["id"]])) == {"deleted": 1}, "the workspace owner may remove anyone's document"
    assert tenant_object_keys(owner.tenant_id) == []


def test_ids_from_another_dataset_and_unknown_ids_are_404_and_change_nothing(ingress: httpx.Client, space) -> None:
    owner, dataset_id = space
    other = ok(create(ingress, owner))["id"]
    mine = put(ingress, owner, dataset_id, "m.pdf", pdf_bytes("m"))
    theirs = put(ingress, owner, other, "t.pdf", pdf_bytes("t"))
    before = snapshot(owner.tenant_id)
    for ids in ([uuid.uuid4().hex], [theirs["id"]], [mine["id"], uuid.uuid4().hex]):
        resp = delete_docs(ingress, owner, dataset_id, ids)
        assert resp.status_code == 404 and resp.json() == NOT_FOUND, (ids, resp.text)
        assert snapshot(owner.tenant_id) == before
    assert ok(delete_docs(ingress, owner, dataset_id, [mine["id"]])) == {"deleted": 1}
    again = delete_docs(ingress, owner, dataset_id, [mine["id"]])
    assert again.status_code == 404 and again.json() == NOT_FOUND, "a repeated delete"


@pytest.mark.parametrize(
    ("body", "reason"),
    [
        pytest.param({"ids": []}, "ids_invalid", id="empty-list"),
        pytest.param({"ids": ["not-hex"]}, "ids_invalid", id="not-hex"),
        pytest.param({"ids": [f"{i:032x}" for i in range(101)]}, "ids_invalid", id="over-100"),
        pytest.param({"ids": [5]}, None, id="not-text"),
        pytest.param({"ids": "0" * 32}, None, id="not-a-list"),
        pytest.param({"ids": ["0" * 32], "extra": 1}, None, id="extra-field"),
        pytest.param({}, None, id="missing-ids"),
    ],
)
def test_malformed_delete_bodies_are_400_and_change_nothing(ingress: httpx.Client, space, body: dict, reason: str | None) -> None:
    owner, dataset_id = space
    put(ingress, owner, dataset_id, "a.pdf", pdf_bytes("keep"))
    before = snapshot(owner.tenant_id)
    resp = api(ingress, "DELETE", documents_path(dataset_id), owner.token, body=body)
    assert resp.status_code == 400, resp.text[:200]
    if reason is not None:
        assert reason_of(resp) == reason
    assert snapshot(owner.tenant_id) == before


# ----------------------------------------------------------------------------- who may see what


def test_foreign_private_unknown_and_malformed_datasets_are_the_one_404_for_both_routes(ingress: httpx.Client, registry: AccountRegistry, fake_provider_stack: FakeProvider) -> None:  # noqa: F811
    owner = workspace(ingress, registry, fake_provider_stack, "docfor")
    member, stranger = registry.register(prefix="docmem"), registry.register(prefix="docstr")
    join(ingress, owner, member)
    private = ok(create(ingress, owner, "owner-private"))["id"]
    doc = put(ingress, owner, private, "p.pdf", pdf_bytes("p"))
    before_owner, before_stranger = snapshot(owner.tenant_id), snapshot(stranger.tenant_id)

    for who, dataset_id in [(stranger, private), (member, private), (owner, "0" * 32), (owner, "not-an-id"), (owner, "x" * 300)]:
        listed = list_docs(ingress, who, dataset_id)
        assert listed.status_code == 404 and listed.json() == NOT_FOUND, (who.email, dataset_id)
        removed = delete_docs(ingress, who, dataset_id, [doc["id"]])
        assert removed.status_code == 404 and removed.json() == NOT_FOUND, (who.email, dataset_id)
    assert snapshot(owner.tenant_id) == before_owner and snapshot(stranger.tenant_id) == before_stranger
    assert ok(list_docs(ingress, owner, private))["total"] == 1


def test_an_api_token_lists_and_deletes_in_its_own_workspace_only(ingress: httpx.Client, registry: AccountRegistry, fake_provider_stack: FakeProvider) -> None:  # noqa: F811
    owner = workspace(ingress, registry, fake_provider_stack, "doctok")
    other = workspace(ingress, registry, fake_provider_stack, "doctok2")
    mine, theirs = ok(create(ingress, owner))["id"], ok(create(ingress, other))["id"]
    doc = put(ingress, owner, mine, "t.pdf", pdf_bytes("tok"))
    foreign_doc = put(ingress, other, theirs, "f.pdf", pdf_bytes("frn"))
    created = ingress.post(TOKENS, headers=_bearer(owner.token))
    assert created.status_code == 200, created.text
    holder = Account(owner.email, owner.password, owner.nickname, owner.user_id, owner.tenant_id, created.json()["data"]["token"])

    assert ok(list_docs(ingress, holder, mine))["total"] == 1
    before = snapshot(other.tenant_id)
    for resp in (list_docs(ingress, holder, theirs), delete_docs(ingress, holder, theirs, [foreign_doc["id"]])):
        assert resp.status_code == 404 and resp.json() == NOT_FOUND
    assert snapshot(other.tenant_id) == before
    assert ok(delete_docs(ingress, holder, mine, [doc["id"]])) == {"deleted": 1}


def test_list_and_delete_need_a_credential(ingress: httpx.Client, space) -> None:
    owner, dataset_id = space
    ingress.cookies.clear()
    assert ingress.get(documents_path(dataset_id)).status_code == 401
    assert ingress.request("DELETE", documents_path(dataset_id), json={"ids": ["0" * 32]}).status_code == 401
