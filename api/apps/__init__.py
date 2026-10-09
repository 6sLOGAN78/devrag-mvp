"""Quart application factory."""
from __future__ import annotations

from collections.abc import Iterable

from quart import Blueprint, Quart
from quart_schema import QuartSchema

from api.apps.auth import Resolver, register_auth_gate
from api.apps.errors import register_error_handlers
from api.apps.middleware import register_middleware
from api.db.services import auth_service
from common.settings import Settings, get_settings

OPENAPI_PATH = "/api/v1/openapi.json"


def create_app(
    settings: Settings | None = None,
    extra_blueprints: Iterable[Blueprint] = (),
    *,
    principal_resolver: Resolver | None = None,
) -> Quart:
    """Build the application.

    ``principal_resolver`` is a keyword for unit tests and the offline OpenAPI export only. It is never read
    from configuration or the environment, and the production entrypoint never passes it (test_auth_gate).
    """
    settings = settings or get_settings()
    # No static folder: this server serves the API only (the SPA is served by Nginx), so no route is undeclared.
    app = Quart("ragflow_server", static_folder=None)
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
    register_auth_gate(app, settings, principal_resolver or auth_service.make_resolver(settings.security.secret_key))

    from api.apps.restful_apis.dataset_api import dataset_bp
    from api.apps.restful_apis.models_api import models_bp
    from api.apps.restful_apis.provider_api import provider_bp
    from api.apps.restful_apis.system_api import system_bp

    app.register_blueprint(system_bp)
    app.register_blueprint(provider_bp)
    app.register_blueprint(models_bp)
    app.register_blueprint(dataset_bp)
    for blueprint in extra_blueprints:
        app.register_blueprint(blueprint)
    return app
