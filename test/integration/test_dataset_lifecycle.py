"""Dataset update and permanent deletion against the real MySQL, MinIO and Elasticsearch (plan 03-18; KB-06..09, TEN-13, TEN-16, DOC-14, DOC-15, D-09, D-10, D-20, D-27).

Every test registers its own accounts through the running stack; the registry removes exactly those rows afterwards, with each tenant's Elasticsearch index
and MinIO objects. The storage driver is the real ``MinioStorage``; ``FaultyStorage`` (plan 03-16) records calls and ``RmFailingStorage`` (plan 03-17) raises
on ``rm`` after recording it. Chunks go into the real index with an 8-dimension vector, the dimension of ``embed-a``.

What "the index is removed" means in these tests (decision R-136): a dataset delete removes THAT DATASET'S ROWS from the per-workspace index
``ragflow_{tenant_id}`` and never drops the index, because every dataset of the workspace shares it. The raw Elasticsearch client proves both halves.
"""

from __future__ import annotations

import dataclasses
import uuid
from typing import Any

import pytest
from elasticsearch import Elasticsearch

from api.db.services import document_service as docs
from api.db.services import knowledgebase_service as kb
from api.db.services import tenant_model_service as models
from api.db.services.auth_service import AUTH_API, Principal
from api.db.services.service_errors import Kind, ServiceError
from common.constants import BUCKET_NAME
from common.doc_store.doc_store_base import index_name
from common.settings import EsSettings
from test.helpers.uploads import object_bytes, pdf_bytes, sql, tenant_object_keys, tenant_row_counts
from test.integration import test_document_service as docsvc
from test.integration import test_knowledgebase_service as kbsvc
from test.integration import test_upload_service as base

pytestmark = pytest.mark.integration

# Fixtures of the earlier service tests, reused by name.
_bound_database = base._bound_database
settings = base.settings
llm = base.llm
registry = base.registry
storage = base.storage
space = base.space
raw_es = kbsvc.raw_es

FaultyStorage = base.FaultyStorage
RmFailingStorage = docsvc.RmFailingStorage
item = base.item
upload = base.upload
refused = base.refused
doc_rows = base.doc_rows
doc_num = base.doc_num
configure = kbsvc.configure
join = kbsvc.join
principal_of = kbsvc.principal_of
make = kbsvc.make
put_chunks = docsvc.put_chunks
chunk_ids = docsvc.chunk_ids
team_dataset_of = docsvc.team_dataset_of
exists = docsvc.exists
race_together = docsvc.race_together

EMBED_A, EMBED_B, CHAT_A = kbsvc.EMBED_A, kbsvc.EMBED_B, kbsvc.CHAT_A
HUGE = f"embed-huge@{kbsvc.PROVIDER}"
ROUNDS = 12


# ----------------------------------------------------------------------------- helpers


def update(cfg, who, dataset, changes, **kw: Any) -> kb.DatasetRecord:
    """What the PUT handler does, minus the web framework: resolve what the caller can see, then update."""
    visible = kb.load_visible_dataset(principal_of(who), dataset.id)
    return kb.update_dataset(cfg, visible, who.user_id, changes, **kw)


def delete(cfg, who, ids, **kw: Any) -> list[str]:
    return kb.delete_datasets(cfg, principal_of(who), ids, **kw)


def token_of(who) -> Principal:
    """An API-token principal of ``who``'s own workspace: it inherits the workspace role but is authorised as ``api_token``."""
    return Principal(who.user_id, who.tenant_id, "owner", AUTH_API, False)


def kb_row(dataset_id: str) -> tuple | None:
    found = sql("SELECT `name`, `permission`, `embd_id`, `tenant_embd_id`, `parser_id`, `description`, `language`, `update_time` FROM `knowledgebase` WHERE `id` = %s", (dataset_id,))
    return found[0] if found else None


def dataset_ids_of(tenant_id: str) -> list[str]:
    return sorted(str(r[0]) for r in sql("SELECT `id` FROM `knowledgebase` WHERE `tenant_id` = %s", (tenant_id,)))


def chunk_count(es: Elasticsearch, tenant_id: str, dataset_id: str) -> int:
    index = index_name(tenant_id)
    es.indices.refresh(index=index)
    return int(es.count(index=index, query={"term": {"kb_id": dataset_id}}).body["count"])


def state_of(owner, *datasets: kb.DatasetRecord) -> dict[str, Any]:
    """Rows, objects and document ids of the workspace: what a refused delete or update must leave identical."""
    return {
        "datasets": dataset_ids_of(owner.tenant_id),
        "objects": tenant_object_keys(owner.tenant_id),
        "counts": tenant_row_counts(owner.tenant_id),
        "documents": {d.id: sorted(r["id"] for r in doc_rows(d.id)) for d in datasets},
        "rows": {d.id: kb_row(d.id) for d in datasets},
    }


def workspace(settings, llm, registry, prefix: str, *members: str):
    """An owner with models configured and one member per name (the first two names are a normal member and an admin when given)."""
    owner = registry.register(prefix=f"{prefix}own")
    configure(llm, owner)
    people = []
    for index, role in enumerate(members):
        person = registry.register(prefix=f"{prefix}{index}")
        join(owner, person, None if role == "normal" else role)
        people.append(person)
    return owner, *people


# ----------------------------------------------------------------------------- update: names


