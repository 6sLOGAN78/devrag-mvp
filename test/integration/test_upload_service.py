"""Upload services against the real MySQL and MinIO (plan 03-16; DOC-01..07, DOC-16, STOR-01, STOR-02, STOR-11, SEC-06, TEN-13, D-09, D-14, D-20).

Every test registers its own accounts through the running stack; the registry removes exactly those rows afterwards, with each tenant's
Elasticsearch index and MinIO objects (by exact key prefix). The storage driver is the real ``MinioStorage``; ``FaultyStorage`` subclasses
it to record calls, fail the n-th write and count open read streams. It replaces nothing of devRag: every byte still goes to MinIO.
"""

from __future__ import annotations

import dataclasses
import io
import json
import os
import re
import threading
import uuid
from base64 import urlsafe_b64encode
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pytest
import xxhash

from api.db.database import DatabaseLock
from api.db.services import document_service as docs
from api.db.services import file_service
from api.db.services import knowledgebase_service as kb
from api.db.services.auth_service import AUTH_BETA, AUTH_JWT, Principal
from api.db.services.document_service import UploadItem
from api.db.services.service_errors import Kind, ServiceError
from api.db.services.tenant_scope import ActingScope
from common.settings import Settings, load_settings
from rag.utils.minio_conn import MinioStorage
from rag.utils.storage_base import StorageError
from test.helpers.accounts import Account, AccountRegistry
from test.helpers.uploads import object_bytes, pdf_bytes, snapshot, sql, tenant_object_keys, tenant_row_counts, text_bytes
from test.integration.test_knowledgebase_service import configure, join, make, principal_of
from test.testcases.conftest import BASE_URL

pytestmark = pytest.mark.integration

KEY_SHAPE = "[0-9a-f]{32}"
MIMES = {"pdf": "application/pdf", "txt": "text/plain", "exe": "application/octet-stream", "gif": "image/gif", "md": "text/markdown"}
DOC_ROWS_QUERY = (
    "SELECT `id`, `name`, `run`, `progress`, `size`, `suffix`, `type`, `content_hash`, `location`, `parser_id`, `created_by`, `source_type`, `kb_id` "
    "FROM `document` WHERE `kb_id` = %s ORDER BY `name`"
)
FILE_OF_DOCUMENT = (
    "SELECT `location`, `parent_id`, `tenant_id`, `size`, `name`, `source_type` FROM `file` "
    "WHERE `id` = (SELECT `file_id` FROM `file2document` WHERE `document_id` = %s)"
)
DTO_KEYS = {"id", "name", "size", "type", "suffix", "run", "progress", "dataset_id", "created_by", "parser_id", "chunk_num", "token_num", "create_time", "update_time"}


class _Tracked:
    """A read stream whose closing is counted, so a test can prove none is left holding a pooled connection."""

    def __init__(self, inner: Iterator[bytes], owner: FaultyStorage) -> None:
        self._inner = inner
        self._owner = owner
        self._open = True

    def __iter__(self) -> _Tracked:
        return self

    def __next__(self) -> bytes:
        try:
            return next(self._inner)
        except StopIteration:
            self.close()
            raise

    def close(self) -> None:
        if self._open:
            self._open = False
            close = getattr(self._inner, "close", None)
            if close is not None:
                close()
            self._owner.release_stream()


class FaultyStorage(MinioStorage):
    """The real MinIO driver that records every call, can raise on the n-th ``put`` and counts open read streams."""

    def __init__(self, settings: Settings, *, fail_on_put: int | None = None, crash_after_put: int | None = None) -> None:
        super().__init__(settings)
        self.calls: list[str] = []
        self.puts = 0
        self.fail_on_put = fail_on_put
        self.crash_after_put = crash_after_put
        self.open_streams = 0
        self._counter = threading.Lock()

    def release_stream(self) -> None:
        with self._counter:
            self.open_streams -= 1

    def put(self, bucket, key, data, length=None):  # type: ignore[no-untyped-def]
        with self._counter:
            self.calls.append("put")
            self.puts += 1
            number = self.puts
        if self.fail_on_put == number:
            raise StorageError("storage write failed in bucket ragflow")
        super().put(bucket, key, data, length)
        if self.crash_after_put == number:
            raise RuntimeError("simulated crash after the write")

    def rm(self, bucket, key):  # type: ignore[no-untyped-def]
        with self._counter:
            self.calls.append("rm")
        super().rm(bucket, key)

    def iter_chunks(self, bucket, key, chunk_size=1 << 20):  # type: ignore[no-untyped-def]
        with self._counter:
            self.calls.append("iter_chunks")
            self.open_streams += 1
        return _Tracked(super().iter_chunks(bucket, key, chunk_size), self)

    def size(self, bucket, key):  # type: ignore[no-untyped-def]
        with self._counter:
            self.calls.append("size")
        return super().size(bucket, key)


