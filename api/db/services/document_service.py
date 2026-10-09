"""Document upload: authorise, validate everything, hash, dedupe, rename, store and record in one step (plan 03-16; DOC-01..07, DOC-16, STOR-11, SEC-06, TEN-13).

Order of ``upload_documents`` (Pattern 9; Pitfalls 1 to 3):

1. ``authorize_upload`` runs first and alone: the dataset must be visible to the caller (one ``NOT_FOUND`` for absent, foreign and private-to-others
   datasets, D-20) and the caller's subject must hold ``datasets.manage_document`` (``FORBIDDEN``). Any member may upload into a ``team`` dataset (D-09).
2. Every file is validated and hashed before anything is written: request counts, name, extension, declared type, magic bytes, size, dataset
   capacity, then the optional per-document parser. One failure rejects the whole request and storage and tables stay unchanged.
3. Under the named lock ``kb-upload:{dataset_id}`` (42 characters) the dataset's counter and document names are read again, final names are
   chosen (``name(1).ext`` when taken, also against earlier files of the same request, D-14), then one transaction stores or reuses each blob
   (a reused blob is first compared byte for byte, see ``file_service``), inserts ``file``, ``document`` and ``file2document`` rows and raises
   ``knowledgebase.doc_num``.
4. If anything fails after a blob was written, the blobs created by this request (never reused ones) are removed and the transaction is rolled back.

Listing and deletion (plan 03-17; DOC-08, DOC-14, DOC-15):

* ``list_documents`` / ``list_view``: one page of a visible dataset's documents, newest first, optional escaped ``LIKE`` on the name.
* ``delete_documents`` is all-or-nothing. Every id must belong to the dataset (one ``NOT_FOUND`` otherwise) and the caller must be allowed to
  remove each (``FORBIDDEN``) before anything changes. The index is pruned first (``DocStoreConnection.delete`` by ``doc_id``; an unavailable
  index is ``UNAVAILABLE`` ``index_unavailable`` and nothing else changes). Then, under the same dataset lock uploads use and in one transaction,
  the documents are locked again (a concurrent delete of the same ids loses with ``NOT_FOUND``), their tasks, links and rows go, the dataset's
  counters drop, and ``file_service.release_files`` frees a ``file`` row only when no link in the workspace still points to it. The freed blobs
  are removed after the commit, best effort. A caller with an API token is not given its owner's role: only the uploader or the dataset's
  creator may remove (``tenant_scope.can_remove_document`` is called with the permission subject, D-26, Pitfall 6).

The module imports no web framework; files arrive as small readable streams. Storage drivers are blocking: the caller runs this in the storage
executor with an explicit deadline.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import peewee

from api.apps.permissions_gen import allowed
from api.db.database import DB, DatabaseLock, LockError, LockTimeoutError, transaction
from api.db.models import Document, File, File2Document, Knowledgebase
from api.db.models.base import current_timestamp_ms, timestamp_to_date
from api.db.services import file_service
from api.db.services.auth_service import Principal
from api.db.services.knowledgebase_service import MAX_PARSER_CONFIG, PARSER_IDS, DatasetRecord, VisibleDataset, load_visible_dataset
from api.db.services.service_errors import Kind, ServiceError
from api.db.services.tenant_scope import can_remove_document
from api.db.services.upload_rules import (
    HEAD_BYTES,
    SeekableReader,
    ValidatedFile,
    auto_rename_batch,
    check_batch,
    check_capacity,
    hash_and_measure,
    validate_file,
)
from api.utils import reasons
from common.doc_store.doc_store_base import DocStoreConnection, DocStoreError, index_name
from common.settings import Settings, UploadSettings
from rag.utils.es_conn import get_doc_store
from rag.utils.storage_base import Storage, StorageError
from rag.utils.storage_factory import get_storage

logger = logging.getLogger(__name__)

AREA = "datasets"
MANAGE_DOCUMENT = "manage_document"
LOCK_PREFIX = "kb-upload:"
LOCK_TIMEOUT_SECONDS = 30
_VALID = "1"  # knowledgebase.status: 1 is a live dataset
_SOURCE_LOCAL = "local"
_FILE_SOURCE = "knowledgebase"
_NOT_STARTED = "0"
MAX_PAGE_SIZE = 100
MAX_KEYWORDS = 128
MAX_DELETE_IDS = 100
DEADLOCK_ATTEMPTS = 3
_MYSQL_DEADLOCK = 1213
_ID = re.compile(r"[0-9a-f]{32}")


@dataclass
class UploadItem:
    """One uploaded file as the service sees it: the client's name and declared type, and a readable, seekable stream."""

    name: str
    mime: str
    stream: SeekableReader