def test_the_creator_renames_and_the_name_is_trimmed(settings, space):
    owner, dataset = space
    renamed = update(settings, owner, dataset, {"name": "  Quarterly Reports  "})
    assert renamed.name == "Quarterly Reports" and renamed.id == dataset.id and renamed.created_by == owner.user_id
    assert kb_row(dataset.id)[0] == "Quarterly Reports"
    assert renamed.update_time >= dataset.update_time and renamed.create_time == dataset.create_time


def test_changing_only_the_case_of_its_own_name_is_allowed_and_a_clash_with_another_dataset_is_not(settings, space):
    owner, dataset = space
    other = make(settings, owner, "Plan Alpha")
    first = update(settings, owner, dataset, {"name": "Plan Beta"})
    assert update(settings, owner, first, {"name": "PLAN BETA"}).name == "PLAN BETA", "the dataset does not clash with itself"
    assert update(settings, owner, first, {"name": "PLAN BETA"}).name == "PLAN BETA", "the same name again is not a change to refuse"

    for clash in ("Plan Alpha", "plan alpha", "  PLAN ALPHA  "):
        err = refused(lambda clash=clash: update(settings, owner, first, {"name": clash}))
        assert err.kind is Kind.CONFLICT and err.reason == "duplicate_name"
    assert kb_row(dataset.id)[0] == "PLAN BETA" and kb_row(other.id)[0] == "Plan Alpha"


def test_two_renames_to_one_name_give_one_winner_and_one_conflict(settings, space):
    owner, first = space
    second = make(settings, owner)
    name = f"race-{uuid.uuid4().hex[:8]}"
    results = race_together([lambda: update(settings, owner, first, {"name": name}), lambda: update(settings, owner, second, {"name": name})])
    assert sorted(type(r).__name__ for r in results) == ["DatasetRecord", "ServiceError"], results
    loser = next(r for r in results if isinstance(r, ServiceError))
    assert loser.kind is Kind.CONFLICT and loser.reason == "duplicate_name"
    assert sum(1 for d in (first, second) if kb_row(d.id)[0] == name) == 1


def test_names_are_checked_per_workspace_only(settings, llm, registry):
    one, two = registry.register(prefix="lcn1"), registry.register(prefix="lcn2")
    configure(llm, one)
    configure(llm, two)
    mine, theirs = make(settings, one, "Shared Title"), make(settings, two)
    assert update(settings, two, theirs, {"name": "Shared Title"}).name == "Shared Title"
    assert kb_row(mine.id)[0] == "Shared Title"


# ----------------------------------------------------------------------------- update: who may


def test_the_owner_and_an_admin_update_a_team_dataset_of_another_member_and_a_normal_member_may_not(settings, llm, registry):
    owner, creator, admin, plain = workspace(settings, llm, registry, "lcw", "normal", "admin", "normal")
    dataset = team_dataset_of(settings, owner, creator)

    assert update(settings, creator, dataset, {"description": "by the creator"}).description == "by the creator"
    assert update(settings, owner, dataset, {"description": "by the owner"}).description == "by the owner"
    assert update(settings, admin, dataset, {"description": "by an admin"}).description == "by an admin"

    before = kb_row(dataset.id)
    err = refused(lambda: update(settings, plain, dataset, {"description": "by a plain member"}))
    assert err.kind is Kind.FORBIDDEN and err.reason == "forbidden"
    assert kb_row(dataset.id) == before, "a refused update changes nothing"


def test_a_private_dataset_of_someone_else_stays_invisible_to_the_owner_and_admins(settings, llm, registry):
    owner, creator, admin = workspace(settings, llm, registry, "lcp", "normal", "admin")
    scope = kbsvc.scope_of(owner, "normal")
    private = kb.create_dataset(settings, scope, creator.user_id, kb.CreateRequest(name=f"mine-{uuid.uuid4().hex[:6]}", permission="me"))
    before = kb_row(private.id)
    for who in (owner, admin):
        err = refused(lambda who=who: update(settings, who, private, {"description": "x"}))
        assert err.kind is Kind.NOT_FOUND, "no owner or admin override for a private dataset (D-27)"
    assert kb_row(private.id) == before
    assert update(settings, creator, private, {"description": "mine"}).description == "mine"


def test_an_api_token_is_not_elevated_to_its_owners_role(settings, llm, registry):
    owner, creator = workspace(settings, llm, registry, "lct", "normal")
    theirs = team_dataset_of(settings, owner, creator)
    own = make(settings, owner)

    visible = kb.load_visible_dataset(token_of(owner), theirs.id)
    err = refused(lambda: kb.update_dataset(settings, visible, owner.user_id, {"description": "by token"}))
    assert err.kind is Kind.FORBIDDEN, "a token of the owner does not manage a dataset the owner did not create"
    err = refused(lambda: kb.delete_datasets(settings, token_of(owner), [theirs.id]))
    assert err.kind is Kind.FORBIDDEN

    visible = kb.load_visible_dataset(token_of(owner), own.id)
    assert kb.update_dataset(settings, visible, owner.user_id, {"description": "mine by token"}).description == "mine by token"
    assert kb.delete_datasets(settings, token_of(owner), [own.id]) == [own.id]
    assert dataset_ids_of(owner.tenant_id) == [theirs.id]


