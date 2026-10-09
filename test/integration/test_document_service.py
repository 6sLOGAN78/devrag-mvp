"""Document listing and deletion against the real MySQL, MinIO and Elasticsearch (plan 03-17; DOC-08, DOC-14, DOC-15, DOC-16, TEN-13, D-09, D-20).

Every test registers its own accounts through the running stack; the registry removes exactly those rows afterwards, with each tenant's
Elasticsearch index and MinIO objects (by exact key prefix). The storage driver is the real ``MinioStorage``; ``FaultyStorage`` (plan 03-16) records
calls and ``RmFailingStorage`` below raises on ``rm`` after recording it. Chunks are inserted into the real index with an 8-dimension vector, the
dimension of the default embedding model of these workspaces.
"""

from __future__ import annotations

import dataclasses
import re
import threading
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pytest

from api.db.services import document_service as docs
from api.db.services import knowledgebase_service as kb
from api.db.services.auth_service import AUTH_API, AUTH_BETA, Principal
from api.db.services.service_errors import Kind, ServiceError
from api.db.services.tenant_scope import ActingScope
from common.constants import BUCKET_NAME
from common.doc_store.doc_store_base import index_name
from common.settings import EsSettings
from rag.utils.es_conn import get_doc_store
from rag.utils.storage_base import StorageError
from test.helpers.doc_store_contract import row, search
from test.helpers.uploads import object_bytes, pdf_bytes, sql, tenant_object_keys, tenant_row_counts
from test.integration import test_upload_service as base
from test.integration.test_knowledgebase_service import configure, join, principal_of

pytestmark = pytest.mark.integration

# Fixtures of the upload service tests, reused by name.
_bound_database = base._bound_database
settings = base.settings
llm = base.llm
registry = base.registry
storage = base.storage
space = base.space

FaultyStorage = base.FaultyStorage
item = base.item
upload = base.upload
refused = base.refused
doc_rows = base.doc_rows
doc_num = base.doc_num

DTO_KEYS = {"id", "name", "size", "type", "suffix", "run", "progress", "dataset_id", "created_by", "parser_id", "chunk_num", "token_num", "create_time", "update_time"}
ROUNDS = 15


class RmFailingStorage(FaultyStorage):
    """The real MinIO driver whose ``rm`` records the call and then fails, as a storage outage after the commit would."""

    def rm(self, bucket, key):  # type: ignore[no-untyped-def]
        with self._counter:
            self.calls.append("rm")
        raise StorageError("storage remove failed in bucket ragflow")


# ----------------------------------------------------------------------------- helpers


def remove(cfg, who, dataset, ids, **kw: Any) -> int:
    """What the delete handler does, minus the web framework: authorise first, then delete."""
    visible = docs.authorize_removal(principal_of(who), dataset.id)
    return docs.delete_documents(cfg, visible, who.user_id, ids, **kw)


def listing(who, dataset, **kw: Any) -> tuple[list[dict], int]:
    visible = kb.load_visible_dataset(principal_of(who), dataset.id)
    return docs.list_documents(visible, **{"page": 1, "page_size": 20, "keywords": None, **kw})


def team_dataset_of(cfg, owner, creator, name: str | None = None) -> kb.DatasetRecord:
    """A ``team`` dataset of the owner's workspace created by another member (so the creator is not the workspace owner)."""
    scope = ActingScope(tenant_id=owner.tenant_id, role="normal", subject="normal")
    return kb.create_dataset(cfg, scope, creator.user_id, kb.CreateRequest(name=name or f"team-{uuid.uuid4().hex[:8]}", permission="team"))


def put_chunks(cfg, owner, dataset, doc_id: str, count: int) -> list[str]:
    rows = [row(uuid.uuid4().hex, doc_id, f"chunk {i} of {doc_id}", i % 8, i) for i in range(count)]
    assert get_doc_store(cfg).insert(rows, index_name(owner.tenant_id), dataset.id) == []
    return [r["id"] for r in rows]


def chunk_ids(cfg, owner, dataset, doc_id: str) -> list[str]:
    result = search(get_doc_store(cfg), index_name(owner.tenant_id), [dataset.id], condition={"doc_id": [doc_id]}, limit=100)
    return sorted(h["id"] for h in result.hits)


