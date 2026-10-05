"""System routes: health, status and the Python-only language diagnostic."""
from __future__ import annotations

from pydantic import BaseModel
from quart import Blueprint, Response, current_app
from quart_schema import document_response

from api.db.services import system_service
from api.utils.api_utils import error_result, json_result
from common.constants import RetCode
from common.settings import Settings

system_bp = Blueprint("system", __name__)

# Mirrors the Python exact entries (and their `also` aliases) in conf/routes.yaml.
HEALTH_PATHS = ("/api/v1/system/healthz", "/system/healthz", "/api/v1/system/status", "/system/status")
LANGUAGE_PATH = "/api/v1/language"  # direct-only diagnostic duplicate; Nginx routes this path to Go (D-08)


class ProbeResult(BaseModel):
    status: str
    elapsed_ms: int


class Checks(BaseModel):
    database: ProbeResult
    redis: ProbeResult
    storage: ProbeResult
    doc_store: ProbeResult


class HealthData(BaseModel):
    status: str
    engine: str
    checks: Checks


class HealthEnvelope(BaseModel):
    code: int
    message: str
    data: HealthData


class LanguageData(BaseModel):
    engine: str


class LanguageEnvelope(BaseModel):
    code: int
    message: str
    data: LanguageData


@document_response(HealthEnvelope, 200)
@document_response(HealthEnvelope, 503)
async def health() -> Response:
    settings: Settings = current_app.extensions["ragflow_settings"]
    status, data = await system_service.get_health(settings)
    if status == 200:
        return json_result(data)
    return error_result(RetCode.SERVICE_UNAVAILABLE, "service unavailable", 503, data=data)


@document_response(LanguageEnvelope, 200)
async def language() -> Response:
    return json_result(system_service.get_language())


for _index, _path in enumerate(HEALTH_PATHS):
    system_bp.add_url_rule(_path, endpoint=f"health_{_index}", view_func=health, methods=["GET"])
system_bp.add_url_rule(LANGUAGE_PATH, endpoint="language", view_func=language, methods=["GET"])