def test_narrowing_the_permission_hides_the_dataset_at_once_and_widening_restores_it(settings, llm, registry):
    owner, creator, member = workspace(settings, llm, registry, "lcs", "normal", "normal")
    dataset = team_dataset_of(settings, owner, creator)
    uploaded = upload(settings, member, dataset, [item("member.pdf", pdf_bytes("m"))])[0]
    scope = kbsvc.scope_of(owner, "normal")

    def seen_by_member() -> bool:
        listed, _ = kb.list_datasets(scope, member.user_id, page=1, page_size=100, keywords=None)
        opens = True
        try:
            kb.load_visible_dataset(principal_of(member), dataset.id)
        except ServiceError as exc:
            assert exc.kind is Kind.NOT_FOUND
            opens = False
        assert opens == (dataset.id in {d.id for d in listed})
        return opens

    assert seen_by_member()
    assert update(settings, creator, dataset, {"permission": "me"}).permission == "me"
    assert not seen_by_member(), "narrowing hides the dataset from every other member immediately"
    assert [r["id"] for r in doc_rows(dataset.id)] == [uploaded["id"]], "the documents the member uploaded stay in it"
    assert update(settings, creator, dataset, {"permission": "team"}).permission == "team"
    assert seen_by_member()


# ----------------------------------------------------------------------------- update: fields


def test_every_editable_field_changes_and_the_rest_stays(settings, space):
    owner, dataset = space
    changed = update(
        settings,
        owner,
        dataset,
        {"description": "d", "permission": "team", "avatar": "data:image/png;base64,AAAA", "language": "German", "parser_id": "book"},
    )
    assert (changed.description, changed.permission, changed.avatar, changed.language, changed.parser_id) == ("d", "team", "data:image/png;base64,AAAA", "German", "book")
    assert (changed.tenant_id, changed.created_by, changed.embd_id, changed.doc_num, changed.chunk_num, changed.token_num) == (
        dataset.tenant_id, dataset.created_by, dataset.embd_id, 0, 0, 0,
    )  # fmt: skip
    assert kb_row(dataset.id)[1] == "team" and kb_row(dataset.id)[4] == "book" and kb_row(dataset.id)[6] == "German"
    cleared = update(settings, owner, changed, {"description": None, "avatar": None})
    assert cleared.description == "" and cleared.avatar == "", "null clears the free-text fields"


def test_the_parser_configuration_merges_over_the_defaults_and_the_stored_value(settings, space):
    owner, dataset = space
    first = update(settings, owner, dataset, {"parser_config": {"chunk_token_num": 256}})
    assert first.parser_config["chunk_token_num"] == 256 and first.parser_config["layout_recognize"] is True and "pages" in first.parser_config
    second = update(settings, owner, first, {"parser_config": {"auto_keywords": 3}})
    assert second.parser_config["chunk_token_num"] == 256, "an earlier setting survives a later partial update"
    assert second.parser_config["auto_keywords"] == 3
    assert kb.load_visible_dataset(kbsvc.principal_of(owner), dataset.id).dataset.parser_config == second.parser_config


@pytest.mark.parametrize(
    "changes",
    [
        pytest.param({}, id="no-changes"),
        pytest.param({"tenant_id": "0" * 32}, id="tenant"),
        pytest.param({"created_by": "0" * 32}, id="creator"),
        pytest.param({"doc_num": 5}, id="doc-num"),
        pytest.param({"chunk_num": 5}, id="chunk-num"),
        pytest.param({"token_num": 5}, id="token-num"),
        pytest.param({"id": "0" * 32}, id="id"),
        pytest.param({"status": "0"}, id="status"),
        pytest.param({"tenant_embd_id": "0" * 32}, id="tenant-embd-id"),
        pytest.param({"description": "ok", "doc_num": 5}, id="one-good-one-bad"),
    ],
)
def test_empty_and_server_owned_changes_are_refused_as_fields_invalid(settings, space, changes):
    owner, dataset = space
    before = state_of(owner, dataset)
    err = refused(lambda: update(settings, owner, dataset, changes))
    assert err.kind is Kind.INVALID and err.reason == "fields_invalid"
    assert state_of(owner, dataset) == before


@pytest.mark.parametrize(
    "changes",
    [
        pytest.param({"parser_id": "bogus"}, id="unknown-parser"),
        pytest.param({"parser_id": None}, id="null-parser"),
        pytest.param({"name": ""}, id="empty-name"),
        pytest.param({"name": "   "}, id="blank-name"),
        pytest.param({"name": "n" * 129}, id="long-name"),
        pytest.param({"name": None}, id="null-name"),
        pytest.param({"permission": "all"}, id="bad-permission"),
        pytest.param({"permission": None}, id="null-permission"),
        pytest.param({"description": "d" * 2001}, id="long-description"),
        pytest.param({"parser_config": {"k": "v" * 4100}}, id="long-parser-config"),
        pytest.param({"parser_config": "text"}, id="text-parser-config"),
        pytest.param({"language": ""}, id="empty-language"),
        pytest.param({"language": "L" * 33}, id="long-language"),
    ],
)
def test_bad_values_are_refused_as_dataset_invalid_and_change_nothing(settings, space, changes):
    owner, dataset = space
    before = state_of(owner, dataset)
    err = refused(lambda: update(settings, owner, dataset, changes))
    assert err.kind is Kind.INVALID and err.reason == "dataset_invalid", changes
    assert state_of(owner, dataset) == before


