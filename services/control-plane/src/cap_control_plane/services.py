"""Serviços compartilhados pela aplicação, criados uma vez e guardados em `app.state`."""

from __future__ import annotations

from dataclasses import dataclass

import redis
from fastapi import Request
from sqlalchemy import Engine

from cap_control_plane.core.db import create_db_engine
from cap_control_plane.core.email import Mailer
from cap_control_plane.core.secrets import TransitCipher
from cap_control_plane.core.settings import Settings
from cap_control_plane.identity.keycloak_admin import KeycloakAdminClient
from cap_control_plane.identity.oidc import OidcClient
from cap_control_plane.identity.service.security_settings import SecuritySettingsService
from cap_control_plane.identity.sessions import SessionStore


@dataclass
class Services:
    settings: Settings
    engine: Engine
    valkey: redis.Redis
    sessions: SessionStore
    oidc: OidcClient
    keycloak_admin: KeycloakAdminClient
    mailer: Mailer
    security: SecuritySettingsService

    @classmethod
    def from_settings(cls, settings: Settings) -> Services:
        valkey = redis.Redis.from_url(settings.valkey_url.get_secret_value())
        keycloak_admin = KeycloakAdminClient(settings)
        security = SecuritySettingsService(keycloak_admin, settings)
        return cls(
            settings=settings,
            engine=create_db_engine(settings),
            valkey=valkey,
            sessions=SessionStore(
                valkey,
                TransitCipher(settings),
                idle_seconds=settings.session_idle_seconds,
                max_seconds=settings.session_max_seconds,
                # Tempos configurados pelo Administrador da instalação (RF-006, RF-007).
                limits=security.session_limits,
            ),
            oidc=OidcClient(settings),
            keycloak_admin=keycloak_admin,
            mailer=Mailer(settings),
            security=security,
        )


def get_services(request: Request) -> Services:
    services: Services = request.app.state.services
    return services