def _mime(name: str) -> str:
    return MIMES.get(name.rsplit(".", 1)[-1].lower(), "application/octet-stream")


def item(name: str, data: bytes, mime: str | None = None) -> UploadItem:
    return UploadItem(name=name, mime=_mime(name) if mime is None else mime, stream=io.BytesIO(data))


def upload(settings: Settings, who: Account, dataset: kb.DatasetRecord, files: list[UploadItem], *, storage: FaultyStorage | None = None, **kw: Any) -> list[dict]:
    """What the handler does, minus the web framework: authorise first, then store."""
    visible = docs.authorize_upload(principal_of(who), dataset.id)
    return docs.upload_documents(settings, visible, who.user_id, files, storage=storage, **kw)


def refused(call: Callable[[], Any]) -> ServiceError:
    with pytest.raises(ServiceError) as err:
        call()
    return err.value


def limited(settings: Settings, **upload_limits: int) -> Settings:
    return dataclasses.replace(settings, upload=dataclasses.replace(settings.upload, **upload_limits))


def doc_rows(dataset_id: str) -> list[dict[str, Any]]:
    columns = "id name run progress size suffix type content_hash location parser_id created_by source_type kb_id".split()
    rows = sql(DOC_ROWS_QUERY, (dataset_id,))
    return [dict(zip(columns, row, strict=True)) for row in rows]


def doc_num(dataset_id: str) -> int:
    return int(sql("SELECT `doc_num` FROM `knowledgebase` WHERE `id` = %s", (dataset_id,))[0][0])


def parser_config_of(document_id: str) -> dict[str, Any]:
    return json.loads(sql("SELECT `parser_config` FROM `document` WHERE `id` = %s", (document_id,))[0][0])


def run_together(calls: list[Callable[[], Any]]) -> list[Any]:
    """Start every call at the same moment on its own thread and return the results in order (errors are returned, not raised)."""
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


@pytest.fixture(scope="module", autouse=True)
def _bound_database() -> Iterator[None]:
    from api.db.database import DB, init_database

    init_database(load_settings().mysql)
    yield
    DB.close()


@pytest.fixture(scope="module")
def settings() -> Settings:
    return load_settings()


@pytest.fixture(scope="module")
def llm(settings: Settings):
    return dataclasses.replace(settings.llm, encryption_key=urlsafe_b64encode(os.urandom(32)).decode(), key_id="k1")


@pytest.fixture
def registry() -> Iterator[AccountRegistry]:
    accounts = AccountRegistry(BASE_URL)
    try:
        yield accounts
    finally:
        accounts.cleanup()


@pytest.fixture
def storage(settings: Settings) -> FaultyStorage:
    return FaultyStorage(settings)


@pytest.fixture
def space(settings: Settings, llm, registry: AccountRegistry) -> tuple[Account, kb.DatasetRecord]:
    owner = registry.register(prefix="upsvc")
    configure(llm, owner)
    return owner, make(settings, owner)


@pytest.fixture(scope="module")
def shared(settings: Settings, llm) -> Iterator[tuple[Account, kb.DatasetRecord]]:
    """One workspace and dataset for the cases that must leave everything unchanged."""
    accounts = AccountRegistry(BASE_URL)
    try:
        owner = accounts.register(prefix="upshared")
        configure(llm, owner)
        yield owner, make(settings, owner)
    finally:
        accounts.cleanup()


# ----------------------------------------------------------------------------- the happy path


