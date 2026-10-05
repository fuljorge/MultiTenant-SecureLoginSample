"""Ativação no primeiro login (T045; US2 cenário 1, US3 cenário 1)."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from cap_control_plane.core.db import DbContext, transaction
from tests.support.keycloak import KeycloakAdmin
from tests.support.people import create_organization, create_person, login
from tests.support.stack import Stack


def test_primeiro_login_ativa_pessoa_e_vinculos(
    client: TestClient, engine: Engine, stack: Stack, kc: KeycloakAdmin
) -> None:
    org = create_organization(engine)
    person = create_person(engine, kc, organizations={org: "supervisor"}, status="invited")
    with transaction(engine, DbContext.system()) as s:
        s.execute(
            text("UPDATE identity.membership SET status = 'pending' WHERE user_id = :id"),
            {"id": person.id},
        )

    login(client, stack, person)

    with transaction(engine, DbContext.system()) as s:
        status = s.execute(
            text("SELECT status FROM identity.user_account WHERE id = :id"), {"id": person.id}
        ).scalar_one()
        membership = s.execute(
            text("SELECT status FROM identity.membership WHERE user_id = :id"), {"id": person.id}
        ).scalar_one()
        activated = s.execute(
            text(
                "SELECT details FROM audit.audit_event"
                " WHERE event_type = 'user.activated' AND target_id = :id"
            ),
            {"id": str(person.id)},
        ).scalar_one()
    assert (status, membership) == ("active", "active")
    assert activated == {"via": "invitation"}
    assert client.get("/api/v1/me").json()["active_organization_id"] == str(org)
    kc.delete_user(str(person.id))


def test_pessoa_desativada_nao_entra(
    client: TestClient, engine: Engine, stack: Stack, kc: KeycloakAdmin
) -> None:
    from tests.support.people import authorize

    org = create_organization(engine)
    person = create_person(engine, kc, organizations={org: "supervisor"}, status="disabled")

    callback = client.get(
        "/api/v1/auth/callback", params=authorize(client, stack, person), follow_redirects=False
    )

    assert "/entrar/erro?motivo=sem-acesso" in callback.headers["location"]
    assert client.get("/api/v1/me").status_code == 401
    kc.delete_user(str(person.id))


def test_vinculo_removido_nao_e_reativado(
    client: TestClient, engine: Engine, stack: Stack, kc: KeycloakAdmin
) -> None:
    org_a, org_b = create_organization(engine), create_organization(engine)
    person = create_person(
        engine, kc, organizations={org_a: "supervisor", org_b: "supervisor"}, status="invited"
    )
    with transaction(engine, DbContext.system()) as s:
        s.execute(
            text(
                "UPDATE identity.membership SET status = 'removed'"
                " WHERE user_id = :id AND organization_id = :org"
            ),
            {"id": person.id, "org": org_b},
        )

    login(client, stack, person)

    orgs = {o["id"] for o in client.get("/api/v1/me").json()["organizations"]}
    assert orgs == {str(org_a)}
    assert uuid.UUID(client.get("/api/v1/me").json()["active_organization_id"]) == org_a
    kc.delete_user(str(person.id))