def test_the_view_of_an_updated_dataset_never_carries_status_or_source(settings, space):
    owner, dataset = space
    view = kb.view_of(update(settings, owner, dataset, {"description": "v"}))
    assert {"status", "source", "location"}.isdisjoint(view)
    assert set(view) == {
        "id", "name", "description", "avatar", "language", "permission", "embd_id", "embedding_dimension", "parser_id", "parser_config",
        "doc_num", "chunk_num", "token_num", "tenant_id", "created_by", "create_time", "update_time",
    }  # fmt: skip


# ----------------------------------------------------------------------------- update: the embedding model


def test_the_embedding_model_changes_on_an_empty_dataset_and_provisions_the_new_vector_field_first(settings, space, raw_es):
    owner, dataset = space
    index = index_name(owner.tenant_id)
    assert dataset.embd_id == EMBED_A
    assert kbsvc.field_mapping(raw_es, index, "q_16_vec") is None, "no 16-dimension field before the change"

    changed = update(settings, owner, dataset, {"embd_id": EMBED_B})
    assert changed.embd_id == EMBED_B
    assert changed.tenant_embd_id == next(m.id for m in models.list_models(owner.tenant_id, "embedding") if m.model == "embed-b")
    row = kb_row(dataset.id)
    assert row[2] == EMBED_B and row[3] == changed.tenant_embd_id
    mapping = kbsvc.field_mapping(raw_es, index, "q_16_vec")
    assert mapping is not None and mapping["type"] == "dense_vector" and mapping["dims"] == 16 and mapping["similarity"] == "cosine"
    assert kbsvc.field_mapping(raw_es, index, "q_8_vec")["dims"] == 8, "the old field stays: other datasets may still use it"
    assert kb.view_of(changed)["embedding_dimension"] == 16


def test_the_same_embedding_model_is_not_a_change_even_with_documents(settings, space, storage):
    owner, dataset = space
    upload(settings, owner, dataset, [item("d.pdf", pdf_bytes("same"))], storage=storage)
    assert update(settings, owner, dataset, {"embd_id": EMBED_A, "description": "kept"}).embd_id == EMBED_A


def test_the_embedding_model_is_locked_once_a_document_or_a_chunk_exists(settings, space, storage, raw_es):
    owner, dataset = space
    stale = kb.load_visible_dataset(principal_of(owner), dataset.id)
    assert stale.dataset.doc_num == 0
    upload(settings, owner, dataset, [item("first.pdf", pdf_bytes("lock"))], storage=storage)

    # The caller's copy still says the dataset is empty; the service reads the counters again under the dataset lock.
    err = refused(lambda: kb.update_dataset(settings, stale, owner.user_id, {"embd_id": EMBED_B}))
    assert err.kind is Kind.CONFLICT and err.reason == "embedding_locked"
    assert kb_row(dataset.id)[2] == EMBED_A
    assert kbsvc.field_mapping(raw_es, index_name(owner.tenant_id), "q_16_vec") is None, "a refused change provisions nothing"

    other = make(settings, owner)
    sql("UPDATE `knowledgebase` SET `chunk_num` = 3 WHERE `id` = %s", (other.id,))
    err = refused(lambda: update(settings, owner, other, {"embd_id": EMBED_B}))
    assert err.kind is Kind.CONFLICT and err.reason == "embedding_locked", "chunks alone lock it"
    sql("UPDATE `knowledgebase` SET `chunk_num` = 0 WHERE `id` = %s", (other.id,))
    assert update(settings, owner, other, {"embd_id": EMBED_B}).embd_id == EMBED_B


@pytest.mark.parametrize(
    ("embd_id", "reason"),
    [
        pytest.param(CHAT_A, "model_unavailable", id="chat-model"),
        pytest.param(f"missing@{kbsvc.PROVIDER}", "model_unavailable", id="unknown-model"),
        pytest.param("not-a-composite-id", "model_unavailable", id="malformed"),
        pytest.param("x" * 129 + f"@{kbsvc.PROVIDER}", "model_unavailable", id="over-long"),
        pytest.param(HUGE, "dimension_unsupported", id="dimension-too-large"),
    ],
)
def test_an_unusable_embedding_model_is_refused_and_changes_nothing(settings, space, embd_id, reason):
    owner, dataset = space
    before = state_of(owner, dataset)
    err = refused(lambda: update(settings, owner, dataset, {"embd_id": embd_id, "description": "must not land"}))
    assert err.kind is Kind.INVALID and err.reason == reason
    assert state_of(owner, dataset) == before, "nothing else in the same request was applied either"


def test_a_model_of_another_workspace_is_unavailable(settings, llm, registry):
    mine, theirs = registry.register(prefix="lcm1"), registry.register(prefix="lcm2")
    configure(llm, mine)
    models.save_instance(
        llm, theirs.tenant_id, kbsvc.PROVIDER, "default", api_key=kbsvc.fake_key(), api_base=None, api_version=None,
        models=[models.NewModel(name="foreign-embed", model_type="embedding", dimension=8, max_tokens=8192)], replace_key=True,
    )  # fmt: skip
    dataset = make(settings, mine)
    err = refused(lambda: update(settings, mine, dataset, {"embd_id": f"foreign-embed@{kbsvc.PROVIDER}"}))
    assert err.kind is Kind.INVALID and err.reason == "model_unavailable"