def test_an_upload_stores_generated_keys_and_writes_the_rows_in_one_step(settings, space, storage):
    owner, dataset = space
    pdf, txt = pdf_bytes("one"), text_bytes("two")
    made = upload(settings, owner, dataset, [item("Plan 2026.pdf", pdf), item("notes.txt", txt)], storage=storage)

    assert [d["name"] for d in made] == ["Plan 2026.pdf", "notes.txt"]
    assert all(set(d) == DTO_KEYS for d in made), "only listed fields are returned: no location, status or thumbnail"
    assert all(d["run"] == "0" and d["progress"] == 0.0 and d["dataset_id"] == dataset.id and d["created_by"] == owner.user_id for d in made)
    assert made[0]["size"] == len(pdf) and made[0]["suffix"] == "pdf" and made[0]["type"] == "pdf"
    assert made[1]["size"] == len(txt) and made[1]["suffix"] == "txt" and made[1]["type"] == "doc"
    assert made[0]["chunk_num"] == 0 and made[0]["token_num"] == 0 and made[0]["parser_id"] == dataset.parser_id

    keys = tenant_object_keys(owner.tenant_id)
    assert len(keys) == 2 and all(re.fullmatch(f"{owner.tenant_id}/{KEY_SHAPE}", k) for k in keys)
    assert not any("plan" in k.lower() or "notes" in k.lower() for k in keys), "the client name is never part of a key"
    assert {object_bytes(k) for k in keys} == {pdf, txt}

    rows = doc_rows(dataset.id)
    assert sorted((r["name"] for r in rows), key=str.lower) == ["notes.txt", "Plan 2026.pdf"]
    for row in rows:
        assert row["run"] == "0" and row["progress"] == 0.0 and row["source_type"] == "local" and row["kb_id"] == dataset.id
        assert row["parser_id"] == dataset.parser_id and row["created_by"] == owner.user_id and len(row["content_hash"]) == 16
        file_row = sql(FILE_OF_DOCUMENT, (row["id"],))
        assert len(file_row) == 1, "each document is linked to exactly one file row"
        location, parent, tenant, size, name, source = file_row[0]
        assert location == row["location"] and location in keys, "document.location equals file.location"
        assert parent == dataset.id and tenant == owner.tenant_id and size == row["size"] and name == row["name"] and source == "knowledgebase"
    assert tenant_row_counts(owner.tenant_id) == {"file": 2, "document": 2, "file2document": 2, "doc_num": 2}
    assert doc_num(dataset.id) == 2
    assert storage.open_streams == 0


def test_the_upload_log_line_names_counts_only(settings, space, storage, caplog):
    owner, dataset = space
    with caplog.at_level("INFO"):
        upload(settings, owner, dataset, [item("log.pdf", pdf_bytes("log"))], storage=storage)
    line = next(r.getMessage() for r in caplog.records if "upload" in r.getMessage() and dataset.id in r.getMessage())
    assert owner.tenant_id in line and "files=1" in line and "reused=0" in line and "created=1" in line
    assert "log.pdf" not in line, "no file name in the log"


# ----------------------------------------------------------------------------- dedupe and names


def test_identical_content_under_two_names_is_one_blob_and_two_links(settings, space, storage):
    owner, dataset = space
    data = pdf_bytes("same")
    upload(settings, owner, dataset, [item("first.pdf", data)], storage=storage)
    upload(settings, owner, dataset, [item("second.pdf", data)], storage=storage)

    assert len(tenant_object_keys(owner.tenant_id)) == 1
    assert tenant_row_counts(owner.tenant_id) == {"file": 1, "document": 2, "file2document": 2, "doc_num": 2}
    first, second = doc_rows(dataset.id)
    assert first["location"] == second["location"] and first["content_hash"] == second["content_hash"]
    assert storage.open_streams == 0, "the byte comparison closed its read stream"
    assert "iter_chunks" in storage.calls, "a hash match was verified byte for byte before it was reused"


def test_identical_files_inside_one_request_share_one_blob(settings, space, storage):
    owner, dataset = space
    data = text_bytes("twin")
    made = upload(settings, owner, dataset, [item("a.txt", data), item("b.txt", data)], storage=storage)
    assert [d["name"] for d in made] == ["a.txt", "b.txt"]
    assert len(tenant_object_keys(owner.tenant_id)) == 1
    assert tenant_row_counts(owner.tenant_id) == {"file": 1, "document": 2, "file2document": 2, "doc_num": 2}


