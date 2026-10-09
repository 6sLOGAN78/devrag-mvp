"""Datasets (knowledge bases): create with a provisioned index, list by visibility, load one (plan 03-14; KB-01..05, KB-08, KB-09, IDX-04, IDX-05).

* ``create_dataset`` validates, resolves the embedding model (an explicit composite id, else the workspace default; nothing is ever chosen
  for the caller, D-18), then under the named lock ``kb-create:{tenant_id}`` checks the name, provisions the vector field in the tenant's
  Elasticsearch index and only then inserts the row, so a failed index leaves no dataset behind. The index step is idempotent, so a row
  insert that fails afterwards leaves nothing that blocks a retry.
* ``list_datasets`` and ``load_visible_dataset`` apply one rule: a dataset of the acting workspace is visible to its creator, and to every
  member when its permission is ``team``. There is no owner or admin override for ``me`` (D-08, D-27). Every miss is the same
  ``NOT_FOUND`` (D-20).

Update and delete (plan 03-18; KB-06..09, D-09, D-10):

* ``update_dataset`` changes name, description, permission, avatar, language, parser and parser configuration for the dataset's creator and the
  workspace owner and admins (``tenant_scope.can_manage_dataset``; decided by the permission subject, so an API token is not elevated). A rename is
  checked against the workspace's other datasets under ``kb-create:{tenant_id}``. The embedding model may change only while the dataset holds no
  documents and no chunks; that is read again under ``kb-upload:{dataset_id}``, the lock uploads take, and the new vector field is provisioned in the
  index before the row changes.
* ``delete_datasets`` authorises every id first (any miss is the one ``NOT_FOUND``, then any id the caller may not manage is ``FORBIDDEN``) and
  changes nothing until then. Per dataset it removes the documents in batches through ``document_service.delete_documents`` (which prunes the index,
  releases blobs only at zero links across the workspace and takes ``kb-upload:{dataset_id}`` itself, so that lock is NOT held around those calls),
  then under that lock removes the dataset's rows from the shared tenant index (``delete_idx``; the index itself is never dropped, decision R-136),
  and in one transaction any document that slipped in, the dataset's other rows and the dataset row. Blobs go after the commit, best effort.
  An upload that raced the delete either landed before the final transaction (and is removed with it) or finds no dataset (``NOT_FOUND``).

This module imports no web framework. Messages in ``ServiceError`` never hold a host, a key or the caller's input.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from collections.abc import Iterator, Mapping, Sequence
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from typing import Any

import peewee

from api.apps.permissions_gen import allowed
from api.db.database import DB, DatabaseLock, LockError, LockTimeoutError, transaction
from api.db.models import Connector2Kb, Document, Knowledgebase, PipelineOperationLog, SyncLogs
from api.db.models.base import current_timestamp_ms, timestamp_to_date
from api.db.services import file_service, tenant_model_service
from api.db.services.auth_service import Principal
from api.db.services.service_errors import Kind, ServiceError
from api.db.services.tenant_scope import PERMISSION_ME, PERMISSION_TEAM, ActingScope, can_manage_dataset, dataset_visible, scope_for_tenant
from api.utils import reasons
from common.doc_store.doc_store_base import MAX_VECTOR_SIZE, MIN_VECTOR_SIZE, DocStoreConnection, DocStoreError, InvalidVectorSize, index_name
from common.model_ref import InvalidModelRef, parse_model_ref
from common.settings import Settings, UploadSettings
from rag.utils.es_conn import get_doc_store
from rag.utils.storage_base import Storage
from rag.utils.storage_factory import get_storage

logger = logging.getLogger(__name__)

# The chunking methods of docs/05-rag-pipeline/chunking.md ("14 specialized chunkers configured per dataset"); `naive` is also dispatched as `general`.
PARSER_IDS: tuple[str, ...] = ("naive", "paper", "book", "laws", "presentation", "table", "qa", "resume", "picture", "manual", "email", "tag", "one", "audio")
DEFAULT_PARSER_ID = PARSER_IDS[0]
DEFAULT_PARSER_CONFIG: dict[str, Any] = {
    "pages": [[1, 1000000]],
    "chunk_token_num": 512,
    "delimiter": "\n!?;。；！？",
    "table_context_size": 0,
    "image_context_size": 0,
    "layout_recognize": True,
    "auto_keywords": 0,
}
PERMISSIONS = (PERMISSION_ME, PERMISSION_TEAM)
DEFAULT_LANGUAGE = "English"
MAX_NAME = 128  # knowledgebase.name is VARCHAR(128)
MAX_LANGUAGE = 32  # knowledgebase.language is VARCHAR(32)
MAX_DESCRIPTION = 2000
MAX_AVATAR = 200_000
MAX_PARSER_CONFIG = 4096
MAX_PAGE_SIZE = 100
LOCK_PREFIX = "kb-create:"
LOCK_TIMEOUT_SECONDS = 10
UPLOAD_LOCK_PREFIX = "kb-upload:"  # uploads, document deletes, embedding changes and dataset deletes of one dataset serialise on this name
UPLOAD_LOCK_TIMEOUT_SECONDS = 30
PERMISSION_AREA = "datasets"
MANAGE_DATASET = "manage_dataset"
EDITABLE_FIELDS = frozenset({"name", "description", "permission", "avatar", "language", "parser_id", "parser_config", "embd_id"})
NEVER_NULL_FIELDS = ("name", "permission", "language", "parser_id", "parser_config", "embd_id")  # description and avatar may be cleared with null
MAX_DELETE_DATASETS = 20
MAX_BATCH_MISSES = 3
DEADLOCK_ATTEMPTS = 3
_MYSQL_DEADLOCK = 1213
_VALID = "1"  # knowledgebase.status: 1 is a live dataset
_ID = re.compile(r"[0-9a-f]{32}")


@dataclass(frozen=True)
class CreateRequest:
    """What a caller may choose. Tenant, creator, counters and ids are never part of it."""

    name: str
    embd_id: str | None = None
    parser_id: str | None = None
    permission: str | None = None
    description: str | None = None
    language: str | None = None
    avatar: str | None = None
    parser_config: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class DatasetRecord:
    id: str
    tenant_id: str
    name: str
    description: str
    avatar: str
    language: str
    embd_id: str
    tenant_embd_id: str
    parser_id: str
    parser_config: dict[str, Any]
    permission: str
    created_by: str
    doc_num: int
    chunk_num: int
    token_num: int
    create_time: int
    update_time: int


@dataclass(frozen=True)
class VisibleDataset:
    dataset: DatasetRecord
    scope: ActingScope


def create_lock_name(tenant_id: str) -> str:
    """``kb-create:`` plus a 32-character tenant id: 42 characters, within the 64 MySQL allows."""
    return f"{LOCK_PREFIX}{tenant_id}"


def upload_lock_name(dataset_id: str) -> str:
    """``kb-upload:`` plus a 32-character dataset id: 42 characters, within the 64 MySQL allows."""
    return f"{UPLOAD_LOCK_PREFIX}{dataset_id}"


def _invalid(message: str) -> ServiceError:
    return ServiceError(Kind.INVALID, reasons.DATASET_INVALID, message)


def _model_unavailable() -> ServiceError:
    return ServiceError(Kind.INVALID, reasons.MODEL_UNAVAILABLE, "that embedding model is not available in this workspace")


def _not_found() -> ServiceError:
    return ServiceError(Kind.NOT_FOUND, reasons.DATASET_NOT_FOUND, "not found")


# ----------------------------------------------------------------------------- validation


@dataclass(frozen=True)
class _Fields:
    name: str
    parser_id: str
    permission: str
    description: str
    language: str
    avatar: str
    parser_config: dict[str, Any]


def _text(value: object, limit: int, label: str, *, default: str = "") -> str:
    if value is None:
        return default
    if not isinstance(value, str) or len(value) > limit:
        raise _invalid(f"{label} is not valid")
    return value


def _validate(req: CreateRequest) -> _Fields:
    if not isinstance(req.name, str):
        raise _invalid("the name is not valid")
    name = req.name.strip()
    if not 1 <= len(name) <= MAX_NAME:
        raise _invalid(f"the name must be 1 to {MAX_NAME} characters")
    parser_id = DEFAULT_PARSER_ID if req.parser_id is None else req.parser_id
    if parser_id not in PARSER_IDS:
        raise _invalid("that parser is not supported")
    permission = PERMISSION_ME if req.permission is None else req.permission
    if permission not in PERMISSIONS:
        raise _invalid("permission must be me or team")
    language = _text(req.language, MAX_LANGUAGE, "the language", default=DEFAULT_LANGUAGE).strip()
    if not language:
        raise _invalid("the language is not valid")
    config: dict[str, Any] = {}
    if req.parser_config is not None:
        if not isinstance(req.parser_config, Mapping):
            raise _invalid("the parser configuration must be an object")
        try:
            encoded = json.dumps(dict(req.parser_config), ensure_ascii=False)
        except (TypeError, ValueError):
            raise _invalid("the parser configuration is not valid") from None
        if len(encoded) > MAX_PARSER_CONFIG:
            raise _invalid(f"the parser configuration is over {MAX_PARSER_CONFIG} characters")
        config = dict(req.parser_config)
    return _Fields(
        name=name,
        parser_id=parser_id,
        permission=permission,
        description=_text(req.description, MAX_DESCRIPTION, "the description"),
        language=language,
        avatar=_text(req.avatar, MAX_AVATAR, "the avatar"),
        parser_config={**DEFAULT_PARSER_CONFIG, **config},
    )


def _embedding_model(tenant_id: str, requested: str | None) -> tenant_model_service.ModelInfo:
    """The embedding model to use: the explicit composite id, else the workspace default. A missing default is an error, not a guess."""
    wanted = requested
    if wanted is None:
        wanted = tenant_model_service.get_defaults(tenant_id).embedding
        if not wanted:
            raise ServiceError(Kind.INVALID, reasons.NO_DEFAULT_EMBEDDING, "choose an embedding model, or ask an owner to set a default one")
    try:
        ref = parse_model_ref(wanted)  # bounds the id at 128 characters, the width of knowledgebase.embd_id
    except InvalidModelRef:
        raise _model_unavailable() from None
    found = tenant_model_service.find_model(tenant_id, ref)
    if found is None or found.model_type != "embedding":
        raise _model_unavailable()
    if not isinstance(found.dimension, int) or not MIN_VECTOR_SIZE <= found.dimension <= MAX_VECTOR_SIZE:
        raise ServiceError(Kind.INVALID, reasons.DIMENSION_UNSUPPORTED, "that embedding model's vector size is not supported")
    return found


# ----------------------------------------------------------------------------- records


def _record(row: Knowledgebase) -> DatasetRecord:
    stored = row.parser_config if isinstance(row.parser_config, dict) else {}
    return DatasetRecord(
        id=row.id,
        tenant_id=row.tenant_id,
        name=row.name,
        description=row.description or "",
        avatar=row.avatar or "",
        language=row.language or DEFAULT_LANGUAGE,
        embd_id=row.embd_id,
        tenant_embd_id=row.tenant_embd_id or "",
        parser_id=row.parser_id,
        parser_config={**DEFAULT_PARSER_CONFIG, **stored},
        permission=row.permission,
        created_by=row.created_by,
        doc_num=int(row.doc_num or 0),
        chunk_num=int(row.chunk_num or 0),
        token_num=int(row.token_num or 0),
        create_time=int(row.create_time or 0),
        update_time=int(row.update_time or 0),
    )


def _name_taken(tenant_id: str, name: str, exclude_id: str | None = None) -> bool:
    """Case-insensitive by the column collation, and again by an explicit lower-case comparison. ``exclude_id`` is the dataset being renamed."""
    same = (Knowledgebase.name == name) | (peewee.fn.LOWER(Knowledgebase.name) == name.lower())
    where = (Knowledgebase.tenant_id == tenant_id) & (Knowledgebase.status == _VALID) & same
    if exclude_id is not None:
        where = where & (Knowledgebase.id != exclude_id)
    return Knowledgebase.select(Knowledgebase.id).where(where).first() is not None


def _provision_index(doc_store: DocStoreConnection, tenant_id: str, dataset_id: str, dimension: int, parser_id: str) -> None:
    try:
        doc_store.create_idx(index_name(tenant_id), dataset_id, dimension, parser_id)
    except InvalidVectorSize:
        raise ServiceError(Kind.INVALID, reasons.DIMENSION_UNSUPPORTED, "that embedding model's vector size is not supported") from None
    except DocStoreError as exc:
        # The class says what went wrong without a host or a body; the adapter's message is already free of both.
        logger.warning("index provisioning failed tenant=%s error=%s", tenant_id, type(exc).__name__)
        raise ServiceError(Kind.UNAVAILABLE, reasons.INDEX_UNAVAILABLE, "the search index is not available, try again shortly") from None


# ----------------------------------------------------------------------------- operations


def create_dataset(settings: Settings, scope: ActingScope, user_id: str, req: CreateRequest, *, doc_store: DocStoreConnection | None = None) -> DatasetRecord:
    """Create a dataset in the acting workspace for ``user_id``. See the module note for the order of the steps."""
    fields = _validate(req)
    tenant_id = scope.tenant_id
    # The model services open and close their own connection scope (a nested scope would close this one), so they run before ours.
    model = _embedding_model(tenant_id, req.embd_id)
    store = doc_store if doc_store is not None else get_doc_store(settings)
    dimension = int(model.dimension or 0)
    dataset_id = uuid.uuid4().hex
    lock = DatabaseLock(create_lock_name(tenant_id), LOCK_TIMEOUT_SECONDS)
    try:
        lock.acquire()
    except (LockTimeoutError, LockError):
        raise ServiceError(Kind.UNAVAILABLE, reasons.BUSY, "another dataset is being created, try again shortly") from None
    try:
        with DB.connection_context():
            if _name_taken(tenant_id, fields.name):
                raise ServiceError(Kind.CONFLICT, reasons.DUPLICATE_NAME, "a dataset with that name already exists")
            _provision_index(store, tenant_id, dataset_id, dimension, fields.parser_id)
            with transaction():
                row = Knowledgebase.create(
                    id=dataset_id,
                    tenant_id=tenant_id,
                    name=fields.name,
                    language=fields.language,
                    description=fields.description,
                    avatar=fields.avatar or None,
                    embd_id=model.composite,
                    tenant_embd_id=model.id,
                    parser_id=fields.parser_id,
                    parser_config=fields.parser_config,
                    permission=fields.permission,
                    created_by=user_id,
                    status=_VALID,
                    doc_num=0,
                    token_num=0,
                    chunk_num=0,
                )
            record = _record(row)
    finally:
        lock.release()
    logger.info("dataset created tenant=%s dataset=%s dimension=%d", tenant_id, dataset_id, dimension)
    return record


def _escape_like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def list_datasets(scope: ActingScope, user_id: str, *, page: int, page_size: int, keywords: str | None) -> tuple[list[DatasetRecord], int]:
    """One page of the datasets the user may see in the workspace, newest first, with the total number of matches."""
    page = max(1, int(page))
    page_size = min(max(1, int(page_size)), MAX_PAGE_SIZE)
    visible = (Knowledgebase.tenant_id == scope.tenant_id) & (Knowledgebase.status == _VALID) & ((Knowledgebase.created_by == user_id) | (Knowledgebase.permission == PERMISSION_TEAM))
    if keywords:
        pattern = f"%{_escape_like(keywords)}%"
        visible = visible & peewee.NodeList((Knowledgebase.name, peewee.SQL("LIKE"), pattern, peewee.SQL("ESCAPE '\\\\'")))
    with DB.connection_context():
        total = Knowledgebase.select().where(visible).count()
        rows = Knowledgebase.select().where(visible).order_by(Knowledgebase.update_time.desc(), Knowledgebase.id).paginate(page, page_size)
        return [_record(row) for row in rows], total


def load_visible_dataset(principal: Principal, dataset_id: str) -> VisibleDataset:
    """The dataset and the caller's scope in its workspace, or the one ``NOT_FOUND`` for an absent, foreign or invisible dataset."""
    if not isinstance(dataset_id, str) or _ID.fullmatch(dataset_id) is None:
        raise _not_found()
    with DB.connection_context():
        row = Knowledgebase.get_or_none((Knowledgebase.id == dataset_id) & (Knowledgebase.status == _VALID))
    if row is None:
        raise _not_found()
    scope = scope_for_tenant(principal, row.tenant_id)
    if scope is None or not dataset_visible(row.created_by, row.permission, principal.user_id, True):
        raise _not_found()
    return VisibleDataset(_record(row), scope)


