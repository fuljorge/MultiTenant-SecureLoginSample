"""Gestão de usuários pelo Administrador (T046; US3; RF-009 a RF-012, RF-017)."""

from __future__ import annotations

import threading
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
def org(engine: Engine) -> uuid.UUID:
    return create_organization(engine)


@pytest.fixture
def admin(engine: Engine, kc: KeycloakAdmin, org: uuid.UUID) -> Iterator[Person]:
    person = create_person(engine, kc, organizations={org: "administrator"})
    yield person
    kc.delete_user(str(person.id))


@pytest.fixture
def admin_client(app: FastAPI, stack: Stack, admin: Person) -> Iterator[TestClient]:
    with logged_in(app, stack, admin) as client:
        yield client


def _status(engine: Engine, user_id: uuid.UUID) -> tuple[str, list[str]]:
    with transaction(engine, DbContext.system()) as s:
        status = s.execute(
            text("SELECT status FROM identity.user_account WHERE id = :id"), {"id": user_id}
        ).scalar_one()
        memberships = (
            s.execute(
                text("SELECT status FROM identity.membership WHERE user_id = :id"), {"id": user_id}
            )
            .scalars()
            .all()
        )
    return status, list(memberships)


def test_convite_de_pessoa_nova_cria_conta_pendente_e_envia_ativacao(
    admin_client: TestClient, engine: Engine, stack: Stack, kc: KeycloakAdmin, org: uuid.UUID
) -> None:
    email, since = f"nova-{uuid.uuid4().hex[:8]}@cliente.com.br", datetime.now(UTC)

    response = admin_client.post(
        "/api/v1/invitations",
        json={"email": email, "name": "Nova Pessoa", "organization_id": str(org),
              "profile": "supervisor"},
        headers=csrf_headers(admin_client),
    )  # fmt: skip

    assert response.status_code == 201, response.text
    created = kc.get("/users", email=email, exact="true")[0]
    assert _status(engine, uuid.UUID(created["id"])) == ("invited", ["pending"])
    assert "Você recebeu acesso" in wait_for_email(stack.mailpit_url, email, since)
    pending = admin_client.get("/api/v1/invitations").json()
    assert [i["email"] for i in pending if not i["existing_person"]] == [email]
    kc.delete_user(created["id"])


def test_convite_de_pessoa_ja_cadastrada_e_aceito_logado(
    admin_client: TestClient,
    app: FastAPI,
    engine: Engine,
    stack: Stack,
    kc: KeycloakAdmin,
    org: uuid.UUID,
) -> None:
    other_org = create_organization(engine)
    person = create_person(engine, kc, organizations={other_org: "developer"})
    since = datetime.now(UTC)

    response = admin_client.post(
        "/api/v1/invitations",
        json={"email": person.email, "name": person.name, "organization_id": str(org),
              "profile": "business_analyst"},
        headers=csrf_headers(admin_client),
    )  # fmt: skip
    assert response.status_code == 201, response.text
    text_ = wait_for_email(stack.mailpit_url, person.email, since)
    token = text_.split("/convites/")[1].split()[0]

    with logged_in(app, stack, person) as invited:
        accepted = invited.post(
            f"/api/v1/invitations/{token}/accept", headers=csrf_headers(invited)
        )
        reused = invited.post(f"/api/v1/invitations/{token}/accept", headers=csrf_headers(invited))
        orgs = {o["id"]: o["profile"] for o in invited.get("/api/v1/me").json()["organizations"]}

    assert accepted.json() == {"organization_id": str(org)}
    assert reused.status_code == 404
    assert orgs == {str(other_org): "developer", str(org): "business_analyst"}
    kc.delete_user(str(person.id))


