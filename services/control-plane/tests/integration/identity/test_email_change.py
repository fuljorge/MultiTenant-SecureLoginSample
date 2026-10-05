"""Troca de e-mail pelo Administrador (T047; US3 cenário 6)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from cap_control_plane.core.db import DbContext, transaction
from tests.support.keycloak import KeycloakAdmin
from tests.support.mailpit import wait_for_email
from tests.support.people import create_organization, create_person, csrf_headers, logged_in
from tests.support.stack import Stack


def _new_email() -> str:
    return f"novo-{uuid.uuid4().hex[:8]}@cliente.com.br"


def _request(admin: TestClient, user_id: uuid.UUID, email: str) -> str:
    since = datetime.now(UTC)
    response = admin.post(
        f"/api/v1/users/{user_id}/email-change",
        json={"new_email": email},
        headers=csrf_headers(admin),
    )
    assert response.status_code == 202, response.text
    return response.text, since  # type: ignore[return-value]


def test_confirmacao_troca_email_encerra_sessoes_e_avisa_o_antigo(
    app: FastAPI, engine: Engine, stack: Stack, kc: KeycloakAdmin
) -> None:
    org = create_organization(engine)
    admin = create_person(engine, kc, organizations={org: "administrator"})
    person = create_person(engine, kc, organizations={org: "supervisor"})
    new_email = _new_email()

    with logged_in(app, stack, admin) as admin_client, logged_in(app, stack, person) as target:
        _, since = _request(admin_client, person.id, new_email)
        mail = wait_for_email(stack.mailpit_url, new_email, since)
        token = mail.split("/confirmar-email/")[1].split()[0]
        old_notice_since = datetime.now(UTC)

        with TestClient(app, base_url="https://testserver") as anonymous:
            confirmed = anonymous.post(f"/api/v1/email-change/{token}/confirm")
            reused = anonymous.post(f"/api/v1/email-change/{token}/confirm")

        assert confirmed.status_code == 204
        assert reused.status_code == 404
        assert target.get("/api/v1/me").status_code == 401

    with transaction(engine, DbContext.system()) as s:
        stored = s.execute(
            text("SELECT email FROM identity.user_account WHERE id = :id"), {"id": person.id}
        ).scalar_one()
    assert stored == new_email
    assert kc.get(f"/users/{person.id}")["email"] == new_email
    assert "foi trocado" in wait_for_email(stack.mailpit_url, person.email, old_notice_since)
    for p in (admin, person):
        kc.delete_user(str(p.id))


def test_link_expirado_nao_troca(
    app: FastAPI, engine: Engine, stack: Stack, kc: KeycloakAdmin
) -> None:
    org = create_organization(engine)
    admin = create_person(engine, kc, organizations={org: "administrator"})
    person = create_person(engine, kc, organizations={org: "supervisor"})
    new_email = _new_email()

    with logged_in(app, stack, admin) as admin_client:
        _, since = _request(admin_client, person.id, new_email)
    token = wait_for_email(stack.mailpit_url, new_email, since).split("/confirmar-email/")[1]
    token = token.split()[0]
    with transaction(engine, DbContext.system()) as s:
        s.execute(
            text(
                "UPDATE identity.email_change_request SET expires_at = now() - interval '1 minute'"
                " WHERE user_id = :id"
            ),
            {"id": person.id},
        )

    with TestClient(app, base_url="https://testserver") as anonymous:
        response = anonymous.post(f"/api/v1/email-change/{token}/confirm")

    assert response.status_code == 409
    assert kc.get(f"/users/{person.id}")["email"] == person.email
    for p in (admin, person):
        kc.delete_user(str(p.id))


def test_email_em_uso_por_outra_pessoa_e_recusado(
    app: FastAPI, engine: Engine, stack: Stack, kc: KeycloakAdmin
) -> None:
    org = create_organization(engine)
    admin = create_person(engine, kc, organizations={org: "administrator"})
    person = create_person(engine, kc, organizations={org: "supervisor"})

    with logged_in(app, stack, admin) as admin_client:
        response = admin_client.post(
            f"/api/v1/users/{person.id}/email-change",
            json={"new_email": admin.email},
            headers=csrf_headers(admin_client),
        )

    assert response.status_code == 409
    for p in (admin, person):
        kc.delete_user(str(p.id))