def embedding_dimensions(tenant_id: str) -> dict[str, int]:
    """Recorded vector size of each embedding model of the workspace, keyed by composite id, for the ``embedding_dimension`` of a response."""
    return {m.composite: m.dimension for m in tenant_model_service.list_models(tenant_id, "embedding") if isinstance(m.dimension, int)}


def dataset_dto(record: DatasetRecord, *, embedding_dimension: int | None, include_limits: UploadSettings | None = None) -> dict[str, Any]:
    """The response body for a dataset. Keys are listed here, so a column added to the table never reaches a client unreviewed."""
    out: dict[str, Any] = {
        "id": record.id,
        "name": record.name,
        "description": record.description,
        "avatar": record.avatar,
        "language": record.language,
        "permission": record.permission,
        "embd_id": record.embd_id,
        "embedding_dimension": embedding_dimension,
        "parser_id": record.parser_id,
        "parser_config": record.parser_config,
        "doc_num": record.doc_num,
        "chunk_num": record.chunk_num,
        "token_num": record.token_num,
        "tenant_id": record.tenant_id,
        "created_by": record.created_by,
        "create_time": record.create_time,
        "update_time": record.update_time,
    }
    if include_limits is not None:
        out["upload_limits"] = {
            "max_file_bytes": include_limits.max_file_bytes,
            "max_files_per_request": include_limits.max_files_per_request,
            "max_documents": include_limits.max_documents_per_dataset,
            "allowed_extensions": list(include_limits.allowed_extensions),
        }
    return out