def test_an_unreachable_index_leaves_an_embedding_change_unapplied(settings, space):
    owner, dataset = space
    dead = dataclasses.replace(settings, es=EsSettings(hosts="http://127.0.0.1:1", username="elastic", password="not-a-real-password"))
    before = state_of(owner, dataset)
    err = refused(lambda: update(dead, owner, dataset, {"embd_id": EMBED_B}))
    assert err.kind is Kind.UNAVAILABLE and err.reason == "index_unavailable"
    text = f"{err!r} {err} {err.message}"
    assert "127.0.0.1" not in text and "not-a-real-password" not in text
    assert state_of(owner, dataset) == before, "the index step comes first: no row changed"


# ----------------------------------------------------------------------------- delete: who and what


def make_world(settings, owner, storage):
    """``doomed`` holds d1 and d2 (one shared blob) and d3 (a blob shared with k1 of ``keep``); chunks in both datasets and one orphan chunk."""
    doomed, keep = base.make(settings, owner, "doomed"), base.make(settings, owner, "keep")
    inner, cross = pdf_bytes("inner", 400), pdf_bytes("cross", 400)
    d1 = upload(settings, owner, doomed, [item("d1.pdf", inner)], storage=storage)[0]
    d2 = upload(settings, owner, doomed, [item("d2.pdf", inner)], storage=storage)[0]
    d3 = upload(settings, owner, doomed, [item("d3.pdf", cross)], storage=storage)[0]
    k1 = upload(settings, owner, keep, [item("k1.pdf", cross)], storage=storage)[0]
    k2 = upload(settings, owner, keep, [item("k2.pdf", pdf_bytes("own", 400))], storage=storage)[0]
    chunks = {
        "doomed": [put_chunks(settings, owner, doomed, d["id"], 2) for d in (d1, d2, d3)],
        "orphan": put_chunks(settings, owner, doomed, uuid.uuid4().hex, 2),
        "k1": put_chunks(settings, owner, keep, k1["id"], 3),
        "k2": put_chunks(settings, owner, keep, k2["id"], 1),
    }
    return doomed, keep, (d1, d2, d3), (k1, k2), chunks


def test_a_dataset_delete_removes_its_rows_chunks_and_unshared_blobs_and_nothing_else(settings, space, storage, raw_es):
    owner, _ = space
    doomed, keep, (d1, d2, d3), (k1, k2), chunks = make_world(settings, owner, storage)
    shared_inner = next(r["location"] for r in doc_rows(doomed.id) if r["id"] == d1["id"])
    assert shared_inner == next(r["location"] for r in doc_rows(doomed.id) if r["id"] == d2["id"])
    cross_key = next(r["location"] for r in doc_rows(doomed.id) if r["id"] == d3["id"])
    assert cross_key in {r["location"] for r in doc_rows(keep.id)}, "d3 and k1 share a blob"
    keep_before = {r["id"]: r["location"] for r in doc_rows(keep.id)}
    cross_bytes = object_bytes(cross_key)
    assert chunk_count(raw_es, owner.tenant_id, doomed.id) == 8 and chunk_count(raw_es, owner.tenant_id, keep.id) == 4

    assert delete(settings, owner, [doomed.id], storage=storage) == [doomed.id]

    # Rows: the dataset, its documents, tasks, links and unreferenced files are gone.
    assert kb_row(doomed.id) is None and doc_rows(doomed.id) == []
    assert sql("SELECT COUNT(*) FROM `file2document` WHERE `document_id` IN (%s, %s, %s)", (d1["id"], d2["id"], d3["id"])) == [(0,)]
    # Blobs: the one shared by d1 and d2 is gone; the one d3 shares with k1 stays, and so does keep's own.
    assert not exists(storage, shared_inner)
    assert exists(storage, cross_key) and exists(storage, keep_before[k2["id"]])
    assert sorted(tenant_object_keys(owner.tenant_id)) == sorted({keep_before[k1["id"]], keep_before[k2["id"]]})
    assert object_bytes(cross_key) == cross_bytes and {r["id"] for r in doc_rows(keep.id)} == {k1["id"], k2["id"]}
    assert {r["location"] for r in doc_rows(keep.id)} == set(keep_before.values())
    assert tenant_row_counts(owner.tenant_id)["document"] == 2 and tenant_row_counts(owner.tenant_id)["file"] == 2
    assert doc_num(keep.id) == 2
    # Index: the dataset's chunks (also the orphan ones) are gone; the shared tenant index and the neighbour's chunks are not (R-136).
    index = index_name(owner.tenant_id)
    assert raw_es.indices.exists(index=index).body is True, "the shared tenant index is never dropped"
    assert chunk_count(raw_es, owner.tenant_id, doomed.id) == 0
    assert chunk_count(raw_es, owner.tenant_id, keep.id) == 4, "the other dataset keeps every chunk"
    assert chunk_ids(settings, owner, keep, k1["id"]) == sorted(chunks["k1"])
    assert kbsvc.field_mapping(raw_es, index, "q_8_vec") is not None, "and its vector field"
    assert storage.open_streams == 0