def exists(store, location: str) -> bool:
    return store.exists(BUCKET_NAME, location)


def file_rows(tenant_id: str) -> int:
    return tenant_row_counts(tenant_id)["file"]


def state_of(owner, dataset) -> tuple[list[str], dict[str, int], list[str]]:
    """Objects, row counts and document ids: what an unchanged delete must leave identical."""
    return tenant_object_keys(owner.tenant_id), tenant_row_counts(owner.tenant_id), sorted(r["id"] for r in doc_rows(dataset.id))


def race_together(calls: list[Callable[[], Any]]) -> list[Any]:
    barrier = threading.Barrier(len(calls))

    def go(call: Callable[[], Any]) -> Any:
        barrier.wait(15)
        try:
            return call()
        except Exception as exc:  # noqa: BLE001 - the test inspects the failure
            return exc

    with ThreadPoolExecutor(max_workers=len(calls)) as pool:
        futures = [pool.submit(go, call) for call in calls]
        return [f.result(timeout=90) for f in futures]


# ----------------------------------------------------------------------------- list


def test_listing_pages_newest_first_and_reports_the_total(settings, space, storage):
    owner, dataset = space
    made = [upload(settings, owner, dataset, [item(f"doc{i}.pdf", pdf_bytes(f"l{i}"))], storage=storage)[0] for i in range(5)]
    for index, doc in enumerate(made):
        sql("UPDATE `document` SET `create_time` = %s WHERE `id` = %s", (1_000_000 + index * 1000, doc["id"]))

    first, total = listing(owner, dataset, page=1, page_size=2)
    assert total == 5 and [d["name"] for d in first] == ["doc4.pdf", "doc3.pdf"], "newest first"
    second, _ = listing(owner, dataset, page=2, page_size=2)
    last, _ = listing(owner, dataset, page=3, page_size=2)
    beyond, beyond_total = listing(owner, dataset, page=4, page_size=2)
    assert [d["name"] for d in second] == ["doc2.pdf", "doc1.pdf"] and [d["name"] for d in last] == ["doc0.pdf"]
    assert beyond == [] and beyond_total == 5

    everything, count = listing(owner, dataset, page=0, page_size=1000)
    assert count == 5 and len(everything) == 5, "page below 1 is page 1; an oversized page is capped, not an error"


def test_list_rows_carry_exactly_the_allowed_keys_and_no_storage_detail(settings, space, storage):
    owner, dataset = space
    upload(settings, owner, dataset, [item("a.pdf", pdf_bytes("a"))], storage=storage)
    rows, _ = listing(owner, dataset)
    assert len(rows) == 1 and set(rows[0]) == DTO_KEYS
    banned = {"location", "status", "thumbnail", "source", "source_type", "bucket", "key"}
    assert banned.isdisjoint(rows[0])
    assert re.search(r"[0-9a-f]{32}/[0-9a-f]{32}", str(rows[0])) is None, "no storage key shape"


def test_list_shows_a_per_document_parser_override(settings, space, storage):
    owner, dataset = space
    plain = upload(settings, owner, dataset, [item("plain.pdf", pdf_bytes("p"))], storage=storage)[0]
    over = upload(settings, owner, dataset, [item("over.pdf", pdf_bytes("o"))], storage=storage, parser_id="book")[0]
    by_id = {d["id"]: d for d in listing(owner, dataset)[0]}
    assert by_id[plain["id"]]["parser_id"] == dataset.parser_id and by_id[over["id"]]["parser_id"] == "book"


def test_keywords_match_case_insensitively_and_percent_and_underscore_are_literal(settings, space, storage):
    owner, dataset = space
    for name in ("Budget 2026.pdf", "budget_notes.txt", "budgetXnotes.txt", "100%.txt", "1000.txt"):
        data = pdf_bytes(name) if name.endswith(".pdf") else base.text_bytes(name)
        upload(settings, owner, dataset, [item(name, data)], storage=storage)

    def names(word: str) -> list[str]:
        return sorted(d["name"] for d in listing(owner, dataset, keywords=word)[0])

    assert names("BUDGET") == ["Budget 2026.pdf", "budgetXnotes.txt", "budget_notes.txt"]
    assert names("t_n") == ["budget_notes.txt"], "an underscore is not a wildcard"
    assert names("100%") == ["100%.txt"], "a percent sign is not a wildcard"
    assert names("no-such-name") == []
    assert listing(owner, dataset, keywords="budget")[1] == 3, "the total follows the filter"