def view_of(record: DatasetRecord, *, include_limits: UploadSettings | None = None, dimensions: Mapping[str, int] | None = None) -> dict[str, Any]:
    """``dataset_dto`` with the recorded vector size of the dataset's embedding model looked up (or taken from ``dimensions``)."""
    known = embedding_dimensions(record.tenant_id) if dimensions is None else dimensions
    return dataset_dto(record, embedding_dimension=known.get(record.embd_id), include_limits=include_limits)


def create_view(settings: Settings, scope: ActingScope, user_id: str, req: CreateRequest) -> dict[str, Any]:
    return view_of(create_dataset(settings, scope, user_id, req))


def list_view(scope: ActingScope, user_id: str, *, page: int, page_size: int, keywords: str | None) -> dict[str, Any]:
    records, total = list_datasets(scope, user_id, page=page, page_size=page_size, keywords=keywords)
    dimensions = embedding_dimensions(scope.tenant_id)
    return {"items": [view_of(r, dimensions=dimensions) for r in records], "total": total}


def detail_view(principal: Principal, dataset_id: str, upload: UploadSettings) -> dict[str, Any]:
    found = load_visible_dataset(principal, dataset_id)
    return view_of(found.dataset, include_limits=upload)


# ----------------------------------------------------------------------------- update