def test_deleting_the_last_dataset_of_a_workspace_still_keeps_the_index(settings, space, storage, raw_es):
    owner, only = space
    doc = upload(settings, owner, only, [item("o.pdf", pdf_bytes("only"))], storage=storage)[0]
    put_chunks(settings, owner, only, doc["id"], 2)
    assert delete(settings, owner, [only.id], storage=storage) == [only.id]
    assert dataset_ids_of(owner.tenant_id) == [] and tenant_object_keys(owner.tenant_id) == []
    assert raw_es.indices.exists(index=index_name(owner.tenant_id)).body is True
    assert chunk_count(raw_es, owner.tenant_id, only.id) == 0
    fresh = make(settings, owner)
    assert upload(settings, owner, fresh, [item("again.pdf", pdf_bytes("again"))], storage=storage), "the workspace keeps working"


def test_the_counters_tasks_and_pipeline_rows_of_the_dataset_go_with_it(settings, space, storage):
    owner, dataset = space
    doc = upload(settings, owner, dataset, [item("t.pdf", pdf_bytes("task"))], storage=storage)[0]
    sql("INSERT INTO `task` (`id`, `doc_id`, `create_time`) VALUES (%s, %s, 1)", (uuid.uuid4().hex, doc["id"]))
    sql("INSERT INTO `connector2kb` (`id`, `connector_id`, `kb_id`, `auto_parse`, `create_time`) VALUES (%s, %s, %s, '1', 1)", (uuid.uuid4().hex, uuid.uuid4().hex, dataset.id))
    delete(settings, owner, [dataset.id], storage=storage)
    assert sql("SELECT COUNT(*) FROM `task` WHERE `doc_id` = %s", (doc["id"],)) == [(0,)]
    assert sql("SELECT COUNT(*) FROM `connector2kb` WHERE `kb_id` = %s", (dataset.id,)) == [(0,)]


def test_an_empty_dataset_and_several_datasets_at_once_are_deleted(settings, space, storage):
    owner, first = space
    second, third = make(settings, owner), make(settings, owner)
    upload(settings, owner, second, [item("s.pdf", pdf_bytes("two"))], storage=storage)
    assert delete(settings, owner, [first.id, second.id, second.id], storage=storage) == [first.id, second.id], "repeated ids are one"
    assert dataset_ids_of(owner.tenant_id) == [third.id] and tenant_object_keys(owner.tenant_id) == []


def test_a_dataset_with_more_than_one_batch_of_documents_is_deleted_completely(settings, space, storage):
    owner, dataset = space
    wide = base.limited(settings, max_files_per_request=50)
    for start in range(0, 105, 35):
        files = [item(f"bulk{start + n}.pdf", pdf_bytes(f"b{start + n}")) for n in range(35)]
        upload(wide, owner, dataset, files, storage=storage)
    assert doc_num(dataset.id) == 105 and len(tenant_object_keys(owner.tenant_id)) == 105
    assert delete(settings, owner, [dataset.id], storage=storage) == [dataset.id]
    assert tenant_object_keys(owner.tenant_id) == [] and tenant_row_counts(owner.tenant_id) == {"file": 0, "document": 0, "file2document": 0, "doc_num": 0}


def test_the_log_line_names_the_tenant_the_dataset_and_a_count_only(settings, space, storage, caplog):
    owner, dataset = space
    dataset = update(settings, owner, dataset, {"name": "Very Private Title"})
    upload(settings, owner, dataset, [item("secret-name.pdf", pdf_bytes("log"))], storage=storage)
    with caplog.at_level("INFO"):
        delete(settings, owner, [dataset.id], storage=storage)
    line = next(r.getMessage() for r in caplog.records if "dataset deleted" in r.getMessage() and dataset.id in r.getMessage())
    assert owner.tenant_id in line and "documents=1" in line
    assert "Very Private Title" not in line and "secret-name" not in line


# ----------------------------------------------------------------------------- delete: authorisation


def test_a_list_with_one_unmanageable_id_is_forbidden_and_changes_nothing(settings, llm, registry):
    owner, creator, plain = workspace(settings, llm, registry, "ldf", "normal", "normal")
    store = FaultyStorage(settings)
    mine = team_dataset_of(settings, owner, plain, "plain-mine")
    theirs = team_dataset_of(settings, owner, creator, "creator-team")
    upload(settings, plain, mine, [item("m.pdf", pdf_bytes("m"))], storage=store)
    upload(settings, plain, theirs, [item("t.pdf", pdf_bytes("t"))], storage=store)
    before = state_of(owner, mine, theirs)

    for ids in ([theirs.id], [mine.id, theirs.id], [theirs.id, mine.id]):
        err = refused(lambda ids=ids: delete(settings, plain, ids, storage=store))
        assert err.kind is Kind.FORBIDDEN and err.reason == "forbidden"
        assert state_of(owner, mine, theirs) == before
    assert "rm" not in store.calls
    assert delete(settings, plain, [mine.id], storage=store) == [mine.id], "a creator deletes their own"


def test_a_list_with_one_unknown_or_invisible_id_is_not_found_and_changes_nothing(settings, llm, registry):
    owner, creator = workspace(settings, llm, registry, "ldn", "normal")
    store = FaultyStorage(settings)
    team = make(settings, owner, permission="team")
    private = kb.create_dataset(settings, kbsvc.scope_of(owner, "normal"), creator.user_id, kb.CreateRequest(name=f"cp-{uuid.uuid4().hex[:6]}", permission="me"))
    upload(settings, owner, team, [item("t.pdf", pdf_bytes("nf"))], storage=store)
    before = state_of(owner, team, private)

    for ids in ([uuid.uuid4().hex], [team.id, uuid.uuid4().hex], [private.id], [team.id, private.id]):
        err = refused(lambda ids=ids: delete(settings, owner, ids, storage=store))
        assert err.kind is Kind.NOT_FOUND, ids
        assert state_of(owner, team, private) == before, "the visible dataset in the list is untouched too"
    stranger = kbsvc.principal_of(registry.register(prefix="ldnstr"))
    err = refused(lambda: kb.delete_datasets(settings, stranger, [team.id]))
    assert err.kind is Kind.NOT_FOUND and err.reason == "dataset_not_found"
    assert "rm" not in store.calls


