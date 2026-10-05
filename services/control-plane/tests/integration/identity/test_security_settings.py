"""Configuração de segurança da instalação pelo Super Administrador (T048, T083; RF-007)."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from tests.support.keycloak import KeycloakAdmin
from tests.support.people import create_organization, create_person, csrf_headers, logged_in
from tests.support.stack import Stack


@pytest.fixture
def super_admin_client(
    app: FastAPI, engine: Engine, stack: Stack, kc: KeycloakAdmin
) -> Iterator[TestClient]:
    person = create_person(engine, kc, super_admin=True)
    with logged_in(app, stack, person) as client:
        original = client.get("/api/v1/security-settings").json()
        yield client
        # Devolve a instalação à configuração original para os outros testes.
        client.put("/api/v1/security-settings", json=original, headers=csrf_headers(client))
    kc.delete_user(str(person.id))


def test_le_a_configuracao_vigente_do_keycloak(super_admin_client: TestClient) -> None:
    settings = super_admin_client.get("/api/v1/security-settings").json()

    assert settings["password_min_length"] == 12
    assert settings["code_valid_minutes"] == 10
    assert settings["session_idle_minutes"] == 30
    assert settings["invitation_valid_hours"] == 72


def test_altera_e_aplica_no_keycloak(super_admin_client: TestClient, kc: KeycloakAdmin) -> None:
    current = super_admin_client.get("/api/v1/security-settings").json()
    changed = {**current, "password_min_length": 14, "code_valid_minutes": 12,
               "invitation_valid_hours": 48}  # fmt: skip

    response = super_admin_client.put(
        "/api/v1/security-settings", json=changed, headers=csrf_headers(super_admin_client)
    )

    realm = kc.get("")
    executions = kc.get("/authentication/flows/cap-browser/executions")
    step = next(e for e in executions if e.get("providerId") == "email-authenticator")
    code = kc.get(f"/authentication/config/{step['authenticationConfig']}")["config"]
    assert response.status_code == 200
    assert "length(14)" in realm["passwordPolicy"]
    assert "passwordBlacklist(pwdb-top-1000000.txt)" in realm["passwordPolicy"]
    assert "maxLength(128)" in realm["passwordPolicy"]
    assert realm["actionTokenGeneratedByAdminLifespan"] == 48 * 3600
    assert code["ttl"] == "720"
    assert code["simulationMode"] == "false"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("password_min_length", 8),
        ("code_valid_minutes", 20),
        ("code_length", 4),
        ("lockout_failures", 50),
        ("session_max_hours", 48),
    ],
)
def test_limites_minimos_nao_podem_ser_afrouxados(
    super_admin_client: TestClient, field: str, value: int
) -> None:
    current = super_admin_client.get("/api/v1/security-settings").json()

    response = super_admin_client.put(
        "/api/v1/security-settings",
        json={**current, field: value},
        headers=csrf_headers(super_admin_client),
    )

    assert response.status_code == 422


def test_administrador_de_organizacao_nao_altera_a_seguranca(
    app: FastAPI, engine: Engine, stack: Stack, kc: KeycloakAdmin
) -> None:
    person = create_person(engine, kc, organizations={create_organization(engine): "administrator"})

    with logged_in(app, stack, person) as client:
        response = client.get("/api/v1/security-settings")

    assert response.status_code == 403
    kc.delete_user(str(person.id))