def _forbidden() -> ServiceError:
    return ServiceError(Kind.FORBIDDEN, reasons.FORBIDDEN, "forbidden")


def _fields_invalid(message: str) -> ServiceError:
    return ServiceError(Kind.INVALID, reasons.FIELDS_INVALID, message)


def _require_manage(visible: VisibleDataset, user_id: str) -> None:
    """The creator, or an owner or admin session, may edit or delete (D-09). The permission subject decides, never an inherited role."""
    scope = visible.scope
    if not allowed(scope.subject, PERMISSION_AREA, MANAGE_DATASET) or not can_manage_dataset(visible.dataset.created_by, user_id, scope.subject):
        raise _forbidden()


@contextmanager
def _named_lock(name: str, timeout: int, busy_message: str) -> Iterator[None]:
    lock = DatabaseLock(name, timeout)
    try:
        lock.acquire()
    except (LockTimeoutError, LockError):
        raise ServiceError(Kind.UNAVAILABLE, reasons.BUSY, busy_message) from None
    try:
        yield
    finally:
        try:
            lock.release()
        except LockError:
            logger.warning("lock was not held at release name=%s", name)


def _validated_changes(dataset: DatasetRecord, changes: Mapping[str, Any]) -> _Fields:
    """The values after the change, validated by the create rules. Only the keys named in ``changes`` differ from the stored dataset."""
    if not isinstance(changes, Mapping) or not changes:
        raise _fields_invalid("send at least one field to change")
    if not set(changes) <= EDITABLE_FIELDS:
        raise _fields_invalid("some of those fields cannot be changed")
    if any(key in changes and changes[key] is None for key in NEVER_NULL_FIELDS):
        raise _invalid("a field that cannot be cleared was sent empty")
    config: Mapping[str, Any] | None = None
    if "parser_config" in changes:
        sent = changes["parser_config"]
        if not isinstance(sent, Mapping):
            raise _invalid("the parser configuration must be an object")
        config = {**dataset.parser_config, **dict(sent)}  # a partial update keeps what was stored
    return _validate(
        CreateRequest(
            name=changes.get("name", dataset.name),
            parser_id=changes.get("parser_id", dataset.parser_id),
            permission=changes.get("permission", dataset.permission),
            description=changes["description"] if "description" in changes else dataset.description,
            language=changes.get("language", dataset.language),
            avatar=changes["avatar"] if "avatar" in changes else dataset.avatar,
            parser_config=config,
        )
    )