def test_keywords_over_128_characters_are_refused(settings, space):
    owner, dataset = space
    err = refused(lambda: listing(owner, dataset, keywords="k" * 129))
    assert err.kind is Kind.INVALID and err.reason == "query_invalid"


def test_a_caller_who_cannot_see_the_dataset_gets_not_found_from_the_list(settings, llm, registry):
    owner, stranger, member = registry.register(prefix="dlown"), registry.register(prefix="dlstr"), registry.register(prefix="dlmem")
    configure(llm, owner)
    join(owner, member)
    private = base.make(settings, owner, permission="me")
    for who, dataset_id in [(stranger, private.id), (member, private.id), (owner, uuid.uuid4().hex), (owner, "not-an-id"), (owner, "x" * 300)]:
        err = refused(lambda who=who, dataset_id=dataset_id: docs.list_view(principal_of(who), dataset_id, page=1, page_size=20, keywords=None))
        assert err.kind is Kind.NOT_FOUND
    view = docs.list_view(principal_of(owner), private.id, page=1, page_size=20, keywords=None)
    assert view == {"items": [], "total": 0}


# ----------------------------------------------------------------------------- delete and blob release


def test_a_shared_blob_stays_until_its_last_document_goes(settings, space, storage):
    owner, dataset = space
    data = pdf_bytes("shared")
    first = upload(settings, owner, dataset, [item("one.pdf", data)], storage=storage)[0]
    second = upload(settings, owner, dataset, [item("two.pdf", data)], storage=storage)[0]
    (key,) = tenant_object_keys(owner.tenant_id)
    assert tenant_row_counts(owner.tenant_id) == {"file": 1, "document": 2, "file2document": 2, "doc_num": 2}

    assert remove(settings, owner, dataset, [first["id"]], storage=storage) == 1
    assert exists(storage, key) and object_bytes(key) == data, "the second document still needs the blob"
    assert tenant_row_counts(owner.tenant_id) == {"file": 1, "document": 1, "file2document": 1, "doc_num": 1}

    assert remove(settings, owner, dataset, [second["id"]], storage=storage) == 1
    assert not exists(storage, key) and tenant_object_keys(owner.tenant_id) == []
    assert tenant_row_counts(owner.tenant_id) == {"file": 0, "document": 0, "file2document": 0, "doc_num": 0}
    assert storage.open_streams == 0


def test_a_blob_shared_with_another_dataset_of_the_workspace_is_kept(settings, space, storage):
    owner, first_set = space
    second_set = base.make(settings, owner)
    data = pdf_bytes("cross")
    a = upload(settings, owner, first_set, [item("a.pdf", data)], storage=storage)[0]
    b = upload(settings, owner, second_set, [item("b.pdf", data)], storage=storage)[0]
    (key,) = tenant_object_keys(owner.tenant_id)

    assert remove(settings, owner, first_set, [a["id"]], storage=storage) == 1
    assert exists(storage, key) and doc_rows(second_set.id)[0]["location"] == key
    assert doc_num(first_set.id) == 0 and doc_num(second_set.id) == 1
    assert remove(settings, owner, second_set, [b["id"]], storage=storage) == 1
    assert tenant_object_keys(owner.tenant_id) == [] and file_rows(owner.tenant_id) == 0


def test_deleting_several_documents_at_once_releases_each_unshared_blob(settings, space, storage):
    owner, dataset = space
    keep = upload(settings, owner, dataset, [item("keep.pdf", pdf_bytes("keep"))], storage=storage)[0]
    gone = upload(settings, owner, dataset, [item("g1.pdf", pdf_bytes("g1")), item("g2.pdf", pdf_bytes("g2"))], storage=storage)
    assert remove(settings, owner, dataset, [d["id"] for d in gone], storage=storage) == 2
    assert [r["id"] for r in doc_rows(dataset.id)] == [keep["id"]]
    assert len(tenant_object_keys(owner.tenant_id)) == 1 and doc_num(dataset.id) == 1


