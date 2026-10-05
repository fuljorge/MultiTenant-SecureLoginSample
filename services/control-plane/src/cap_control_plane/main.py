"""Ponto de entrada da API do Control Plane."""

from __future__ import annotations

from fastapi import APIRouter, FastAPI

from cap_control_plane.audit import api as audit_api
from cap_control_plane.core.logging import configure_logging
from cap_control_plane.core.settings import Settings, get_settings
from cap_control_plane.core.telemetry import setup_telemetry
from cap_control_plane.identity.api import (
    auth,
    me,
    organizations,
    security_settings,
    super_admins,
    users,
)
from cap_control_plane.identity.authz import audit_access_denied
from cap_control_plane.identity.middleware import bff_session
from cap_control_plane.identity.service.common import register_error_handlers
from cap_control_plane.services import Services


def create_app(settings: Settings | None = None, services: Services | None = None) -> FastAPI:
    configured = settings or (services.settings if services else None)
    # Documentação interativa só quando ligada (desenvolvimento); OWASP ASVS 4.3.2. O
    # cliente TypeScript usa app.openapi(), que funciona sem a rota.
    docs = bool(configured and configured.api_docs)
    app = FastAPI(
        title="SecureLogin Control Plane",
        version="0.1.0",
        docs_url="/docs" if docs else None,
        redoc_url=None,
        openapi_url="/openapi.json" if docs else None,
        # operationId = nome da função: gera useMe, useMySessions etc. no cliente TypeScript.
        generate_unique_id_function=lambda route: route.name,
    )

    @app.get("/healthz", include_in_schema=False)
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    if settings is None and services is None:
        # Sem configuração (ex.: geração do OpenAPI): só as rotas, sem serviços.
        _include_routes(app)
        return app

    services = services or Services.from_settings(settings or get_settings())
    app.state.services = services
    app.state.record_access_denied = audit_access_denied(services.engine)
    app.middleware("http")(bff_session)
    _include_routes(app)
    register_error_handlers(app)
    setup_telemetry(app, services.settings.service_name)
    return app


def _include_routes(app: FastAPI) -> None:
    api = APIRouter(prefix="/api/v1")
    api.include_router(auth.router)
    api.include_router(me.router)
    api.include_router(users.router)
    api.include_router(organizations.router)
    api.include_router(super_admins.router)
    api.include_router(security_settings.router)
    api.include_router(audit_api.router)
    app.include_router(api)


def run() -> FastAPI:
    """Fábrica usada pelo uvicorn: `uvicorn cap_control_plane.main:run --factory`."""
    configure_logging()
    return create_app(get_settings())