def update_dataset(settings: Settings, visible: VisibleDataset, user_id: str, changes: Mapping[str, Any], *, doc_store: DocStoreConnection | None = None) -> DatasetRecord:
    """Apply ``changes`` to the dataset and return it. See the module note for the rules; nothing is written unless every check passes."""
    dataset, tenant_id = visible.dataset, visible.scope.tenant_id
    _require_manage(visible, user_id)
    fields = _validated_changes(dataset, changes)
    renamed = "name" in changes and fields.name != dataset.name
    wanted = changes.get("embd_id") if "embd_id" in changes else None
    swap = "embd_id" in changes and wanted != dataset.embd_id
    model = None
    if swap:
        if not isinstance(wanted, str):
            raise _model_unavailable()
        model = _embedding_model(tenant_id, wanted)  # before our connection scope: the model services open and close their own
    store = (doc_store if doc_store is not None else get_doc_store(settings)) if swap else None

    values: dict[str, Any] = {}
    for key in ("name", "description", "permission", "language", "parser_id"):
        if key in changes:
            values[key] = getattr(fields, key)
    if "avatar" in changes:
        values["avatar"] = fields.avatar or None
    if "parser_config" in changes:
        values["parser_config"] = fields.parser_config

    with ExitStack() as locks:
        if renamed:
            locks.enter_context(_named_lock(create_lock_name(tenant_id), LOCK_TIMEOUT_SECONDS, "another dataset is being changed, try again shortly"))
        if swap:
            locks.enter_context(_named_lock(upload_lock_name(dataset.id), UPLOAD_LOCK_TIMEOUT_SECONDS, "an upload to this dataset is running, try again shortly"))
        with DB.connection_context():
            current = Knowledgebase.get_or_none((Knowledgebase.id == dataset.id) & (Knowledgebase.status == _VALID))
            if current is None:
                raise _not_found()
            if renamed and _name_taken(tenant_id, fields.name, dataset.id):
                raise ServiceError(Kind.CONFLICT, reasons.DUPLICATE_NAME, "a dataset with that name already exists")
            if swap and model is not None and store is not None:
                if int(current.doc_num or 0) > 0 or int(current.chunk_num or 0) > 0:
                    raise ServiceError(Kind.CONFLICT, reasons.EMBEDDING_LOCKED, "the embedding model cannot change once the dataset has documents")
                _provision_index(store, tenant_id, dataset.id, int(model.dimension or 0), values.get("parser_id", current.parser_id))
                values["embd_id"] = model.composite
                values["tenant_embd_id"] = model.id
            now = current_timestamp_ms()
            with transaction():
                Knowledgebase.update(update_time=now, update_date=timestamp_to_date(now), **values).where(Knowledgebase.id == dataset.id).execute()
            record = _record(Knowledgebase.get_by_id(dataset.id))
    logger.info("dataset updated tenant=%s dataset=%s fields=%s", tenant_id, dataset.id, ",".join(sorted(changes)))
    return record


