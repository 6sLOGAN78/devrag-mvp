"""Datasets (knowledge bases): create with a provisioned index, list by visibility, load one (plan 03-14; KB-01..05, KB-08, KB-09, IDX-04, IDX-05).

* ``create_dataset`` validates, resolves the embedding model (an explicit composite id, else the workspace default; nothing is ever chosen
  for the caller, D-18), then under the named lock ``kb-create:{tenant_id}`` checks the name, provisions the vector field in the tenant's
  Elasticsearch index and only then inserts the row, so a failed index leaves no dataset behind. The index step is idempotent, so a row
  insert that fails afterwards leaves nothing that blocks a retry.
* ``list_datasets`` and ``load_visible_dataset`` apply one rule: a dataset of the acting workspace is visible to its creator, and to every
  member when its permission is ``team``. There is no owner or admin override for ``me`` (D-08, D-27). Every miss is the same
  ``NOT_FOUND`` (D-20).

This module imports no web framework. Messages in ``ServiceError`` never hold a host, a key or the caller's input.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import peewee

from api.db.database import DB, DatabaseLock, LockError, LockTimeoutError, transaction
from api.db.models import Knowledgebase
from api.db.services import tenant_model_service
from api.db.services.auth_service import Principal
from api.db.services.service_errors import Kind, ServiceError
from api.db.services.tenant_scope import PERMISSION_ME, PERMISSION_TEAM, ActingScope, dataset_visible, scope_for_tenant
from api.utils import reasons
from common.doc_store.doc_store_base import MAX_VECTOR_SIZE, MIN_VECTOR_SIZE, DocStoreConnection, DocStoreError, InvalidVectorSize, index_name
from common.model_ref import InvalidModelRef, parse_model_ref
from common.settings import Settings, UploadSettings
from rag.utils.es_conn import get_doc_store

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


def _name_taken(tenant_id: str, name: str) -> bool:
    """Case-insensitive by the column collation, and again by an explicit lower-case comparison."""
    same = (Knowledgebase.name == name) | (peewee.fn.LOWER(Knowledgebase.name) == name.lower())
    return Knowledgebase.select(Knowledgebase.id).where((Knowledgebase.tenant_id == tenant_id) & (Knowledgebase.status == _VALID) & same).first() is not None


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
