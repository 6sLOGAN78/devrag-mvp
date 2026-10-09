"""Dataset routes: create, list, open (plan 03-14; KB-01..05, KB-08, KB-09, TEN-13, TEN-16, SEC-02, D-08, D-18, D-19, D-20, D-26, D-27).

Three thin handlers in the order the other workspace-scoped routes use: resolve the acting workspace (a foreign or malformed one is the
single not-found body), check the permission matrix, run the blocking service call in a bounded executor, map ``ServiceError`` to the
envelope. Creating needs ``datasets.manage_dataset``; any member (and an API token for its own workspace) may list. Opening a dataset
derives the workspace from the dataset itself, so an absent id, another workspace's id and another member's private dataset all give the
same 404 body (D-20, D-27). The request model refuses every field it does not name, so tenant, creator, counters and ids cannot be assigned.
"""
from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from quart import Blueprint, Response, current_app, g, request
from quart_schema import document_response, validate_request

from api.apps.handler_support import acting_scope, forbid_unless
from api.apps.service_errors import not_found_response, service_error_response
from api.db.services import knowledgebase_service
from api.db.services.knowledgebase_service import CreateRequest
from api.db.services.service_errors import Kind, ServiceError
from api.utils import reasons
from api.utils.api_utils import json_result
from api.utils.blocking import DB_EXECUTOR, DOCSTORE_EXECUTOR, run_blocking
from common.settings import Settings

dataset_bp = Blueprint("dataset", __name__)

# Identical to the endpoint rows in conf/routes.yaml (Quart spells a path parameter <name>, the registry {name}).
DATASETS = "/api/v1/datasets"
DATASET = "/api/v1/datasets/<dataset_id>"

AREA = "datasets"
MANAGE = "manage_dataset"
LOOKUP_TIMEOUT_SECONDS = 10.0
# The service waits up to 10 s for the creation lock and gives the index engine 30 s; the handler waits longer so the typed errors win.
CREATE_TIMEOUT_SECONDS = 45.0
DEFAULT_PAGE_SIZE = 12
MAX_PAGE_SIZE = 100
MAX_KEYWORDS = 128
_TENANT_ID_PATTERN = r"^[0-9a-f]{32}$"
_WHOLE_NUMBER = re.compile(r"[0-9]{1,9}")


class CreateDatasetBody(BaseModel):
    """Only these fields exist. Bounds on the text are the service's, so a bad value is a typed ``dataset_invalid`` and an over-long model id a typed ``model_unavailable``."""

    model_config = ConfigDict(extra="forbid")

    name: str
    embd_id: str | None = None
    parser_id: str | None = None
    permission: str | None = None
    description: str | None = None
    language: str | None = None
    avatar: str | None = None
    parser_config: dict[str, Any] | None = None
    tenant_id: str | None = Field(default=None, pattern=_TENANT_ID_PATTERN)


class UploadLimitsView(BaseModel):
    max_file_bytes: int
    max_files_per_request: int
    max_documents: int
    allowed_extensions: list[str]


class DatasetView(BaseModel):
    id: str
    name: str
    description: str
    avatar: str
    language: str
    permission: str
    embd_id: str
    embedding_dimension: int | None
    parser_id: str
    parser_config: dict[str, Any]
    doc_num: int
    chunk_num: int
    token_num: int
    tenant_id: str
    created_by: str
    create_time: int
    update_time: int
    upload_limits: UploadLimitsView | None = None


class DatasetEnvelope(BaseModel):
    code: int
    message: str
    data: DatasetView


class DatasetPage(BaseModel):
    items: list[DatasetView]
    total: int


class DatasetPageEnvelope(BaseModel):
    code: int
    message: str
    data: DatasetPage


def _settings() -> Settings:
    return current_app.extensions["ragflow_settings"]


def _invalid(message: str) -> ServiceError:
    return ServiceError(Kind.INVALID, reasons.DATASET_INVALID, message)


def _whole(name: str, default: int, low: int, high: int) -> int:
    raw = request.args.get(name)
    if raw is None:
        return default
    if _WHOLE_NUMBER.fullmatch(raw) is None or not low <= int(raw) <= high:
        raise _invalid(f"{name} must be a whole number from {low} to {high}")
    return int(raw)


@validate_request(CreateDatasetBody)
@document_response(DatasetEnvelope, 200)
async def create_dataset(data: CreateDatasetBody) -> Response:
    try:
        scope = await acting_scope(data.tenant_id)
        if scope is None:
            return not_found_response()
        denied = forbid_unless(scope, AREA, MANAGE)
        if denied is not None:
            return denied
        req = CreateRequest(
            name=data.name,
            embd_id=data.embd_id,
            parser_id=data.parser_id,
            permission=data.permission,
            description=data.description,
            language=data.language,
            avatar=data.avatar,
            parser_config=data.parser_config,
        )
        # Settings are read here, on the loop; the document-store pool keeps a stalled search engine from parking the database pool's threads.
        view = await run_blocking(DOCSTORE_EXECUTOR, knowledgebase_service.create_view, _settings(), scope, g.principal.user_id, req, timeout=CREATE_TIMEOUT_SECONDS)
        return json_result(view)
    except ServiceError as exc:
        return service_error_response(exc)


@document_response(DatasetPageEnvelope, 200)
async def list_datasets() -> Response:
    try:
        scope = await acting_scope(request.args.get("tenant_id"))
        if scope is None:
            return not_found_response()
        page = _whole("page", 1, 1, 1_000_000_000)
        page_size = _whole("page_size", DEFAULT_PAGE_SIZE, 1, MAX_PAGE_SIZE)
        keywords = request.args.get("keywords")
        if keywords is not None and len(keywords) > MAX_KEYWORDS:
            raise _invalid(f"keywords must be at most {MAX_KEYWORDS} characters")
        user_id = g.principal.user_id  # read on the loop: the request context does not follow the call into the worker thread
        view = await run_blocking(
            DB_EXECUTOR,
            lambda: knowledgebase_service.list_view(scope, user_id, page=page, page_size=page_size, keywords=keywords),
            timeout=LOOKUP_TIMEOUT_SECONDS,
        )
        return json_result(view)
    except ServiceError as exc:
        return service_error_response(exc)


@document_response(DatasetEnvelope, 200)
async def get_dataset(dataset_id: str) -> Response:
    try:
        upload = _settings().upload
        view = await run_blocking(DB_EXECUTOR, knowledgebase_service.detail_view, g.principal, dataset_id, upload, timeout=LOOKUP_TIMEOUT_SECONDS)
        return json_result(view)
    except ServiceError as exc:
        return service_error_response(exc)


dataset_bp.add_url_rule(DATASETS, endpoint="create_dataset", view_func=create_dataset, methods=["POST"])
dataset_bp.add_url_rule(DATASETS, endpoint="list_datasets", view_func=list_datasets, methods=["GET"])
dataset_bp.add_url_rule(DATASET, endpoint="get_dataset", view_func=get_dataset, methods=["GET"])