def test_the_same_name_again_is_kept_and_renamed_never_overwritten(settings, space, storage):
    owner, dataset = space
    one, two, three = pdf_bytes("1"), pdf_bytes("2"), pdf_bytes("3")
    assert upload(settings, owner, dataset, [item("report.pdf", one)], storage=storage)[0]["name"] == "report.pdf"
    assert upload(settings, owner, dataset, [item("report.pdf", two)], storage=storage)[0]["name"] == "report(1).pdf"
    assert upload(settings, owner, dataset, [item("REPORT.PDF", three)], storage=storage)[0]["name"] == "REPORT(2).PDF", "names compare case-insensitively"
    assert sorted(r["name"] for r in doc_rows(dataset.id)) == ["REPORT(2).PDF", "report(1).pdf", "report.pdf"]
    assert {object_bytes(k) for k in tenant_object_keys(owner.tenant_id)} == {one, two, three}
    assert doc_num(dataset.id) == 3


def test_two_files_with_one_name_in_one_request_get_distinct_names(settings, space, storage):
    owner, dataset = space
    made = upload(settings, owner, dataset, [item("x.pdf", pdf_bytes("a")), item("x.pdf", pdf_bytes("b")), item("x.pdf", pdf_bytes("c"))], storage=storage)
    assert [d["name"] for d in made] == ["x.pdf", "x(1).pdf", "x(2).pdf"]


def test_dedupe_works_across_datasets_of_one_workspace_and_stops_at_the_workspace_edge(settings, llm, space, registry, storage):
    owner, first = space
    second = make(settings, owner)
    data = pdf_bytes("shared")
    upload(settings, owner, first, [item("a.pdf", data)], storage=storage)
    upload(settings, owner, second, [item("b.pdf", data)], storage=storage)
    assert len(tenant_object_keys(owner.tenant_id)) == 1, "one blob for the workspace"
    assert doc_rows(first.id)[0]["location"] == doc_rows(second.id)[0]["location"]
    assert tenant_row_counts(owner.tenant_id) == {"file": 1, "document": 2, "file2document": 2, "doc_num": 2}

    other = registry.register(prefix="upother")
    configure(llm, other)
    theirs = make(settings, other)
    upload(settings, other, theirs, [item("a.pdf", data)], storage=storage)
    mine, others = tenant_object_keys(owner.tenant_id), tenant_object_keys(other.tenant_id)
    assert len(mine) == 1 and len(others) == 1 and mine[0].split("/")[0] != others[0].split("/")[0], "another workspace never shares a blob"
    assert doc_rows(theirs.id)[0]["location"] == others[0]


def test_a_forged_hash_and_size_match_with_different_bytes_never_links_the_other_blob(settings, llm, registry, storage):
    """Pitfall 2: the lookup key is crafted to hit the victim's blob; the byte comparison refuses it."""
    owner = registry.register(prefix="upvictim")
    attacker = registry.register(prefix="upattack")
    configure(llm, owner)
    join(owner, attacker)  # a member of the same workspace, so the tenant filter alone cannot protect the victim
    victim_set = make(settings, owner, permission="me")
    victim_bytes = pdf_bytes("victim", 400)
    forged_bytes = bytearray(victim_bytes)
    forged_bytes[-1] ^= 0x01
    forged_bytes = bytes(forged_bytes)
    assert forged_bytes != victim_bytes and len(forged_bytes) == len(victim_bytes)

    upload(settings, owner, victim_set, [item("secret.pdf", victim_bytes)], storage=storage)
    (victim_key,) = tenant_object_keys(owner.tenant_id)
    sql("UPDATE `document` SET `content_hash` = %s, `size` = %s WHERE `kb_id` = %s", (xxhash.xxh64(forged_bytes).hexdigest(), len(forged_bytes), victim_set.id))

    member_scope = ActingScope(tenant_id=owner.tenant_id, role="normal", subject="normal")
    theirs = kb.create_dataset(settings, member_scope, attacker.user_id, kb.CreateRequest(name="attacker-set", permission="me"))
    visible = docs.authorize_upload(Principal(attacker.user_id, attacker.tenant_id, "owner", AUTH_JWT, False), theirs.id)
    made = docs.upload_documents(settings, visible, attacker.user_id, [item("mine.pdf", forged_bytes)], storage=storage)

    assert len(made) == 1
    keys = tenant_object_keys(owner.tenant_id)
    assert len(keys) == 2 and victim_key in keys, "a second blob was stored and the victim's was left alone"
    assert object_bytes(victim_key) == victim_bytes
    (mine,) = doc_rows(theirs.id)
    assert mine["location"] != victim_key and object_bytes(mine["location"]) == forged_bytes, "the attacker's document points at the attacker's own bytes"
    assert "iter_chunks" in storage.calls and storage.open_streams == 0, "the comparison ran and its stream was closed on the early mismatch"
    assert tenant_row_counts(owner.tenant_id)["file"] == 2