def test_token_de_convite_nao_vale_para_outra_pessoa(
    admin_client: TestClient,
    app: FastAPI,
    engine: Engine,
    stack: Stack,
    kc: KeycloakAdmin,
    org: uuid.UUID,
) -> None:
    invited = create_person(engine, kc, organizations={create_organization(engine): "developer"})
    intruder = create_person(engine, kc, organizations={create_organization(engine): "developer"})
    since = datetime.now(UTC)
    admin_client.post(
        "/api/v1/invitations",
        json={"email": invited.email, "name": invited.name, "organization_id": str(org),
              "profile": "supervisor"},
        headers=csrf_headers(admin_client),
    )  # fmt: skip
    token = (
        wait_for_email(stack.mailpit_url, invited.email, since).split("/convites/")[1].split()[0]
    )

    with logged_in(app, stack, intruder) as client:
        response = client.post(f"/api/v1/invitations/{token}/accept", headers=csrf_headers(client))

    assert response.status_code == 404
    for p in (invited, intruder):
        kc.delete_user(str(p.id))


def test_revogar_convite_de_pessoa_nova_impede_a_ativacao(
    admin_client: TestClient, engine: Engine, kc: KeycloakAdmin, org: uuid.UUID
) -> None:
    email = f"revogada-{uuid.uuid4().hex[:8]}@cliente.com.br"
    invitation = admin_client.post(
        "/api/v1/invitations",
        json={"email": email, "name": "Revogada", "organization_id": str(org),
              "profile": "supervisor"},
        headers=csrf_headers(admin_client),
    ).json()  # fmt: skip

    revoked = admin_client.delete(
        f"/api/v1/invitations/{invitation['id']}", headers=csrf_headers(admin_client)
    )

    user = kc.get("/users", email=email, exact="true")[0]
    assert revoked.status_code == 204
    assert _status(engine, uuid.UUID(user["id"])) == ("disabled", ["removed"])
    assert user["enabled"] is False
    kc.delete_user(user["id"])


def test_mudanca_de_perfil_vale_na_proxima_requisicao(
    admin_client: TestClient, app: FastAPI, engine: Engine, stack: Stack, kc: KeycloakAdmin,
    org: uuid.UUID,
) -> None:  # fmt: skip
    person = create_person(engine, kc, organizations={org: "supervisor"})
    with logged_in(app, stack, person) as target:
        before = set(target.get("/api/v1/me").json()["permissions"])

        changed = admin_client.patch(
            f"/api/v1/users/{person.id}/memberships/{org}",
            json={"profile": "agent_designer"},
            headers=csrf_headers(admin_client),
        )
        after = set(target.get("/api/v1/me").json()["permissions"])

    assert changed.status_code == 204
    assert "agents:publish" not in before
    assert "agents:publish" in after
    kc.delete_user(str(person.id))


def test_edicao_concorrente_responde_412(
    admin_client: TestClient, engine: Engine, kc: KeycloakAdmin, org: uuid.UUID
) -> None:
    person = create_person(engine, kc, organizations={org: "supervisor"})
    version = admin_client.get(f"/api/v1/users/{person.id}").json()["memberships"][0]["version"]
    url = f"/api/v1/users/{person.id}/memberships/{org}"

    first = admin_client.patch(
        url, json={"profile": "developer"},
        headers={**csrf_headers(admin_client), "If-Match": f'"{version}"'},
    )  # fmt: skip
    stale = admin_client.patch(
        url, json={"profile": "business_analyst"},
        headers={**csrf_headers(admin_client), "If-Match": f'"{version}"'},
    )  # fmt: skip

    assert first.status_code == 204
    assert stale.status_code == 412
    kc.delete_user(str(person.id))


def test_desativar_encerra_sessoes_e_reativar_devolve_o_acesso(
    admin_client: TestClient, app: FastAPI, engine: Engine, stack: Stack, kc: KeycloakAdmin,
    org: uuid.UUID,
) -> None:  # fmt: skip
    person = create_person(engine, kc, organizations={org: "supervisor"})
    with logged_in(app, stack, person) as target:
        disabled = admin_client.post(
            f"/api/v1/users/{person.id}/disable", headers=csrf_headers(admin_client)
        )
        assert target.get("/api/v1/me").status_code == 401

    assert disabled.status_code == 204
    assert kc.get(f"/users/{person.id}")["enabled"] is False
    assert kc.get(f"/users/{person.id}/sessions") == []
    enabled = admin_client.post(
        f"/api/v1/users/{person.id}/enable", headers=csrf_headers(admin_client)
    )
    assert enabled.status_code == 204
    assert _status(engine, person.id)[0] == "active"
    assert kc.get(f"/users/{person.id}")["enabled"] is True
    kc.delete_user(str(person.id))


