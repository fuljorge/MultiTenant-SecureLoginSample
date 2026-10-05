"""Isolamento entre organizações, rota a rota (T061; US5 cenário 8; RF-020, CS-004).

O Administrador da organização A tenta agir sobre uma pessoa e um convite da B. Cada
tentativa responde 404 (não revela que existe) e fica registrada como `access.denied`.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from cap_control_plane.core.db import DbContext, transaction
from tests.support.keycloak import KeycloakAdmin
from tests.support.people import (
    Person,
    create_organization,
    create_person,
    csrf_headers,
    logged_in,
)
from tests.support.stack import Stack


@pytest.fixture(scope="module")
def scenario(
    app: FastAPI, engine: Engine, stack: Stack, kc: KeycloakAdmin
) -> Iterator[tuple[TestClient, Person, Person, uuid.UUID]]:
    org_a, org_b = create_organization(engine), create_organization(engine)
    admin_a = create_person(engine, kc, organizations={org_a: "administrator"})
    person_b = create_person(engine, kc, organizations={org_b: "supervisor"})
    with logged_in(app, stack, admin_a) as client:
        yield client, admin_a, person_b, org_b
    for p in (admin_a, person_b):
        kc.delete_user(str(p.id))


ROUTES = [
    ("GET", "/api/v1/users/{b}", None),
    ("PATCH", "/api/v1/users/{b}/memberships/{org_b}", {"profile": "developer"}),
    ("DELETE", "/api/v1/users/{b}/memberships/{org_b}", None),
    ("POST", "/api/v1/users/{b}/disable", None),
    ("POST", "/api/v1/users/{b}/enable", None),
    ("POST", "/api/v1/users/{b}/email-change", {"new_email": "x@exemplo.com.br"}),
    ("POST", "/api/v1/users/{b}/sessions/revoke", None),
]


@pytest.mark.parametrize(("method", "path", "body"), ROUTES)
def test_administrador_de_a_nao_age_sobre_pessoa_de_b(
    scenario: tuple[TestClient, Person, Person, uuid.UUID],
    engine: Engine,
    method: str,
    path: str,
    body: dict[str, str] | None,
) -> None:
    client, admin_a, person_b, org_b = scenario

    response = client.request(
        method,
        path.format(b=person_b.id, org_b=org_b),
        json=body,
        headers=csrf_headers(client),
    )

    assert response.status_code == 404, response.text
    with transaction(engine, DbContext.system()) as s:
        denied = s.execute(
            text(
                "SELECT count(*) FROM audit.audit_event WHERE actor_user_id = :a"
                " AND event_type = 'access.denied' AND target_id = :b"
                " AND details->>'reason' = 'other_organization'"
            ),
            {"a": admin_a.id, "b": str(person_b.id)},
        ).scalar_one()
    assert denied >= 1
    with transaction(engine, DbContext.system()) as s:
        status = s.execute(
            text("SELECT status::text FROM identity.membership WHERE user_id = :b"),
            {"b": person_b.id},
        ).scalar_one()
    assert status == "active"


def test_pessoa_inexistente_responde_404_sem_registro(
    scenario: tuple[TestClient, Person, Person, uuid.UUID], engine: Engine
) -> None:
    client, admin_a, _, _ = scenario
    ghost = uuid.uuid4()

    assert client.get(f"/api/v1/users/{ghost}").status_code == 404
    with transaction(engine, DbContext.system()) as s:
        denied = s.execute(
            text(
                "SELECT count(*) FROM audit.audit_event WHERE actor_user_id = :a"
                " AND event_type = 'access.denied' AND target_id = :g"
            ),
            {"a": admin_a.id, "g": str(ghost)},
        ).scalar_one()
    assert denied == 0