def update_view(settings: Settings, visible: VisibleDataset, user_id: str, changes: Mapping[str, Any]) -> dict[str, Any]:
    return view_of(update_dataset(settings, visible, user_id, changes))


# ----------------------------------------------------------------------------- delete


def _clean_dataset_ids(ids: object) -> list[str]:
    """The unique, well-formed ids of a delete request in request order: 1 to 20 of them, each 32 lowercase hex characters."""
    if not isinstance(ids, (list, tuple)) or not 1 <= len(ids) <= MAX_DELETE_DATASETS:
        raise ServiceError(Kind.INVALID, reasons.IDS_INVALID, f"send between 1 and {MAX_DELETE_DATASETS} dataset ids")
    clean: list[str] = []
    for value in ids:
        if not isinstance(value, str) or _ID.fullmatch(value) is None:
            raise ServiceError(Kind.INVALID, reasons.IDS_INVALID, "a dataset id is not valid")
        if value not in clean:
            clean.append(value)
    return clean


def delete_datasets(
    settings: Settings,
    principal: Principal,
    ids: Sequence[str],
    *,
    tenant_id: str | None = None,
    storage: Storage | None = None,
    doc_store: DocStoreConnection | None = None,
) -> list[str]:
    """Permanently delete the datasets ``ids`` and return their ids in request order. See the module note for the order of the steps.

    Authorisation covers every id before anything changes. After that the datasets are removed one by one; a failure part-way raises with
    ``data={"deleted": [ids finished so far]}`` and the dataset that failed is intact apart from the documents already removed (the call can be repeated).
    ``tenant_id`` (optional) names the workspace the caller believes the datasets are in; a dataset of another workspace is the one ``NOT_FOUND``.
    """
    wanted = _clean_dataset_ids(ids)
    found = [load_visible_dataset(principal, dataset_id) for dataset_id in wanted]  # any absent or invisible id is the one NOT_FOUND, before any 403
    if tenant_id is not None and any(item.scope.tenant_id != tenant_id for item in found):
        raise _not_found()
    for item in found:
        _require_manage(item, principal.user_id)

    blobs = storage if storage is not None else get_storage(settings)
    engine = doc_store if doc_store is not None else get_doc_store(settings)
    done: list[str] = []
    for item in found:
        try:
            _delete_one(settings, item, principal.user_id, blobs, engine)
        except ServiceError as exc:
            exc.data = {**(exc.data or {}), "deleted": list(done)}
            raise
        done.append(item.dataset.id)
    return done