# ----------------------------------------------------------------------------- per-document parser


def test_the_dataset_parser_is_copied_and_a_request_override_wins(settings, llm, registry, storage):
    owner = registry.register(prefix="upparser")
    configure(llm, owner)
    dataset = make(settings, owner, parser_id="paper", parser_config={"chunk_token_num": 256})
    plain = upload(settings, owner, dataset, [item("plain.pdf", pdf_bytes("p"))], storage=storage)[0]
    assert plain["parser_id"] == "paper"
    assert parser_config_of(plain["id"])["chunk_token_num"] == 256, "the dataset's configuration is copied"

    over = upload(settings, owner, dataset, [item("over.pdf", pdf_bytes("o"))], storage=storage, parser_id="book", parser_config={"chunk_token_num": 128})[0]
    assert over["parser_id"] == "book"
    config = parser_config_of(over["id"])
    assert config["chunk_token_num"] == 128 and "pages" in config, "the override is merged over the dataset's configuration"
    assert kb.load_visible_dataset(principal_of(owner), dataset.id).dataset.parser_id == "paper", "the dataset itself is untouched"


@pytest.mark.parametrize(
    "extra",
    [
        pytest.param({"parser_id": "bogus"}, id="unknown-parser"),
        pytest.param({"parser_id": 5}, id="parser-not-text"),
        pytest.param({"parser_config": {"k": "v" * 4100}}, id="config-too-long"),
        pytest.param({"parser_config": ["not", "an", "object"]}, id="config-not-an-object"),
        pytest.param({"parser_config": {"k": {1, 2}}}, id="config-not-json"),
    ],
)
def test_a_bad_parser_override_is_refused_and_stores_nothing(settings, space, storage, extra):
    owner, dataset = space
    before = snapshot(owner.tenant_id)
    err = refused(lambda: upload(settings, owner, dataset, [item("a.pdf", pdf_bytes("x"))], storage=storage, **extra))
    assert err.kind is Kind.INVALID and err.reason == "parser_invalid"
    assert snapshot(owner.tenant_id) == before and storage.calls == []


# ----------------------------------------------------------------------------- all-or-nothing validation

PDF_LIKE = pdf_bytes("dbl")
REJECTED = [
    pytest.param("run.exe", b"MZ\x90\x00binary", None, "unsupported_type", id="exe"),
    pytest.param("pic.gif", b"GIF89a" + b"\x00" * 20, None, "unsupported_type", id="gif"),
    pytest.param("invoice.pdf.exe", PDF_LIKE, "application/pdf", "unsupported_type", id="double-extension"),
    pytest.param("fake.pdf", b"this is not a pdf at all", None, "unsupported_type", id="wrong-magic"),
    pytest.param("notes.txt", b"abc\x00def", None, "unsupported_type", id="nul-in-text"),
    pytest.param("a.pdf", PDF_LIKE, "text/html", "unsupported_type", id="declared-mime"),
    pytest.param("../../etc/passwd.pdf", PDF_LIKE, None, "invalid_filename", id="traversal"),
    pytest.param("..\\evil.pdf", PDF_LIKE, None, "invalid_filename", id="backslash"),
    pytest.param("", PDF_LIKE, None, "invalid_filename", id="empty-name"),
    pytest.param("empty.pdf", b"", None, "empty_file", id="empty-file"),
]