def test_the_chunks_of_the_deleted_document_leave_the_index_and_other_chunks_stay(settings, space, storage):
    owner, dataset = space
    one = upload(settings, owner, dataset, [item("one.pdf", pdf_bytes("c1"))], storage=storage)[0]
    two = upload(settings, owner, dataset, [item("two.pdf", pdf_bytes("c2"))], storage=storage)[0]
    mine = put_chunks(settings, owner, dataset, one["id"], 3)
    kept = put_chunks(settings, owner, dataset, two["id"], 2)
    assert chunk_ids(settings, owner, dataset, one["id"]) == sorted(mine)

    assert remove(settings, owner, dataset, [one["id"]], storage=storage) == 1
    assert chunk_ids(settings, owner, dataset, one["id"]) == [], "the chunks are pruned from the index"
    assert chunk_ids(settings, owner, dataset, two["id"]) == sorted(kept), "another document's chunks stay"


def test_chunks_of_a_same_workspace_neighbour_dataset_are_untouched(settings, space, storage):
    owner, first_set = space
    second_set = base.make(settings, owner)
    doc = upload(settings, owner, first_set, [item("a.pdf", pdf_bytes("n1"))], storage=storage)[0]
    other = upload(settings, owner, second_set, [item("b.pdf", pdf_bytes("n2"))], storage=storage)[0]
    put_chunks(settings, owner, first_set, doc["id"], 2)
    survivors = put_chunks(settings, owner, second_set, other["id"], 2)
    remove(settings, owner, first_set, [doc["id"]], storage=storage)
    assert chunk_ids(settings, owner, second_set, other["id"]) == sorted(survivors)
    assert get_doc_store(settings).index_exist(index_name(owner.tenant_id)), "the shared tenant index is never dropped"


def test_counters_drop_by_what_was_removed_and_never_below_zero(settings, space, storage):
    owner, dataset = space
    a = upload(settings, owner, dataset, [item("a.pdf", pdf_bytes("k1"))], storage=storage)[0]
    b = upload(settings, owner, dataset, [item("b.pdf", pdf_bytes("k2"))], storage=storage)[0]
    sql("UPDATE `document` SET `chunk_num` = 7, `token_num` = 70 WHERE `id` = %s", (a["id"],))
    sql("UPDATE `document` SET `chunk_num` = 3, `token_num` = 30 WHERE `id` = %s", (b["id"],))
    sql("UPDATE `knowledgebase` SET `chunk_num` = 10, `token_num` = 100 WHERE `id` = %s", (dataset.id,))
    assert remove(settings, owner, dataset, [a["id"]], storage=storage) == 1
    assert sql("SELECT `doc_num`, `chunk_num`, `token_num` FROM `knowledgebase` WHERE `id` = %s", (dataset.id,)) == [(1, 3, 30)]

    sql("UPDATE `knowledgebase` SET `doc_num` = 0, `chunk_num` = 1, `token_num` = 1 WHERE `id` = %s", (dataset.id,))
    assert remove(settings, owner, dataset, [b["id"]], storage=storage) == 1
    assert sql("SELECT `doc_num`, `chunk_num`, `token_num` FROM `knowledgebase` WHERE `id` = %s", (dataset.id,)) == [(0, 0, 0)], "an out-of-step counter stops at zero"


def test_the_tasks_of_a_deleted_document_go_with_it(settings, space, storage):
    owner, dataset = space
    doc = upload(settings, owner, dataset, [item("t.pdf", pdf_bytes("task"))], storage=storage)[0]
    sql("INSERT INTO `task` (`id`, `doc_id`, `create_time`) VALUES (%s, %s, 1)", (uuid.uuid4().hex, doc["id"]))
    remove(settings, owner, dataset, [doc["id"]], storage=storage)
    assert sql("SELECT COUNT(*) FROM `task` WHERE `doc_id` = %s", (doc["id"],)) == [(0,)]


def test_repeated_ids_in_one_call_are_one_document(settings, space, storage):
    owner, dataset = space
    doc = upload(settings, owner, dataset, [item("r.pdf", pdf_bytes("rep"))], storage=storage)[0]
    assert remove(settings, owner, dataset, [doc["id"], doc["id"]], storage=storage) == 1
    assert doc_num(dataset.id) == 0


