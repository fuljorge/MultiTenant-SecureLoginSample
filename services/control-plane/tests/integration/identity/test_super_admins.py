"""Gestão de Super Administradores (T091; US5; RF-012, RF-028, RF-030)."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from cap_control_plane.core.db import DbContext, transaction
from tests.support.keycloak import KeycloakAdmin
from tests.support.mailpit import wait_for_email
from tests.support.people import (
    Person,
    create_organization,
    create_person,
    csrf_headers,
    logged_in,
)
from tests.support.stack import Stack


@pytest.fixture
def isolated_super_admins(engine: Engine) -> Iterator[None]:
    """O último ativo só pode ser testado com uma instalação sem outros Super Administradores."""
    with transaction(engine, DbContext.system()) as s:
        s.execute(text("DELETE FROM identity.super_admin"))
    yield
    with transaction(engine, DbContext.system()) as s:
        s.execute(text("DELETE FROM identity.super_admin"))


@pytest.fixture
def first(engine: Engine, kc: KeycloakAdmin, isolated_super_admins: None) -> Iterator[Person]:
    person = create_person(engine, kc, super_admin=True)
    yield person
    kc.delete_user(str(person.id))


@pytest.fixture
def client(app: FastAPI, stack: Stack, first: Person) -> Iterator[TestClient]:
    with logged_in(app, stack, first) as c:
        yield c


def test_convida_desativa_e_reativa_super_administrador(
    client: TestClient, engine: Engine, stack: Stack, kc: KeycloakAdmin
) -> None:
    email, since = f"super-{uuid.uuid4().hex[:8]}@exemplo.com.br", datetime.now(UTC)
    headers = csrf_headers(client)

    invited = client.post(
        "/api/v1/super-admins", json={"name": "Bia", "email": email}, headers=headers
    )

    assert invited.status_code == 201
    new_id = invited.json()["id"]
    assert "Você recebeu acesso" in wait_for_email(stack.mailpit_url, email, since)
    assert email in [s["email"] for s in client.get("/api/v1/super-admins").json()]
    with transaction(engine, DbContext.system()) as s:
        s.execute(
            text("UPDATE identity.user_account SET status = 'active' WHERE id = :id"),
            {"id": new_id},
        )
    assert client.post(f"/api/v1/super-admins/{new_id}/disable", headers=headers).status_code == 204
    assert kc.get(f"/users/{new_id}")["enabled"] is False
    assert client.post(f"/api/v1/super-admins/{new_id}/enable", headers=headers).status_code == 204
    assert kc.get(f"/users/{new_id}")["enabled"] is True
    kc.delete_user(new_id)


def test_ultimo_super_administrador_ativo_nao_e_desativado(
    app: FastAPI, client: TestClient, engine: Engine, stack: Stack, kc: KeycloakAdmin
) -> None:
    second = create_person(engine, kc, super_admin=True)
    with logged_in(app, stack, second) as other:
        first_disabled = other.post(
            f"/api/v1/super-admins/{client.get('/api/v1/me').json()['id']}/disable",
            headers=csrf_headers(other),
        )
        last = other.post(f"/api/v1/super-admins/{second.id}/disable", headers=csrf_headers(other))

    assert first_disabled.status_code == 204
    assert last.status_code == 409  # o próprio, e o último ativo
    kc.delete_user(str(second.id))


def test_email_com_vinculo_em_organizacao_nao_vira_super_administrador(
    client: TestClient, engine: Engine, kc: KeycloakAdmin
) -> None:
    member = create_person(engine, kc, organizations={create_organization(engine): "supervisor"})

    response = client.post(
        "/api/v1/super-admins",
        json={"name": "Membro", "email": member.email},
        headers=csrf_headers(client),
    )

    assert response.status_code == 409
    kc.delete_user(str(member.id))