@pytest.mark.parametrize(("name", "data", "mime", "reason"), REJECTED)
def test_every_rejection_class_leaves_storage_and_tables_unchanged(settings, shared, name, data, mime, reason):
    owner, dataset = shared
    storage = FaultyStorage(settings)
    before = snapshot(owner.tenant_id)
    err = refused(lambda: upload(settings, owner, dataset, [item(name, data, mime)], storage=storage))
    assert err.kind is Kind.INVALID and err.reason == reason
    assert snapshot(owner.tenant_id) == before, "nothing was stored and no row exists"
    assert storage.calls == [], "storage was not touched before validation finished"


def test_an_oversized_file_is_413_and_leaves_nothing(settings, shared):
    owner, dataset = shared
    storage = FaultyStorage(settings)
    before = snapshot(owner.tenant_id)
    err = refused(lambda: upload(limited(settings, max_file_bytes=1024), owner, dataset, [item("big.pdf", pdf_bytes("big", 2000))], storage=storage))
    assert err.kind is Kind.PAYLOAD_TOO_LARGE and err.reason == "file_too_large" and err.data == {"http_status": 413}
    assert snapshot(owner.tenant_id) == before and storage.calls == []


def test_one_bad_file_rejects_the_whole_mixed_batch(settings, shared):
    owner, dataset = shared
    storage = FaultyStorage(settings)
    before = snapshot(owner.tenant_id)
    batch = [item("good-one.pdf", pdf_bytes("g1")), item("good-two.txt", text_bytes("g2")), item("bad.exe", b"MZ"), item("good-three.pdf", pdf_bytes("g3"))]
    err = refused(lambda: upload(settings, owner, dataset, batch, storage=storage))
    assert err.reason == "unsupported_type"
    assert snapshot(owner.tenant_id) == before and storage.calls == []


def test_no_files_and_too_many_files_are_refused_before_anything_else(settings, shared):
    owner, dataset = shared
    storage = FaultyStorage(settings)
    before = snapshot(owner.tenant_id)
    assert refused(lambda: upload(settings, owner, dataset, [], storage=storage)).reason == "no_files"
    three = [item(f"f{i}.pdf", pdf_bytes(str(i))) for i in range(3)]
    err = refused(lambda: upload(limited(settings, max_files_per_request=2), owner, dataset, three, storage=storage))
    assert err.kind is Kind.INVALID and err.reason == "too_many_files"
    assert snapshot(owner.tenant_id) == before and storage.calls == []


def test_the_dataset_capacity_is_checked_against_the_stored_count(settings, space, storage):
    owner, dataset = space
    small = limited(settings, max_documents_per_dataset=2)
    two = [item("a.pdf", pdf_bytes("a")), item("b.pdf", pdf_bytes("b"))]
    three = [*two, item("c.pdf", pdf_bytes("c"))]
    before = snapshot(owner.tenant_id)
    err = refused(lambda: upload(small, owner, dataset, three, storage=storage))
    assert err.kind is Kind.INVALID and err.reason == "dataset_limit"
    assert snapshot(owner.tenant_id) == before and storage.calls == []

    assert len(upload(small, owner, dataset, [two[0]], storage=storage)) == 1
    after_one = snapshot(owner.tenant_id)
    err = refused(lambda: upload(small, owner, dataset, [item("d.pdf", pdf_bytes("d")), item("e.pdf", pdf_bytes("e"))], storage=storage))
    assert err.reason == "dataset_limit" and snapshot(owner.tenant_id) == after_one
    assert len(upload(small, owner, dataset, [item("f.pdf", pdf_bytes("f"))], storage=storage)) == 1
    assert doc_num(dataset.id) == 2


# ----------------------------------------------------------------------------- failure after the first write


def test_a_failing_second_write_removes_the_first_blob_and_writes_no_row(settings, space):
    owner, dataset = space
    faulty = FaultyStorage(settings, fail_on_put=2)
    before = snapshot(owner.tenant_id)
    err = refused(lambda: upload(settings, owner, dataset, [item("a.pdf", pdf_bytes("a")), item("b.pdf", pdf_bytes("b")), item("c.pdf", pdf_bytes("c"))], storage=faulty))
    assert err.kind is Kind.UNAVAILABLE and err.reason == "storage_unavailable"
    assert faulty.puts == 2 and "rm" in faulty.calls
    assert tenant_object_keys(owner.tenant_id) == before[0] == [], "the blob written before the failure is gone"
    assert tenant_row_counts(owner.tenant_id) == before[1] and doc_num(dataset.id) == 0