# ----------------------------------------------------------------------------- not found and invalid input


def test_unknown_foreign_and_repeated_ids_are_not_found_and_change_nothing(settings, space, storage):
    owner, dataset = space
    other_set = base.make(settings, owner)
    mine = upload(settings, owner, dataset, [item("m.pdf", pdf_bytes("m"))], storage=storage)[0]
    theirs = upload(settings, owner, other_set, [item("t.pdf", pdf_bytes("t"))], storage=storage)[0]
    before = state_of(owner, dataset)

    for ids in ([uuid.uuid4().hex], [theirs["id"]], [mine["id"], uuid.uuid4().hex], [mine["id"], theirs["id"]]):
        err = refused(lambda ids=ids: remove(settings, owner, dataset, ids, storage=storage))
        assert err.kind is Kind.NOT_FOUND, ids
        assert state_of(owner, dataset) == before
    assert len(doc_rows(other_set.id)) == 1

    assert remove(settings, owner, dataset, [mine["id"]], storage=storage) == 1
    assert refused(lambda: remove(settings, owner, dataset, [mine["id"]], storage=storage)).kind is Kind.NOT_FOUND, "a repeated delete"


@pytest.mark.parametrize(
    "ids",
    [
        pytest.param([], id="empty"),
        pytest.param(["not-hex"], id="not-hex"),
        pytest.param(["A" * 32], id="uppercase"),
        pytest.param([5], id="not-text"),
        pytest.param(["0" * 31], id="short"),
        pytest.param([f"{i:032x}" for i in range(101)], id="over-100"),
    ],
)
def test_malformed_id_lists_are_invalid_and_touch_nothing(settings, space, storage, ids):
    owner, dataset = space
    upload(settings, owner, dataset, [item("a.pdf", pdf_bytes("inv"))], storage=storage)
    before = state_of(owner, dataset)
    err = refused(lambda: remove(settings, owner, dataset, ids, storage=storage))
    assert err.kind is Kind.INVALID and err.reason == "ids_invalid"
    assert state_of(owner, dataset) == before


def test_exactly_100_ids_are_accepted_as_a_shape(settings, space, storage):
    owner, dataset = space
    ids = [f"{i:032x}" for i in range(100)]
    err = refused(lambda: remove(settings, owner, dataset, ids, storage=storage))
    assert err.kind is Kind.NOT_FOUND, "100 well-formed ids pass the shape check and then miss"


# ----------------------------------------------------------------------------- who may delete


def test_a_member_deletes_their_own_document_but_not_anothers_and_a_mixed_list_changes_nothing(settings, llm, registry):
    owner, alice, bob = registry.register(prefix="dwown"), registry.register(prefix="dwali"), registry.register(prefix="dwbob")
    configure(llm, owner)
    join(owner, alice)
    join(owner, bob)
    dataset = base.make(settings, owner, permission="team")
    store = FaultyStorage(settings)
    alices = upload(settings, alice, dataset, [item("alice.pdf", pdf_bytes("al"))], storage=store)[0]
    bobs = upload(settings, bob, dataset, [item("bob.pdf", pdf_bytes("bo"))], storage=store)[0]
    alice_chunks = put_chunks(settings, owner, dataset, alices["id"], 2)
    before = state_of(owner, dataset)

    err = refused(lambda: remove(settings, alice, dataset, [bobs["id"]], storage=store))
    assert err.kind is Kind.FORBIDDEN and err.reason == "forbidden"
    err = refused(lambda: remove(settings, alice, dataset, [alices["id"], bobs["id"]], storage=store))
    assert err.kind is Kind.FORBIDDEN, "one document the caller may not remove refuses the whole list"
    assert state_of(owner, dataset) == before, "not even the caller's own document was removed"
    assert chunk_ids(settings, owner, dataset, alices["id"]) == sorted(alice_chunks), "and no chunk was pruned"
    assert "rm" not in store.calls

    assert remove(settings, alice, dataset, [alices["id"]], storage=store) == 1
    assert [r["id"] for r in doc_rows(dataset.id)] == [bobs["id"]]