def _delete_one(settings: Settings, visible: VisibleDataset, user_id: str, blobs: Storage, engine: DocStoreConnection) -> None:
    # document_service imports this module, so the dependency in the other direction is taken when it is needed.
    from api.db.services import document_service

    dataset, tenant_id = visible.dataset, visible.scope.tenant_id
    removed, misses = 0, 0
    while True:  # no lock is held here: delete_documents takes kb-upload:{dataset_id} for each batch itself
        with DB.connection_context():
            batch = [row.id for row in Document.select(Document.id).where(Document.kb_id == dataset.id).order_by(Document.id).limit(document_service.MAX_DELETE_IDS)]
        if not batch:
            break
        try:
            removed += document_service.delete_documents(settings, visible, user_id, batch, storage=blobs, doc_store=engine)
            misses = 0
        except ServiceError as exc:
            if exc.kind is Kind.NOT_FOUND and misses < MAX_BATCH_MISSES:  # another delete took some of them: look again
                misses += 1
                continue
            raise

    with _named_lock(upload_lock_name(dataset.id), UPLOAD_LOCK_TIMEOUT_SECONDS, "another change to this dataset is running, try again shortly"):
        try:
            engine.delete_idx(index_name(tenant_id), dataset.id)  # this dataset's rows only: the index is shared by the whole workspace (R-136)
        except DocStoreError as exc:
            logger.warning("dataset delete could not prune the index tenant=%s dataset=%s error=%s", tenant_id, dataset.id, type(exc).__name__)
            raise ServiceError(Kind.UNAVAILABLE, reasons.INDEX_UNAVAILABLE, "the search index is not available, try again shortly") from None
        with DB.connection_context():
            freed, late = _drop_rows(dataset.id)
    file_service.release_blobs(blobs, freed, "dataset delete")  # after the commit: a failure leaves an orphan blob, never a document without one
    logger.info("dataset deleted tenant=%s dataset=%s documents=%d", tenant_id, dataset.id, removed + late)