def upload_lock_name(dataset_id: str) -> str:
    """``kb-upload:`` plus a 32-character dataset id: 42 characters, within the 64 MySQL allows."""
    return f"{LOCK_PREFIX}{dataset_id}"


def authorize_upload(principal: Principal, dataset_id: str) -> VisibleDataset:
    """The dataset the caller may upload into. ``NOT_FOUND`` when it is not visible; ``FORBIDDEN`` when the caller's subject lacks the permission.

    Visibility is decided first so a caller who cannot see a dataset learns nothing about it, not even that a permission is missing.
    """
    visible = load_visible_dataset(principal, dataset_id)
    if not allowed(visible.scope.subject, AREA, MANAGE_DOCUMENT):
        raise ServiceError(Kind.FORBIDDEN, reasons.FORBIDDEN, "forbidden")
    return visible


def authorize_removal(principal: Principal, dataset_id: str) -> VisibleDataset:
    """The dataset the caller may remove documents from: the same visibility and ``datasets.manage_document`` rule as an upload.

    Which documents the caller may remove is decided per document by ``delete_documents``.
    """
    return authorize_upload(principal, dataset_id)


def _parser_invalid(message: str) -> ServiceError:
    return ServiceError(Kind.INVALID, reasons.PARSER_INVALID, message)


def _parser_for(dataset: DatasetRecord, parser_id: object, parser_config: object) -> tuple[str, dict[str, Any]]:
    """The parser a document gets: the dataset's, or the request's override (configuration merged over the dataset's)."""
    if parser_id is not None and (not isinstance(parser_id, str) or parser_id not in PARSER_IDS):
        raise _parser_invalid("that parser is not supported")
    config = dict(dataset.parser_config)
    if parser_config is not None:
        if not isinstance(parser_config, Mapping):
            raise _parser_invalid("the parser configuration must be an object")
        try:
            encoded = json.dumps(dict(parser_config), ensure_ascii=False)
        except (TypeError, ValueError):
            raise _parser_invalid("the parser configuration is not valid") from None
        if len(encoded) > MAX_PARSER_CONFIG:
            raise _parser_invalid(f"the parser configuration is over {MAX_PARSER_CONFIG} characters")
        config = {**config, **dict(parser_config)}
    return (dataset.parser_id if parser_id is None else parser_id), config


def _read_head(stream: SeekableReader) -> bytes:
    parts: list[bytes] = []
    remaining = HEAD_BYTES
    while remaining > 0:
        piece = stream.read(remaining)
        if not piece:
            break
        parts.append(piece)
        remaining -= len(piece)
    return b"".join(parts)


def _validate(settings: Settings, items: Sequence[UploadItem]) -> list[ValidatedFile]:
    """Per-file rules on the measured size and the first bytes. Nothing is hashed yet, so a bad type fails before 100 MB are read."""
    checked: list[ValidatedFile] = []
    for item in items:
        size = item.stream.seek(0, 2)
        item.stream.seek(0)
        head = _read_head(item.stream)
        item.stream.seek(0)
        checked.append(validate_file(item.name or "", item.mime or "", head, size, settings.upload))
    return checked


def document_dto(doc: Document) -> dict[str, Any]:
    """The response body for a document. Keys are listed here, so a column added to the table never reaches a client unreviewed."""
    return {
        "id": doc.id,
        "name": doc.name,
        "size": int(doc.size or 0),
        "type": doc.type,
        "suffix": doc.suffix,
        "run": doc.run,
        "progress": float(doc.progress or 0.0),
        "dataset_id": doc.kb_id,
        "created_by": doc.created_by,
        "parser_id": doc.parser_id,
        "chunk_num": int(doc.chunk_num or 0),
        "token_num": int(doc.token_num or 0),
        "create_time": int(doc.create_time or 0),
        "update_time": int(doc.update_time or 0),
    }