def test_the_dataset_creator_the_owner_and_an_admin_delete_any_document_of_a_team_dataset(settings, llm, registry):
    owner, creator, admin, writer = (registry.register(prefix=p) for p in ("dxown", "dxcre", "dxadm", "dxwri"))
    configure(llm, owner)
    join(owner, creator)
    join(owner, admin, "admin")
    join(owner, writer)
    dataset = team_dataset_of(settings, owner, creator)
    store = FaultyStorage(settings)

    def written(name: str) -> str:
        return upload(settings, writer, dataset, [item(name, pdf_bytes(name))], storage=store)[0]["id"]

    assert remove(settings, creator, dataset, [written("by-creator.pdf")], storage=store) == 1, "the dataset's creator"
    assert remove(settings, owner, dataset, [written("by-owner.pdf")], storage=store) == 1, "the workspace owner"
    assert remove(settings, admin, dataset, [written("by-admin.pdf")], storage=store) == 1, "a workspace admin"
    other = written("kept.pdf")
    plain = registry.register(prefix="dxplain")
    join(owner, plain)
    assert refused(lambda: remove(settings, plain, dataset, [other], storage=store)).kind is Kind.FORBIDDEN, "a plain member who is neither uploader nor creator"
    assert doc_num(dataset.id) == 1


def test_a_private_dataset_is_invisible_for_deletion_even_to_the_owner(settings, llm, registry):
    owner, member = registry.register(prefix="dpown"), registry.register(prefix="dpmem")
    configure(llm, owner)
    join(owner, member)
    scope = ActingScope(tenant_id=owner.tenant_id, role="normal", subject="normal")
    private = kb.create_dataset(settings, scope, member.user_id, kb.CreateRequest(name=f"mine-{uuid.uuid4().hex[:6]}", permission="me"))
    doc = upload(settings, member, private, [item("p.pdf", pdf_bytes("priv"))])[0]
    err = refused(lambda: docs.authorize_removal(principal_of(owner), private.id))
    assert err.kind is Kind.NOT_FOUND, "no owner override for a private dataset (D-27)"
    assert [r["id"] for r in doc_rows(private.id)] == [doc["id"]]


def test_tokens_follow_the_matrix_and_an_api_token_is_not_elevated_to_its_owners_role(settings, llm, registry):
    owner, creator, writer = registry.register(prefix="dtown"), registry.register(prefix="dtcre"), registry.register(prefix="dtwri")
    configure(llm, owner)
    join(owner, creator)
    join(owner, writer)
    dataset = team_dataset_of(settings, owner, creator)
    store = FaultyStorage(settings)
    first = upload(settings, writer, dataset, [item("a.pdf", pdf_bytes("tok1"))], storage=store)[0]["id"]
    second = upload(settings, writer, dataset, [item("b.pdf", pdf_bytes("tok2"))], storage=store)[0]["id"]

    beta = Principal(owner.user_id, owner.tenant_id, "owner", AUTH_BETA, False)
    assert refused(lambda: docs.authorize_removal(beta, dataset.id)).kind is Kind.FORBIDDEN

    token = Principal(owner.user_id, owner.tenant_id, "owner", AUTH_API, False)
    visible = docs.authorize_removal(token, dataset.id)
    err = refused(lambda: docs.delete_documents(settings, visible, owner.user_id, [first], storage=store))
    assert err.kind is Kind.FORBIDDEN, "a token deletes what its user uploaded; the owner role is not borrowed"
    assert remove(settings, owner, dataset, [second], storage=store) == 1, "the owner's session may"


# ----------------------------------------------------------------------------- failures


def test_an_unreachable_index_is_unavailable_and_changes_nothing(settings, space, storage):
    owner, dataset = space
    doc = upload(settings, owner, dataset, [item("i.pdf", pdf_bytes("idx"))], storage=storage)[0]
    chunks = put_chunks(settings, owner, dataset, doc["id"], 2)
    before = state_of(owner, dataset)
    dead = dataclasses.replace(settings, es=EsSettings(hosts="http://127.0.0.1:1", username="elastic", password="not-a-real-password"))

    visible = docs.authorize_removal(principal_of(owner), dataset.id)
    err = refused(lambda: docs.delete_documents(dead, visible, owner.user_id, [doc["id"]], storage=storage))
    assert err.kind is Kind.UNAVAILABLE and err.reason == "index_unavailable"
    text = f"{err!r} {err} {err.message}"
    assert "127.0.0.1" not in text and "not-a-real-password" not in text
    assert state_of(owner, dataset) == before and "rm" not in storage.calls
    assert chunk_ids(settings, owner, dataset, doc["id"]) == sorted(chunks)

    assert remove(settings, owner, dataset, [doc["id"]], storage=storage) == 1, "the engine coming back is enough"


