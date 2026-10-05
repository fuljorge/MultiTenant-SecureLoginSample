"""Fixtures compartilhadas pelos testes do Control Plane."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from cap_control_plane.core.db import create_db_engine
from cap_control_plane.core.settings import Settings
from cap_control_plane.main import create_app
from cap_control_plane.services import Services
from tests.support.database import MigratedDatabase, run_migrations, temporary_database
from tests.support.keycloak import KeycloakAdmin
from tests.support.stack import COMPOSE_DIR, Stack, is_ready, load_env, wait_until_ready

INTEGRATION_DIR = Path(__file__).parent / "integration"


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Marca como `integration` tudo que está em tests/integration (precisa de Docker)."""
    for item in items:
        if INTEGRATION_DIR in Path(str(item.path)).parents:
            item.add_marker(pytest.mark.integration)


@pytest.fixture(scope="session")
def stack() -> Iterator[Stack]:
    """Ambiente do compose local: reaproveita o que já estiver no ar; senão, sobe e derruba."""
    current = Stack(
        keycloak_url="http://localhost:8080/idp",
        realm="cap",
        mailpit_url="http://localhost:8025",
        secrets=load_env(),
    )
    if is_ready(current):
        yield current
        return

    from testcontainers.compose import DockerCompose

    with DockerCompose(str(COMPOSE_DIR), compose_file_name="docker-compose.yml", build=True):
        wait_until_ready(current)
        yield current


@pytest.fixture(scope="session")
def database(stack: Stack) -> Iterator[MigratedDatabase]:
    """Banco temporário com as migrações aplicadas; apagado ao fim da sessão de testes."""
    with temporary_database(stack) as db:
        run_migrations(db.migrator_url)
        yield db


@pytest.fixture(scope="session")
def settings(stack: Stack, database: MigratedDatabase) -> Settings:
    """Configuração do Control Plane apontando para o ambiente do compose."""
    s = stack.secrets
    return Settings(
        public_url="http://localhost:3000",
        database_url=database.app_url,
        migrator_database_url=database.migrator_url,
        valkey_url=f"redis://:{s['VALKEY_PASSWORD']}@127.0.0.1:6379/0",
        keycloak_url=stack.keycloak_url,
        oidc_client_secret=s["KC_CLIENT_SECRET_CONTROL_PLANE"],
        admin_client_secret=s["KC_CLIENT_SECRET_ADMIN_BRIDGE"],
        openbao_url="http://localhost:8200",
        openbao_token=s["OPENBAO_DEV_ROOT_TOKEN"],
        smtp_host="localhost",
        smtp_port=1025,
    )


@pytest.fixture(scope="session")
def engine(settings: Settings) -> Iterator[Engine]:
    """Conexão como `cap_app` (papel da aplicação, sujeito a RLS)."""
    db_engine = create_db_engine(settings)
    yield db_engine
    db_engine.dispose()


@pytest.fixture(scope="session")
def services(settings: Settings) -> Services:
    return Services.from_settings(settings)


@pytest.fixture(scope="session")
def app(services: Services) -> FastAPI:
    return create_app(services=services)


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    """Cliente HTTPS: os cookies `__Host-` exigem conexão segura."""
    with TestClient(app, base_url="https://testserver") as test_client:
        yield test_client


@pytest.fixture(scope="session")
def kc(stack: Stack) -> KeycloakAdmin:
    """Admin API do Keycloak para preparar dados de teste (realm master)."""
    return KeycloakAdmin(stack)