def test_an_unexpected_error_after_a_blob_was_written_removes_it_and_leaves_no_row(settings, space):
    """Not a storage error: the driver wrote the first blob and then something else broke inside the transaction."""
    owner, dataset = space
    faulty = FaultyStorage(settings, crash_after_put=1)
    before = snapshot(owner.tenant_id)
    with pytest.raises(RuntimeError, match="simulated crash"):
        upload(settings, owner, dataset, [item("a.pdf", pdf_bytes("a")), item("b.pdf", pdf_bytes("b"))], storage=faulty)
    assert faulty.puts == 1 and "rm" in faulty.calls, "a blob was written and then released"
    assert snapshot(owner.tenant_id) == before and doc_num(dataset.id) == 0


def test_a_reused_blob_is_never_removed_by_the_compensation(settings, space):
    owner, dataset = space
    keep = pdf_bytes("keep")
    upload(settings, owner, dataset, [item("keep.pdf", keep)])
    (key,) = tenant_object_keys(owner.tenant_id)
    faulty = FaultyStorage(settings, fail_on_put=1)
    err = refused(lambda: upload(settings, owner, dataset, [item("again.pdf", keep), item("new.pdf", pdf_bytes("new"))], storage=faulty))
    assert err.reason == "storage_unavailable"
    assert tenant_object_keys(owner.tenant_id) == [key], "only the keys this request created were released"
    assert object_bytes(key) == keep and doc_num(dataset.id) == 1


# ----------------------------------------------------------------------------- the lock and concurrency


def test_the_upload_lock_is_named_per_dataset_and_fits_the_mysql_limit(space):
    _, dataset = space
    assert docs.upload_lock_name(dataset.id) == f"kb-upload:{dataset.id}"
    assert len(docs.upload_lock_name(dataset.id)) == 42


def test_a_held_upload_lock_makes_a_second_upload_wait_and_then_report_busy(settings, space, storage):
    owner, dataset = space
    before = snapshot(owner.tenant_id)
    with DatabaseLock(docs.upload_lock_name(dataset.id), 5):
        err = refused(lambda: upload(settings, owner, dataset, [item("a.pdf", pdf_bytes("a"))], storage=storage, lock_timeout=1))
    assert err.kind is Kind.UNAVAILABLE and err.reason == "busy"
    assert snapshot(owner.tenant_id) == before and storage.calls == []
    assert len(upload(settings, owner, dataset, [item("a.pdf", pdf_bytes("a"))], storage=storage)) == 1, "released: the next upload goes through"


def test_two_threads_uploading_one_name_get_x_and_x_1(settings, space):
    owner, dataset = space
    results = run_together([lambda b=pdf_bytes(f"t{i}"): upload(settings, owner, dataset, [item("x.pdf", b)]) for i in range(2)])
    assert not any(isinstance(r, Exception) for r in results), results
    assert sorted(r[0]["name"] for r in results) == ["x(1).pdf", "x.pdf"]
    assert doc_num(dataset.id) == 2 and len(doc_rows(dataset.id)) == 2


def test_two_threads_uploading_identical_bytes_store_one_blob(settings, space):
    owner, dataset = space
    data = pdf_bytes("race")
    results = run_together([lambda n=n: upload(settings, owner, dataset, [item(n, data)]) for n in ("p.pdf", "q.pdf")])
    assert not any(isinstance(r, Exception) for r in results), results
    assert len(tenant_object_keys(owner.tenant_id)) == 1
    assert tenant_row_counts(owner.tenant_id) == {"file": 1, "document": 2, "file2document": 2, "doc_num": 2}


def test_many_parallel_uploads_keep_the_counter_exact(settings, space):
    owner, dataset = space
    results = run_together([lambda i=i: upload(settings, owner, dataset, [item(f"n{i}.pdf", pdf_bytes(f"n{i}"))]) for i in range(6)])
    assert not any(isinstance(r, Exception) for r in results), results
    assert doc_num(dataset.id) == 6 == len(doc_rows(dataset.id))