def test_the_creator_the_owner_and_an_admin_delete_a_team_dataset_and_a_normal_member_does_not(settings, llm, registry):
    owner, creator, admin, plain = workspace(settings, llm, registry, "ldw", "normal", "admin", "normal")
    store = FaultyStorage(settings)
    mine = team_dataset_of(settings, owner, creator)
    for who in (creator, owner, admin):
        dataset = team_dataset_of(settings, owner, creator)
        upload(settings, creator, dataset, [item("x.pdf", pdf_bytes("w"))], storage=store)
        err = refused(lambda dataset=dataset: delete(settings, plain, [dataset.id], storage=store))
        assert err.kind is Kind.FORBIDDEN
        assert delete(settings, who, [dataset.id], storage=store) == [dataset.id]
    assert dataset_ids_of(owner.tenant_id) == [mine.id]
    assert tenant_object_keys(owner.tenant_id) == []


def test_a_private_dataset_of_a_member_cannot_be_deleted_by_the_owner_or_an_admin(settings, llm, registry):
    owner, creator, admin = workspace(settings, llm, registry, "ldq", "normal", "admin")
    private = kb.create_dataset(settings, kbsvc.scope_of(owner, "normal"), creator.user_id, kb.CreateRequest(name=f"q-{uuid.uuid4().hex[:6]}", permission="me"))
    for who in (owner, admin):
        assert refused(lambda who=who: delete(settings, who, [private.id])).kind is Kind.NOT_FOUND
    assert dataset_ids_of(owner.tenant_id) == [private.id]
    assert delete(settings, creator, [private.id]) == [private.id]


@pytest.mark.parametrize(
    "ids",
    [
        pytest.param([], id="empty"),
        pytest.param(["not-hex"], id="not-hex"),
        pytest.param(["A" * 32], id="uppercase"),
        pytest.param([5], id="not-text"),
        pytest.param(["0" * 31], id="short"),
        pytest.param([f"{i:032x}" for i in range(21)], id="over-20"),
        pytest.param("0" * 32, id="a-bare-string"),
    ],
)
def test_malformed_id_lists_are_invalid_and_touch_nothing(settings, space, ids):
    owner, dataset = space
    before = state_of(owner, dataset)
    err = refused(lambda: delete(settings, owner, ids))
    assert err.kind is Kind.INVALID and err.reason == "ids_invalid"
    assert state_of(owner, dataset) == before


def test_exactly_20_well_formed_ids_pass_the_shape_check_and_then_miss(settings, space):
    owner, _ = space
    assert refused(lambda: delete(settings, owner, [f"{i:032x}" for i in range(20)])).kind is Kind.NOT_FOUND


def test_a_repeated_delete_is_not_found(settings, space, storage):
    owner, dataset = space
    assert delete(settings, owner, [dataset.id], storage=storage) == [dataset.id]
    assert refused(lambda: delete(settings, owner, [dataset.id], storage=storage)).kind is Kind.NOT_FOUND


# ----------------------------------------------------------------------------- delete: failures


def test_an_unreachable_index_is_unavailable_and_the_dataset_is_untouched(settings, space, storage):
    owner, dataset = space
    doc = upload(settings, owner, dataset, [item("i.pdf", pdf_bytes("idx"))], storage=storage)[0]
    chunks = put_chunks(settings, owner, dataset, doc["id"], 2)
    empty = make(settings, owner)
    before = state_of(owner, dataset, empty)
    dead = dataclasses.replace(settings, es=EsSettings(hosts="http://127.0.0.1:1", username="elastic", password="not-a-real-password"))

    for ids in ([dataset.id], [empty.id], [dataset.id, empty.id]):
        err = refused(lambda ids=ids: delete(dead, owner, ids, storage=storage))
        assert err.kind is Kind.UNAVAILABLE and err.reason == "index_unavailable", ids
        assert (err.data or {}).get("deleted") == [], "nothing finished before the first failure"
        text = f"{err!r} {err} {err.message}"
        assert "127.0.0.1" not in text and "not-a-real-password" not in text
        assert state_of(owner, dataset, empty) == before and "rm" not in storage.calls
    assert chunk_ids(settings, owner, dataset, doc["id"]) == sorted(chunks)

    assert delete(settings, owner, [dataset.id, empty.id], storage=storage) == [dataset.id, empty.id], "the engine coming back is enough"