def test_desativar_pessoa_de_duas_organizacoes_tira_so_o_acesso_a_esta(
    admin_client: TestClient, app: FastAPI, engine: Engine, stack: Stack, kc: KeycloakAdmin,
    org: uuid.UUID,
) -> None:  # fmt: skip
    """Plano §4.4: uma organização não tira o acesso da pessoa a outra."""
    other = create_organization(engine)
    shared = create_person(engine, kc, organizations={org: "supervisor", other: "developer"})

    response = admin_client.post(
        f"/api/v1/users/{shared.id}/disable", headers=csrf_headers(admin_client)
    )

    assert response.status_code == 204
    with transaction(engine, DbContext.system()) as s:
        statuses = dict(
            s.execute(
                text(
                    "SELECT organization_id, status::text FROM identity.membership"
                    " WHERE user_id = :u"
                ),
                {"u": shared.id},
            ).all()
        )
    assert statuses == {org: "disabled", other: "active"}
    assert _status(engine, shared.id)[0] == "active"
    assert kc.get(f"/users/{shared.id}")["enabled"] is True
    listed = admin_client.get("/api/v1/users", params={"user_status": "disabled"}).json()
    assert [u["email"] for u in listed] == [shared.email]
    with logged_in(app, stack, shared) as client:
        assert client.get("/api/v1/me").json()["active_organization_id"] == str(other)
    kc.delete_user(str(shared.id))


def test_listagem_com_filtros_e_restrita_a_organizacao(
    admin_client: TestClient, engine: Engine, kc: KeycloakAdmin, org: uuid.UUID
) -> None:
    supervisor = create_person(engine, kc, organizations={org: "supervisor"})
    outsider = create_person(engine, kc, organizations={create_organization(engine): "supervisor"})

    everyone = {u["email"] for u in admin_client.get("/api/v1/users").json()}
    supervisors = admin_client.get("/api/v1/users", params={"profile": "supervisor"}).json()
    by_name = admin_client.get("/api/v1/users", params={"q": supervisor.name}).json()

    assert supervisor.email in everyone
    assert outsider.email not in everyone
    assert [u["email"] for u in supervisors] == [supervisor.email]
    assert [u["email"] for u in by_name] == [supervisor.email]
    assert admin_client.get(f"/api/v1/users/{outsider.id}").status_code == 404
    for p in (supervisor, outsider):
        kc.delete_user(str(p.id))


def test_ultimo_administrador_da_organizacao_mesmo_com_desativacoes_simultaneas(
    app: FastAPI, engine: Engine, stack: Stack, kc: KeycloakAdmin
) -> None:
    """RF-012: a organização nunca fica sem Administrador ativo."""
    org = create_organization(engine)
    first = create_person(engine, kc, organizations={org: "administrator"})
    second = create_person(engine, kc, organizations={org: "administrator"})

    results: dict[str, int] = {}
    with logged_in(app, stack, first) as a, logged_in(app, stack, second) as b:
        barrier = threading.Barrier(2)

        def disable(name: str, client: TestClient, target: Person) -> None:
            barrier.wait()
            results[name] = client.post(
                f"/api/v1/users/{target.id}/disable", headers=csrf_headers(client)
            ).status_code

        threads = [
            threading.Thread(target=disable, args=("a", a, second)),
            threading.Thread(target=disable, args=("b", b, first)),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

    assert sorted(results.values()) == [204, 409]
    active = [p for p in (first, second) if _status(engine, p.id)[0] == "active"]
    assert len(active) == 1
    for p in (first, second):
        kc.delete_user(str(p.id))


def test_rebaixar_o_ultimo_administrador_e_recusado(
    admin_client: TestClient, admin: Person, org: uuid.UUID
) -> None:
    response = admin_client.patch(
        f"/api/v1/users/{admin.id}/memberships/{org}",
        json={"profile": "supervisor"},
        headers=csrf_headers(admin_client),
    )

    assert response.status_code == 409