def upload_documents(
    settings: Settings,
    visible: VisibleDataset,
    user_id: str,
    items: Sequence[UploadItem],
    *,
    parser_id: str | None = None,
    parser_config: Mapping[str, Any] | None = None,
    storage: Storage | None = None,
    lock_timeout: int = LOCK_TIMEOUT_SECONDS,
) -> list[dict[str, Any]]:
    """Store ``items`` in the dataset and return one document body per item, in request order. See the module note for the steps."""
    dataset = visible.dataset
    limits = settings.upload
    check_batch(len(items), limits)
    validated = _validate(settings, items)
    check_capacity(dataset.doc_num, len(items), limits)
    hashes = [hash_and_measure(item.stream)[0] for item in items]
    final_parser, final_config = _parser_for(dataset, parser_id, parser_config)
    blobs = storage if storage is not None else get_storage(settings)

    lock = DatabaseLock(upload_lock_name(dataset.id), lock_timeout)
    try:
        lock.acquire()
    except (LockTimeoutError, LockError):
        raise ServiceError(Kind.UNAVAILABLE, reasons.BUSY, "another upload to this dataset is running, try again shortly") from None
    try:
        with DB.connection_context():
            return _store(blobs, limits, visible, user_id, items, validated, hashes, final_parser, final_config)
    finally:
        try:
            lock.release()
        except LockError:
            logger.warning("upload lock was not held at release dataset=%s", dataset.id)


def _store(
    storage: Storage,
    limits: UploadSettings,
    visible: VisibleDataset,
    user_id: str,
    items: Sequence[UploadItem],
    validated: Sequence[ValidatedFile],
    hashes: Sequence[str],
    parser_id: str,
    parser_config: dict[str, Any],
) -> list[dict[str, Any]]:
    """Steps 3 and 4 of the module note, under the dataset's upload lock with an open connection."""
    dataset, tenant_id = visible.dataset, visible.scope.tenant_id
    current = Knowledgebase.select(Knowledgebase.doc_num).where((Knowledgebase.id == dataset.id) & (Knowledgebase.status == _VALID)).first()
    if current is None:
        raise ServiceError(Kind.NOT_FOUND, reasons.DATASET_NOT_FOUND, "not found")
    check_capacity(int(current.doc_num or 0), len(items), limits)
    taken = {name for (name,) in Document.select(Document.name).where(Document.kb_id == dataset.id).tuples() if name}
    names = auto_rename_batch([v.name for v in validated], taken)

    created_keys: list[str] = []
    reused = 0
    made: list[dict[str, Any]] = []
    try:
        with transaction():
            for item, checked, digest, name in zip(items, validated, hashes, names, strict=True):
                file_id, location, created = file_service.reuse_or_store(storage, tenant_id, item.stream, digest, checked.size, created_keys)
                if created:
                    file_id = uuid.uuid4().hex
                    File.create(
                        id=file_id,
                        parent_id=dataset.id,
                        tenant_id=tenant_id,
                        created_by=user_id,
                        name=name,
                        location=location,
                        size=checked.size,
                        type=checked.file_type,
                        source_type=_FILE_SOURCE,
                    )
                else:
                    reused += 1
                doc = Document.create(
                    id=uuid.uuid4().hex,
                    kb_id=dataset.id,
                    parser_id=parser_id,
                    parser_config=parser_config,
                    source_type=_SOURCE_LOCAL,
                    type=checked.file_type,
                    created_by=user_id,
                    name=name,
                    location=location,
                    size=checked.size,
                    suffix=checked.extension,
                    content_hash=digest,
                    run=_NOT_STARTED,
                    progress=0.0,
                    token_num=0,
                    chunk_num=0,
                )
                File2Document.create(id=uuid.uuid4().hex, file_id=file_id, document_id=doc.id)
                made.append(document_dto(doc))
            now = current_timestamp_ms()
            Knowledgebase.update(doc_num=Knowledgebase.doc_num + len(items), update_time=now, update_date=timestamp_to_date(now)).where(Knowledgebase.id == dataset.id).execute()
    except StorageError:
        file_service.release_blobs(storage, created_keys)
        logger.warning("upload storage failed tenant=%s dataset=%s", tenant_id, dataset.id)
        raise ServiceError(Kind.UNAVAILABLE, reasons.STORAGE_UNAVAILABLE, "file storage is not available, try again shortly") from None
    except Exception:
        file_service.release_blobs(storage, created_keys)
        raise
    logger.info("upload tenant=%s dataset=%s files=%d reused=%d created=%d", tenant_id, dataset.id, len(items), reused, len(created_keys))
    return made