# ----------------------------------------------------------------------------- authorisation before any storage call


def test_a_caller_who_cannot_see_the_dataset_gets_not_found_before_storage(settings, llm, registry):
    owner = registry.register(prefix="upown")
    stranger = registry.register(prefix="upstr")
    member = registry.register(prefix="upmem")
    configure(llm, owner)
    join(owner, member)
    private = make(settings, owner, permission="me")
    faulty = FaultyStorage(settings)

    for who, dataset_id in [(stranger, private.id), (member, private.id), (owner, uuid.uuid4().hex), (owner, "not-an-id"), (owner, "x" * 300)]:
        err = refused(lambda who=who, dataset_id=dataset_id: docs.authorize_upload(principal_of(who), dataset_id))
        assert err.kind is Kind.NOT_FOUND
    err = refused(lambda: upload(settings, stranger, private, [item("a.pdf", pdf_bytes("a"))], storage=faulty))
    assert err.kind is Kind.NOT_FOUND
    assert faulty.calls == [] and tenant_object_keys(owner.tenant_id) == [] and tenant_object_keys(stranger.tenant_id) == []
    assert tenant_row_counts(owner.tenant_id)["document"] == 0 and doc_num(private.id) == 0


def test_a_caller_without_the_document_permission_is_forbidden_before_storage(settings, space):
    owner, dataset = space
    faulty = FaultyStorage(settings)
    beta = Principal(owner.user_id, owner.tenant_id, "owner", AUTH_BETA, False)
    err = refused(lambda: docs.authorize_upload(beta, dataset.id))
    assert err.kind is Kind.FORBIDDEN
    assert faulty.calls == [] and tenant_object_keys(owner.tenant_id) == []


def test_any_member_may_upload_into_a_team_dataset_but_not_into_anothers_private_one(settings, llm, registry):
    owner = registry.register(prefix="upteam")
    member = registry.register(prefix="upteam2")
    configure(llm, owner)
    join(owner, member)
    team, private = make(settings, owner, permission="team"), make(settings, owner, permission="me")
    faulty = FaultyStorage(settings)

    visible = docs.authorize_upload(principal_of(member), team.id)
    assert visible.scope.tenant_id == owner.tenant_id and visible.scope.subject == "normal"
    made = docs.upload_documents(settings, visible, member.user_id, [item("by-member.pdf", pdf_bytes("m"))], storage=faulty)
    assert made[0]["created_by"] == member.user_id and doc_rows(team.id)[0]["created_by"] == member.user_id
    assert len(tenant_object_keys(owner.tenant_id)) == 1, "the blob lives under the dataset's workspace prefix"
    assert tenant_object_keys(member.tenant_id) == []
    assert refused(lambda: docs.authorize_upload(principal_of(member), private.id)).kind is Kind.NOT_FOUND


# ----------------------------------------------------------------------------- the file helpers on their own


def test_find_candidates_is_scoped_to_the_workspace_and_to_hash_and_size(settings, space, storage):
    owner, dataset = space
    data = pdf_bytes("cand")
    upload(settings, owner, dataset, [item("a.pdf", data)], storage=storage)
    digest = xxhash.xxh64(data).hexdigest()
    from api.db.database import DB

    with DB.connection_context():
        found = file_service.find_candidates(owner.tenant_id, digest, len(data))
        assert len(found) == 1 and re.fullmatch(f"{owner.tenant_id}/{KEY_SHAPE}", found[0].location)
        assert file_service.find_candidates(owner.tenant_id, digest, len(data) + 1) == []
        assert file_service.find_candidates(owner.tenant_id, "0" * 16, len(data)) == []
        assert file_service.find_candidates(uuid.uuid4().hex, digest, len(data)) == [], "another workspace finds nothing"


def test_release_blobs_removes_what_it_is_given_and_forgives_the_absent(settings, space, storage):
    owner, dataset = space
    upload(settings, owner, dataset, [item("a.pdf", pdf_bytes("rel"))], storage=storage)
    (key,) = tenant_object_keys(owner.tenant_id)
    file_service.release_blobs(storage, [key, f"{owner.tenant_id}/{uuid.uuid4().hex}"])
    assert tenant_object_keys(owner.tenant_id) == []