def _drop_rows(dataset_id: str) -> tuple[list[str], int]:
    """One transaction under the dataset lock: any document left (an upload that landed meanwhile), the dataset's other rows and the dataset itself.

    Returns the blob keys nothing references any more and the number of documents removed here. Retried when MySQL picks it as a deadlock victim.
    """
    for attempt in range(1, DEADLOCK_ATTEMPTS + 1):
        try:
            with transaction():
                row = Knowledgebase.select(Knowledgebase.id).where((Knowledgebase.id == dataset_id) & (Knowledgebase.status == _VALID)).for_update().first()
                if row is None:  # a concurrent delete finished first
                    raise _not_found()
                left = [doc.id for doc in Document.select(Document.id).where(Document.kb_id == dataset_id).order_by(Document.id)]
                freed = file_service.release_files(left)
                for related in (PipelineOperationLog, Connector2Kb, SyncLogs):
                    related.delete().where(related.kb_id == dataset_id).execute()
                Knowledgebase.delete().where(Knowledgebase.id == dataset_id).execute()
            return freed, len(left)
        except peewee.OperationalError as exc:
            if exc.args and exc.args[0] == _MYSQL_DEADLOCK and attempt < DEADLOCK_ATTEMPTS:
                logger.warning("dataset delete transaction was a deadlock victim dataset=%s attempt=%d", dataset_id, attempt)
                continue
            raise
    raise AssertionError("unreachable: the last attempt returns or raises")
