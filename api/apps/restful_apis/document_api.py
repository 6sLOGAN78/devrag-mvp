"""Document upload route (plan 03-16; E2E-04, DOC-01..07, DOC-16, STOR-01, STOR-11, SEC-06, TEN-13, D-09, D-11, D-14, D-20).

``POST /api/v1/documents/upload?dataset_id=...[&parser_id=...][&parser_config={json}]`` with a multipart body whose parts named ``file`` are the files.

The handler order is the contract: authorise the dataset (an absent, foreign or private-to-others dataset is the one 404; a caller without the
document permission gets 403) before a byte of the body is read; then set this route's limits and read the body; then hand the plain streams to the
service in the storage executor. Zero files is a 400 ``no_files``: Quart's multipart parser is silent about a malformed body and returns an empty
mapping, so emptiness is never taken for success (Pitfall 5).

Request limits (D-11, Pitfall 8). Per request, only on this route: ``request.max_content_length`` is ``max_file_bytes + 1 MiB`` (the framing allowance
that matches the 101m Nginx location) and ``request.body_timeout`` is ``upload.body_timeout_seconds``. The installed Quart takes ``body_timeout`` as a
plain per-request attribute, so no application setting changes: other routes keep Quart's 60 s. ``request.max_content_length`` alone only reaches
the multipart parser's memory guard, so ``CappedRequest`` (``api/apps/request_body.py``) also counts the streamed bytes against the same cap; a declared
``Content-Length`` over the cap is refused before any byte is read. All three answer 413 ``file_too_large``.
"""
from __future__ import annotations

import json
from typing import Any, Protocol

from pydantic import BaseModel
from quart import Blueprint, Response, current_app, g, request
from quart_schema import document_response
from werkzeug.exceptions import RequestEntityTooLarge

from api.apps.service_errors import service_error_response
from api.db.services import document_service
from api.db.services.document_service import UploadItem
from api.db.services.knowledgebase_service import MAX_PARSER_CONFIG
from api.db.services.service_errors import Kind, ServiceError
from api.utils import reasons
from api.utils.api_utils import json_result
from api.utils.blocking import DB_EXECUTOR, STORAGE_EXECUTOR, run_blocking
from common.settings import Settings, UploadSettings

document_bp = Blueprint("document", __name__)

# Identical to the endpoint row in conf/routes.yaml.
UPLOAD = "/api/v1/documents/upload"

FILE_FIELD = "file"
BODY_OVERHEAD_BYTES = 1024 * 1024  # multipart framing on top of one maximal file; the 101m Nginx location is the same sum
AUTHORIZE_TIMEOUT_SECONDS = 10.0


class _LimitedRequest(Protocol):
    max_content_length: int | None
    body_timeout: int | float | None


class DocumentView(BaseModel):
    id: str
    name: str
    size: int
    type: str
    suffix: str
    run: str
    progress: float
    dataset_id: str
    created_by: str
    parser_id: str
    chunk_num: int
    token_num: int
    create_time: int
    update_time: int


class DocumentListEnvelope(BaseModel):
    code: int
    message: str
    data: list[DocumentView]


def _settings() -> Settings:
    return current_app.extensions["ragflow_settings"]


def _too_large() -> ServiceError:
    return ServiceError(Kind.PAYLOAD_TOO_LARGE, reasons.FILE_TOO_LARGE, "the file is larger than the allowed size", data={"http_status": 413})


def apply_upload_limits(req: _LimitedRequest, upload: UploadSettings) -> None:
    """Set this request's body cap and body timeout, and arm the byte counter when the request has one."""
    cap = upload.max_file_bytes + BODY_OVERHEAD_BYTES
    req.max_content_length = cap
    req.body_timeout = upload.body_timeout_seconds
    body = getattr(req, "body", None)
    arm = getattr(body, "cap", None)
    if arm is not None:
        arm(cap)


async def read_upload_files(upload: UploadSettings) -> list[UploadItem]:
    """Apply the route's limits, parse the multipart body and return its ``file`` parts. Raises ``ServiceError`` for 413 and for no files."""
    apply_upload_limits(request, upload)
    cap = request.max_content_length
    declared = request.content_length
    if declared is not None and cap is not None and declared > cap:
        raise _too_large()
    try:
        files = await request.files
    except RequestEntityTooLarge:
        close_upload_streams()
        raise _too_large() from None
    items = [UploadItem(part.filename or "", part.mimetype or "", part.stream) for part in files.getlist(FILE_FIELD)]
    if not items:
        close_upload_streams()
        raise ServiceError(Kind.INVALID, reasons.NO_FILES, "no files were uploaded")
    return items


def close_upload_streams() -> None:
    """Close the request's temporary files (every part the parser opened, finished or not)."""
    closer = getattr(request, "close_streams", None)
    if closer is not None:
        closer()


def _config_argument(raw: str | None) -> dict[str, Any] | None:
    """The optional ``parser_config`` query value: a JSON object in text. The service re-checks the content."""
    if raw is None:
        return None
    if len(raw) > MAX_PARSER_CONFIG * 2:
        raise ServiceError(Kind.INVALID, reasons.PARSER_INVALID, "the parser configuration is too long")
    try:
        value = json.loads(raw)
    except ValueError:
        raise ServiceError(Kind.INVALID, reasons.PARSER_INVALID, "the parser configuration is not valid JSON") from None
    if not isinstance(value, dict):
        raise ServiceError(Kind.INVALID, reasons.PARSER_INVALID, "the parser configuration must be an object")
    return value


@document_response(DocumentListEnvelope, 200)
async def upload_documents() -> Response:
    abandoned = False  # a worker thread that missed its deadline may still be reading the streams: leave them open
    try:
        settings = _settings()
        principal = g.principal
        # Authorised before the body is read. The service does the visibility and permission checks in one place.
        visible = await run_blocking(DB_EXECUTOR, document_service.authorize_upload, principal, request.args.get("dataset_id", ""), timeout=AUTHORIZE_TIMEOUT_SECONDS)
        parser_id = request.args.get("parser_id")
        parser_config = _config_argument(request.args.get("parser_config"))
        items: list[UploadItem] = await read_upload_files(settings.upload)
        made = await run_blocking(
            STORAGE_EXECUTOR,
            lambda: document_service.upload_documents(settings, visible, principal.user_id, items, parser_id=parser_id, parser_config=parser_config),
            timeout=float(settings.upload.body_timeout_seconds),
        )
        return json_result(made)
    except ServiceError as exc:
        abandoned = exc.kind is Kind.TIMEOUT
        return service_error_response(exc)
    finally:
        if not abandoned:
            close_upload_streams()


document_bp.add_url_rule(UPLOAD, endpoint="upload_documents", view_func=upload_documents, methods=["POST"])