def test_a_failing_blob_removal_after_the_commit_does_not_fail_the_delete(settings, space, caplog):
    owner, dataset = space
    upload(settings, owner, dataset, [item("f.pdf", pdf_bytes("rmfail"))])
    (key,) = tenant_object_keys(owner.tenant_id)
    broken = RmFailingStorage(settings)
    with caplog.at_level("WARNING"):
        assert delete(settings, owner, [dataset.id], storage=broken) == [dataset.id]
    assert "rm" in broken.calls
    assert kb_row(dataset.id) is None and doc_rows(dataset.id) == [] and tenant_row_counts(owner.tenant_id)["file"] == 0, "the rows are gone"
    warnings = [r.getMessage() for r in caplog.records if r.levelname == "WARNING" and "blob" in r.getMessage()]
    assert warnings and not any(key in text or owner.tenant_id in text for text in warnings), "logged by operation, never by key"
    assert exists(FaultyStorage(settings), key), "the orphan is left for a sweep, not hidden"
    FaultyStorage(settings).rm(BUCKET_NAME, key)


# ----------------------------------------------------------------------------- delete: concurrency


def test_an_upload_started_after_the_delete_committed_is_not_found(settings, space, storage):
    owner, dataset = space
    visible = docs.authorize_upload(principal_of(owner), dataset.id)  # authorised before the delete, as a request in flight would be
    assert delete(settings, owner, [dataset.id], storage=storage) == [dataset.id]

    err = refused(lambda: docs.upload_documents(settings, visible, owner.user_id, [item("late.pdf", pdf_bytes("late"))], storage=storage))
    assert err.kind is Kind.NOT_FOUND
    assert refused(lambda: upload(settings, owner, dataset, [item("late2.pdf", pdf_bytes("late2"))], storage=storage)).kind is Kind.NOT_FOUND
    assert tenant_object_keys(owner.tenant_id) == [] and tenant_row_counts(owner.tenant_id) == {"file": 0, "document": 0, "file2document": 0, "doc_num": 0}


@pytest.mark.parametrize("shared", [False, True], ids=["own-bytes", "bytes-shared-with-a-survivor"])
def test_a_delete_racing_an_upload_leaves_no_orphan_document_link_or_blob(settings, space, shared):
    owner, other = space
    store = FaultyStorage(settings)
    survivor = upload(settings, owner, other, [item("survivor.pdf", pdf_bytes("sv"))], storage=store)[0]
    survivor_key = doc_rows(other.id)[0]["location"]
    survivor_bytes = object_bytes(survivor_key)
    outcomes: list[str] = []
    for round_number in range(ROUNDS):
        doomed = make(settings, owner, f"doomed-{round_number}-{uuid.uuid4().hex[:6]}")
        upload(settings, owner, doomed, [item("seed.pdf", pdf_bytes(f"seed{round_number}"))], storage=store)
        visible = docs.authorize_upload(principal_of(owner), doomed.id)
        data = survivor_bytes if shared else pdf_bytes(f"race{round_number}")

        results = race_together(
            [
                lambda doomed=doomed: delete(settings, owner, [doomed.id], storage=store),
                lambda visible=visible, n=round_number, data=data: docs.upload_documents(settings, visible, owner.user_id, [item(f"racer{n}.pdf", data)], storage=store),
            ]
        )
        assert results[0] == [doomed.id], (round_number, results)
        late = results[1]
        assert isinstance(late, (list, ServiceError)), (round_number, late)
        if isinstance(late, ServiceError):
            assert late.kind is Kind.NOT_FOUND, (round_number, late)
        outcomes.append("uploaded" if isinstance(late, list) else "refused")

        assert kb_row(doomed.id) is None
        assert doc_rows(doomed.id) == [], f"round {round_number}: a document is left in the deleted dataset"
        survivors = doc_rows(other.id)
        assert [r["id"] for r in survivors] == [survivor["id"]]
        # Everything under the tenant's prefix is exactly what the surviving dataset references.
        assert tenant_object_keys(owner.tenant_id) == [survivor_key], f"round {round_number}: an orphan blob or a lost shared blob"
        assert tenant_row_counts(owner.tenant_id) == {"file": 1, "document": 1, "file2document": 1, "doc_num": 1}, f"round {round_number}"
        assert exists(store, survivor_key) and object_bytes(survivor_key) == survivor_bytes
    assert set(outcomes) <= {"uploaded", "refused"} and store.open_streams == 0


def test_two_deletes_of_one_dataset_give_one_success_and_one_not_found(settings, space):
    owner, dataset = space
    store = FaultyStorage(settings)
    keep = make(settings, owner)
    for n in range(3):
        upload(settings, owner, dataset, [item(f"two{n}.pdf", pdf_bytes(f"two{n}"))], storage=store)
    results = race_together([lambda: delete(settings, owner, [dataset.id], storage=store) for _ in range(2)])
    assert sorted(type(r).__name__ for r in results) == ["ServiceError", "list"], results
    assert next(r for r in results if isinstance(r, ServiceError)).kind is Kind.NOT_FOUND
    assert dataset_ids_of(owner.tenant_id) == [keep.id] and tenant_object_keys(owner.tenant_id) == []


def test_the_dataset_view_after_an_upload_to_a_dataset_being_renamed_is_consistent(settings, space, storage):
    owner, dataset = space
    visible = docs.authorize_upload(principal_of(owner), dataset.id)
    results = race_together(
        [
            lambda: update(settings, owner, dataset, {"name": "Renamed During Upload"}),
            lambda: docs.upload_documents(settings, visible, owner.user_id, [item("during.pdf", pdf_bytes("during"))], storage=storage),
        ]
    )
    assert not any(isinstance(r, Exception) for r in results), results
    assert kb_row(dataset.id)[0] == "Renamed During Upload" and doc_num(dataset.id) == 1