# ----------------------------------------------------------------------------- list


def _escape_like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _query_invalid(message: str) -> ServiceError:
    return ServiceError(Kind.INVALID, reasons.QUERY_INVALID, message)


def list_documents(visible: VisibleDataset, *, page: int, page_size: int, keywords: str | None) -> tuple[list[dict[str, Any]], int]:
    """One page of the dataset's documents, newest first, and the number of matches.

    ``page`` below 1 is 1 and ``page_size`` is held to 1..100 (the handler refuses out-of-range values; the service never lets a caller read more).
    ``keywords`` (at most 128 characters) is a case-insensitive substring of the name; ``%`` and ``_`` in it are literal.
    """
    if keywords is not None and (not isinstance(keywords, str) or len(keywords) > MAX_KEYWORDS):
        raise _query_invalid(f"keywords must be at most {MAX_KEYWORDS} characters")
    page = max(1, int(page))
    page_size = min(max(1, int(page_size)), MAX_PAGE_SIZE)
    where = Document.kb_id == visible.dataset.id
    if keywords:
        pattern = f"%{_escape_like(keywords)}%"
        where = where & peewee.NodeList((Document.name, peewee.SQL("LIKE"), pattern, peewee.SQL("ESCAPE '\\\\'")))
    columns = (
        Document.id, Document.name, Document.size, Document.type, Document.suffix, Document.run, Document.progress, Document.kb_id,
        Document.created_by, Document.parser_id, Document.chunk_num, Document.token_num, Document.create_time, Document.update_time,
    )  # fmt: skip  # not the thumbnail or the progress message: they can be large and are never returned
    with DB.connection_context():
        total = Document.select().where(where).count()
        rows = Document.select(*columns).where(where).order_by(Document.create_time.desc(), Document.id).paginate(page, page_size)
        return [document_dto(row) for row in rows], total


def list_view(principal: Principal, dataset_id: str, *, page: int, page_size: int, keywords: str | None) -> dict[str, Any]:
    """``{"items": [...], "total": n}`` for a dataset the caller can see; the one ``NOT_FOUND`` otherwise."""
    visible = load_visible_dataset(principal, dataset_id)
    items, total = list_documents(visible, page=page, page_size=page_size, keywords=keywords)
    return {"items": items, "total": total}


# ----------------------------------------------------------------------------- delete


def _clean_ids(ids: object) -> list[str]:
    """The unique, well-formed ids of a delete request in request order: 1 to 100 of them, each 32 lowercase hex characters."""
    if not isinstance(ids, (list, tuple)) or not 1 <= len(ids) <= MAX_DELETE_IDS:
        raise ServiceError(Kind.INVALID, reasons.IDS_INVALID, f"send between 1 and {MAX_DELETE_IDS} document ids")
    clean: list[str] = []
    for value in ids:
        if not isinstance(value, str) or _ID.fullmatch(value) is None:
            raise ServiceError(Kind.INVALID, reasons.IDS_INVALID, "a document id is not valid")
        if value not in clean:
            clean.append(value)
    return clean


def _not_found() -> ServiceError:
    return ServiceError(Kind.NOT_FOUND, reasons.DATASET_NOT_FOUND, "not found")


