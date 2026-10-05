"""Gestão de organizações pelo Super Administrador (T060; US5; RF-012, RF-018, RF-025 a RF-027).

O primeiro acesso completo do convidado (link + senha + código) é coberto pelo E2E
(T062); aqui a ativação é feita pela mesma função que o login chama.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from cap_control_plane.audit.writer import Origin
from cap_control_plane.core.db import DbContext, transaction
from cap_control_plane.identity.activation import activate_on_first_login
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
def super_admin(engine: Engine, kc: KeycloakAdmin) -> Iterator[Person]:
    person = create_person(engine, kc, super_admin=True)
    yield person
    kc.delete_user(str(person.id))


@pytest.fixture
def super_client(app: FastAPI, stack: Stack, super_admin: Person) -> Iterator[TestClient]:
    with logged_in(app, stack, super_admin) as client:
        yield client


def _email() -> str:
    return f"resp-{uuid.uuid4().hex[:8]}@cliente.com.br"


def _org_status(engine: Engine, organization_id: uuid.UUID | str) -> str:
    with transaction(engine, DbContext.system()) as s:
        return str(
            s.execute(
                text("SELECT status::text FROM identity.organization WHERE id = :id"),
                {"id": organization_id},
            ).scalar_one()
        )


def _invite(client: TestClient, name: str, email: str) -> str:
    response = client.post(
        "/api/v1/organizations",
        json={"name": name, "admin_name": "Responsável", "admin_email": email},
        headers=csrf_headers(client),
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


def _events(engine: Engine, organization_id: str) -> list[tuple[str, bool]]:
    with transaction(engine, DbContext.system()) as s:
        rows = s.execute(
            text(
                "SELECT event_type, installation_scope FROM audit.audit_event"
                " WHERE organization_id = :o ORDER BY seq"
            ),
            {"o": organization_id},
        ).all()
    return [(r.event_type, r.installation_scope) for r in rows]


def test_convite_de_organizacao_nasce_pendente_e_ativa_com_o_administrador(
    super_client: TestClient, engine: Engine, stack: Stack, kc: KeycloakAdmin
) -> None:
    email, since = _email(), datetime.now(UTC)

    org = _invite(super_client, f"Cliente {uuid.uuid4().hex[:6]}", email)

    assert _org_status(engine, org) == "pending"
    assert "Você recebeu acesso" in wait_for_email(stack.mailpit_url, email, since)
    detail = super_client.get(f"/api/v1/organizations/{org}").json()
    assert [(a["email"], a["status"]) for a in detail["administrators"]] == [(email, "pending")]
    admin_id = uuid.UUID(detail["administrators"][0]["id"])

    activate_on_first_login(engine, admin_id, Origin())

    assert _org_status(engine, org) == "active"
    assert ("org.created", True) in _events(engine, org)
    assert ("org.activated", True) in _events(engine, org)
    kc.delete_user(str(admin_id))


def test_convite_de_organizacao_para_pessoa_ja_cadastrada_e_aceito_logado(
    super_client: TestClient, app: FastAPI, engine: Engine, stack: Stack, kc: KeycloakAdmin
) -> None:
    person = create_person(engine, kc, organizations={create_organization(engine): "developer"})
    since = datetime.now(UTC)

    org = _invite(super_client, f"Grupo {uuid.uuid4().hex[:6]}", person.email)

    link = wait_for_email(stack.mailpit_url, person.email, since)
    token = re.search(r"/convites/([A-Za-z0-9_-]+)", link)
    assert token is not None
    with logged_in(app, stack, person) as client:
        accepted = client.post(
            f"/api/v1/invitations/{token.group(1)}/accept", headers=csrf_headers(client)
        )
    assert accepted.status_code == 200, accepted.text
    assert _org_status(engine, org) == "active"
    kc.delete_user(str(person.id))


def test_so_o_super_administrador_cria_organizacoes(
    app: FastAPI, engine: Engine, stack: Stack, kc: KeycloakAdmin
) -> None:
    admin = create_person(engine, kc, organizations={create_organization(engine): "administrator"})
    with logged_in(app, stack, admin) as client:
        response = client.post(
            "/api/v1/organizations",
            json={"name": "Nova", "admin_name": "X", "admin_email": _email()},
            headers=csrf_headers(client),
        )

    assert response.status_code == 403
    with transaction(engine, DbContext.system()) as s:
        denied = s.execute(
            text(
                "SELECT count(*) FROM audit.audit_event WHERE actor_user_id = :u"
                " AND event_type = 'access.denied' AND target_id = '/api/v1/organizations'"
            ),
            {"u": admin.id},
        ).scalar_one()
    assert denied == 1
    kc.delete_user(str(admin.id))


def test_lista_com_filtros_renomeia_e_detecta_edicao_concorrente(
    super_client: TestClient, engine: Engine, kc: KeycloakAdmin
) -> None:
    org = create_organization(engine, f"Filtro {uuid.uuid4().hex[:6]}")
    admin = create_person(engine, kc, organizations={org: "administrator"})
    hidden = create_person(engine, kc, organizations={org: "supervisor"})

    by_admin = super_client.get("/api/v1/organizations", params={"q": admin.email}).json()
    active = super_client.get("/api/v1/organizations", params={"org_status": "active"}).json()
    assert [o["id"] for o in by_admin] == [str(org)]
    assert str(org) in {o["id"] for o in active}
    # Só os Administradores aparecem; o Supervisor não (RF-028).
    assert [a["email"] for a in by_admin[0]["administrators"]] == [admin.email]
    assert hidden.email not in str(by_admin)

    version = by_admin[0]["version"]
    renamed = super_client.patch(
        f"/api/v1/organizations/{org}",
        json={"name": f"Renomeada {uuid.uuid4().hex[:6]}"},
        headers={**csrf_headers(super_client), "If-Match": str(version)},
    )
    stale = super_client.patch(
        f"/api/v1/organizations/{org}",
        json={"name": f"Outra {uuid.uuid4().hex[:6]}"},
        headers={**csrf_headers(super_client), "If-Match": str(version)},
    )
    assert renamed.status_code == 204
    assert stale.status_code == 412
    for p in (admin, hidden):
        kc.delete_user(str(p.id))


def test_reenviar_e_cancelar_organizacao_pendente(
    super_client: TestClient, engine: Engine, stack: Stack, kc: KeycloakAdmin
) -> None:
    email = _email()
    org = _invite(super_client, f"Pendente {uuid.uuid4().hex[:6]}", email)
    since = datetime.now(UTC)

    resent = super_client.post(
        f"/api/v1/organizations/{org}/invitation/resend", headers=csrf_headers(super_client)
    )
    assert resent.status_code == 204
    assert "Você recebeu acesso" in wait_for_email(stack.mailpit_url, email, since)

    cancelled = super_client.post(
        f"/api/v1/organizations/{org}/cancel", headers=csrf_headers(super_client)
    )
    assert cancelled.status_code == 204
    assert _org_status(engine, org) == "cancelled"
    again = super_client.post(
        f"/api/v1/organizations/{org}/cancel", headers=csrf_headers(super_client)
    )
    assert again.status_code == 409
    user = kc.get("/users", email=email, exact="true")[0]
    kc.delete_user(user["id"])


def test_convite_para_email_de_super_administrador_e_recusado(
    super_client: TestClient, engine: Engine, kc: KeycloakAdmin
) -> None:
    other = create_person(engine, kc, super_admin=True)

    response = super_client.post(
        "/api/v1/organizations",
        json={"name": f"Seg {uuid.uuid4().hex[:6]}", "admin_name": "X", "admin_email": other.email},
        headers=csrf_headers(super_client),
    )

    assert response.status_code == 409
    kc.delete_user(str(other.id))


def test_administradores_desativar_reativar_e_ultimo_ativo(
    super_client: TestClient, engine: Engine, stack: Stack, kc: KeycloakAdmin
) -> None:
    org = create_organization(engine)
    first = create_person(engine, kc, organizations={org: "administrator"})
    analyst = create_person(engine, kc, organizations={org: "business_analyst"})
    headers = csrf_headers(super_client)
    base = f"/api/v1/organizations/{org}/administrators"

    last = super_client.post(f"{base}/{first.id}/disable", headers=headers)
    not_admin = super_client.post(f"{base}/{analyst.id}/disable", headers=headers)
    assert last.status_code == 409
    assert not_admin.status_code == 404  # o Super Administrador não vê outros perfis

    second_email, since = _email(), datetime.now(UTC)
    invited = super_client.post(
        base, json={"name": "Segundo", "email": second_email}, headers=headers
    )
    assert invited.status_code == 201
    assert "Você recebeu acesso" in wait_for_email(stack.mailpit_url, second_email, since)
    second_id = uuid.UUID(kc.get("/users", email=second_email, exact="true")[0]["id"])
    activate_on_first_login(engine, second_id, Origin())

    disabled = super_client.post(f"{base}/{first.id}/disable", headers=headers)
    assert disabled.status_code == 204
    assert kc.get(f"/users/{first.id}")["enabled"] is False
    enabled = super_client.post(f"{base}/{first.id}/enable", headers=headers)
    assert enabled.status_code == 204
    assert kc.get(f"/users/{first.id}")["enabled"] is True
    for user_id in (first.id, analyst.id, second_id):
        kc.delete_user(str(user_id))


def test_suspender_encerra_o_acesso_e_reativar_devolve(
    super_client: TestClient, app: FastAPI, engine: Engine, stack: Stack, kc: KeycloakAdmin
) -> None:
    org, other = create_organization(engine), create_organization(engine)
    member = create_person(engine, kc, organizations={org: "supervisor"})
    shared = create_person(engine, kc, organizations={org: "developer", other: "developer"})
    headers = csrf_headers(super_client)

    with logged_in(app, stack, member) as m, logged_in(app, stack, shared) as sh:
        switched = sh.put(
            "/api/v1/me/active-organization",
            json={"organization_id": str(org)},
            headers=csrf_headers(sh),
        )
        assert switched.status_code == 204, switched.text
        assert sh.get("/api/v1/me").json()["active_organization_id"] == str(org)
        suspended = super_client.post(f"/api/v1/organizations/{org}/suspend", headers=headers)
        assert suspended.status_code == 200
        assert suspended.json()["sessions_ended"] >= 2
        assert m.get("/api/v1/me").status_code == 401
        assert sh.get("/api/v1/me").status_code == 401
    assert kc.get(f"/users/{member.id}/sessions") == []

    # Quem tem outra organização ativa entra direto nela.
    with logged_in(app, stack, shared) as sh:
        me = sh.get("/api/v1/me").json()
        assert me["active_organization_id"] == str(other)
        assert [o["id"] for o in me["organizations"]] == [str(other)]

    reactivated = super_client.post(f"/api/v1/organizations/{org}/reactivate", headers=headers)
    assert reactivated.status_code == 204
    with logged_in(app, stack, member) as m:
        assert m.get("/api/v1/me").json()["active_organization_id"] == str(org)
    for p in (member, shared):
        kc.delete_user(str(p.id))


def test_troca_de_organizacao_so_para_vinculo_valido(
    app: FastAPI, engine: Engine, stack: Stack, kc: KeycloakAdmin
) -> None:
    org_a, org_b = create_organization(engine), create_organization(engine)
    outsider = create_organization(engine)
    person = create_person(engine, kc, organizations={org_a: "supervisor", org_b: "developer"})

    with logged_in(app, stack, person) as client:
        switched = client.put(
            "/api/v1/me/active-organization",
            json={"organization_id": str(org_b)},
            headers=csrf_headers(client),
        )
        me = client.get("/api/v1/me").json()
        refused = client.put(
            "/api/v1/me/active-organization",
            json={"organization_id": str(outsider)},
            headers=csrf_headers(client),
        )

    assert switched.status_code == 204
    assert me["active_organization_id"] == str(org_b)
    assert "developer" in [o["profile"] for o in me["organizations"] if o["id"] == str(org_b)]
    assert refused.status_code == 404
    kc.delete_user(str(person.id))