def test_a_failing_blob_removal_after_the_commit_does_not_fail_the_delete(settings, space, caplog):
    owner, dataset = space
    doc = upload(settings, owner, dataset, [item("f.pdf", pdf_bytes("rmfail"))])[0]
    (key,) = tenant_object_keys(owner.tenant_id)
    broken = RmFailingStorage(settings)
    with caplog.at_level("WARNING"):
        assert remove(settings, owner, dataset, [doc["id"]], storage=broken) == 1
    assert "rm" in broken.calls
    assert doc_rows(dataset.id) == [] and file_rows(owner.tenant_id) == 0 and doc_num(dataset.id) == 0, "the rows are gone"
    warnings = [r.getMessage() for r in caplog.records if r.levelname == "WARNING" and "blob" in r.getMessage()]
    assert warnings, "the failure is logged"
    assert not any(key in text or owner.tenant_id in text for text in warnings), "the log names the operation, never the key"
    assert exists(FaultyStorage(settings), key), "the orphan is left for a sweep, not hidden"
    FaultyStorage(settings).rm(BUCKET_NAME, key)


# ----------------------------------------------------------------------------- concurrency


@pytest.mark.parametrize("same_dataset", [True, False], ids=["same-dataset", "other-dataset"])
def test_a_delete_racing_an_upload_of_the_same_bytes_never_orphans_a_document(settings, space, same_dataset):
    owner, first_set = space
    second_set = first_set if same_dataset else base.make(settings, owner)
    store = FaultyStorage(settings)
    for round_number in range(ROUNDS):
        data = pdf_bytes(f"race{round_number}")
        first = upload(settings, owner, first_set, [item(f"first{round_number}.pdf", data)], storage=store)[0]

        results = race_together(
            [
                lambda first=first: remove(settings, owner, first_set, [first["id"]], storage=store),
                lambda n=round_number, data=data: upload(settings, owner, second_set, [item(f"second{n}.pdf", data)], storage=store)[0],
            ]
        )
        assert results[0] == 1, (round_number, results)
        assert isinstance(results[1], dict), (round_number, results)

        survivors = doc_rows(first_set.id) if same_dataset else [*doc_rows(first_set.id), *doc_rows(second_set.id)]
        assert first["id"] not in {r["id"] for r in survivors}
        assert results[1]["id"] in {r["id"] for r in survivors}
        for survivor in survivors:
            assert exists(store, survivor["location"]), f"round {round_number}: a surviving document lost its blob"
        new = next(r for r in survivors if r["id"] == results[1]["id"])
        assert object_bytes(new["location"]) == data
        assert sorted(tenant_object_keys(owner.tenant_id)) == sorted({r["location"] for r in survivors}), "and no blob is left without a document"
    assert store.open_streams == 0


def test_two_deletes_of_the_same_document_give_one_success_and_one_not_found(settings, space):
    owner, dataset = space
    store = FaultyStorage(settings)
    keep = upload(settings, owner, dataset, [item("keep.pdf", pdf_bytes("keep"))], storage=store)[0]
    doc = upload(settings, owner, dataset, [item("twice.pdf", pdf_bytes("twice"))], storage=store)[0]
    results = race_together([lambda: remove(settings, owner, dataset, [doc["id"]], storage=store) for _ in range(2)])
    assert sorted(type(r).__name__ for r in results) == ["ServiceError", "int"], results
    failure = next(r for r in results if isinstance(r, ServiceError))
    assert failure.kind is Kind.NOT_FOUND
    assert doc_num(dataset.id) == 1 and [r["id"] for r in doc_rows(dataset.id)] == [keep["id"]], "the counter dropped once"
    assert len(tenant_object_keys(owner.tenant_id)) == 1