def delete_documents(
    settings: Settings,
    visible: VisibleDataset,
    user_id: str,
    ids: Sequence[str],
    *,
    storage: Storage | None = None,
    doc_store: DocStoreConnection | None = None,
) -> int:
    """Remove the documents ``ids`` of the dataset, all or none, and return how many. See the module note for the order of the steps."""
    wanted = _clean_ids(ids)
    dataset, scope = visible.dataset, visible.scope
    with DB.connection_context():
        found = list(Document.select(Document.id, Document.created_by).where(Document.id.in_(wanted) & (Document.kb_id == dataset.id)))
    if len(found) != len(wanted):
        raise _not_found()
    for doc in found:
        if not can_remove_document(doc.created_by, dataset.created_by, user_id, scope.subject):
            raise ServiceError(Kind.FORBIDDEN, reasons.FORBIDDEN, "forbidden")

    engine = doc_store if doc_store is not None else get_doc_store(settings)
    try:
        engine.delete({"doc_id": wanted}, index_name(scope.tenant_id), dataset.id)
    except DocStoreError as exc:
        logger.warning("document delete could not prune the index tenant=%s dataset=%s error=%s", scope.tenant_id, dataset.id, type(exc).__name__)
        raise ServiceError(Kind.UNAVAILABLE, reasons.INDEX_UNAVAILABLE, "the search index is not available, try again shortly") from None

    blobs = storage if storage is not None else get_storage(settings)
    lock = DatabaseLock(upload_lock_name(dataset.id), LOCK_TIMEOUT_SECONDS)
    try:
        lock.acquire()
    except (LockTimeoutError, LockError):
        raise ServiceError(Kind.UNAVAILABLE, reasons.BUSY, "another change to this dataset is running, try again shortly") from None
    try:
        with DB.connection_context():
            freed = _remove_rows(dataset.id, wanted)
    finally:
        try:
            lock.release()
        except LockError:
            logger.warning("delete lock was not held at release dataset=%s", dataset.id)
    file_service.release_blobs(blobs, freed, "delete")  # after the commit: a failure here leaves an orphan blob, never a document without one
    logger.info("delete tenant=%s dataset=%s documents=%d blobs=%d", scope.tenant_id, dataset.id, len(wanted), len(freed))
    return len(wanted)


def _remove_rows(dataset_id: str, wanted: list[str]) -> list[str]:
    """One transaction: lock the documents, release their files, lower the dataset's counters. Retried when MySQL picks it as a deadlock victim."""
    for attempt in range(1, DEADLOCK_ATTEMPTS + 1):
        try:
            with transaction():
                # By primary key only, so no range of the dataset is locked; the dataset is checked on the rows that come back.
                locked = list(Document.select(Document.id, Document.kb_id, Document.chunk_num, Document.token_num).where(Document.id.in_(wanted)).order_by(Document.id).for_update())
                if len(locked) != len(wanted) or any(doc.kb_id != dataset_id for doc in locked):
                    raise _not_found()  # a concurrent delete got there first: nothing is changed
                freed = file_service.release_files(wanted)
                chunks = sum(int(doc.chunk_num or 0) for doc in locked)
                tokens = sum(int(doc.token_num or 0) for doc in locked)
                now = current_timestamp_ms()
                Knowledgebase.update(
                    doc_num=peewee.fn.GREATEST(Knowledgebase.doc_num - len(wanted), 0),
                    chunk_num=peewee.fn.GREATEST(Knowledgebase.chunk_num - chunks, 0),
                    token_num=peewee.fn.GREATEST(Knowledgebase.token_num - tokens, 0),
                    update_time=now,
                    update_date=timestamp_to_date(now),
                ).where(Knowledgebase.id == dataset_id).execute()
            return freed
        except peewee.OperationalError as exc:
            if exc.args and exc.args[0] == _MYSQL_DEADLOCK and attempt < DEADLOCK_ATTEMPTS:
                logger.warning("delete transaction was a deadlock victim dataset=%s attempt=%d", dataset_id, attempt)
                continue
            raise
    raise AssertionError("unreachable: the last attempt returns or raises")
