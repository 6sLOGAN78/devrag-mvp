"""Quart application factory."""
from __future__ import annotations

from collections.abc import Iterable

from quart import Blueprint, Quart
from quart_schema import QuartSchema

from api.apps.errors import register_error_handlers
from api.apps.middleware import register_middleware
from common.settings import Settings, get_settings

OPENAPI_PATH = "/api/v1/openapi.json"


def create_app(settings: Settings | None = None, extra_blueprints: Iterable[Blueprint] = ()) -> Quart:
    settings = settings or get_settings()
    app = Quart("ragflow_server")
    app.config["MAX_CONTENT_LENGTH"] = 1024 * 1024 * 1024
    app.extensions["ragflow_settings"] = settings
    # Docs UIs are disabled; the schema itself is served at OPENAPI_PATH (API-08).
    QuartSchema(
        app,
        openapi_path=OPENAPI_PATH,
        swagger_ui_path=None,
        redoc_ui_path=None,
        scalar_ui_path=None,
        info={"title": "devRag Python API", "version": "1"},
    )
    # Registered after QuartSchema so these handlers win over its default 400 responses.
    register_error_handlers(app)
    register_middleware(app, settings)

    for blueprint in extra_blueprints:
        app.register_blueprint(blueprint)
    return app
