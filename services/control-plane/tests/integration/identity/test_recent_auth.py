"""Reautenticação recente (T094; RF-031; plano §4.12)."""

from __future__ import annotations

import time
import uuid
from collections.abc import Iterator
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from cap_control_plane.identity.cookies import SESSION_COOKIE
from cap_control_plane.services import Services
from tests.support.keycloak import KeycloakAdmin
from tests.support.people import (
    Person,
    create_organization,
    create_person,
    csrf_headers,
    logged_in,
    login,
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


def _age_login(services: Services, client: TestClient, seconds: float) -> None:
    """Faz o último login parecer antigo, direto na sessão do BFF."""
    sid = client.cookies.get(SESSION_COOKIE)
    assert sid
    session = services.sessions.get(sid)
    assert session is not None and session.auth_time > 0
    session.auth_time = time.time() - seconds
    services.sessions.save(session)


def test_acao_sensivel_com_login_antigo_pede_reautenticacao_e_nao_muda_nada(
    app: FastAPI, services: Services, stack: Stack, engine: Engine, kc: KeycloakAdmin,
    admin: Person, org: uuid.UUID,
) -> None:  # fmt: skip
    member = create_person(engine, kc, organizations={org: "supervisor"})
    with logged_in(app, stack, admin) as client:
        _age_login(services, client, 16 * 60)

        response = client.post(f"/api/v1/users/{member.id}/disable", headers=csrf_headers(client))
        detail = client.get(f"/api/v1/users/{member.id}").json()

    assert response.status_code == 401
    assert response.json()["code"] == "reauth_required"
    assert detail["status"] == "active"  # leitura não exige login recente
    kc.delete_user(str(member.id))


def test_acao_sensivel_com_login_recente_segue(
    app: FastAPI, services: Services, stack: Stack, engine: Engine, kc: KeycloakAdmin,
    admin: Person, org: uuid.UUID,
) -> None:  # fmt: skip
    member = create_person(engine, kc, organizations={org: "supervisor"})
    with logged_in(app, stack, admin) as client:
        _age_login(services, client, 14 * 60)

        response = client.post(f"/api/v1/users/{member.id}/disable", headers=csrf_headers(client))

    assert response.status_code == 204
    kc.delete_user(str(member.id))


def test_sem_permissao_continua_403_antes_da_reautenticacao(
    app: FastAPI, services: Services, stack: Stack, engine: Engine, kc: KeycloakAdmin,
    org: uuid.UUID,
) -> None:  # fmt: skip
    analyst = create_person(engine, kc, organizations={org: "business_analyst"})
    with logged_in(app, stack, analyst) as client:
        _age_login(services, client, 60 * 60)
        response = client.post(
            f"/api/v1/users/{uuid.uuid4()}/disable", headers=csrf_headers(client)
        )

    assert response.status_code == 403
    kc.delete_user(str(analyst.id))


def test_reauth_exige_senha_e_codigo_e_substitui_a_sessao(
    app: FastAPI, services: Services, stack: Stack, admin: Person
) -> None:
    with TestClient(app, base_url="https://testserver") as client:
        login(client, stack, admin)
        old_sid = client.cookies.get(SESSION_COOKIE)
        _age_login(services, client, 20 * 60)

        start = client.get(
            "/api/v1/auth/login",
            params={"reauth": "1", "return_to": "/admin/usuarios"},
            follow_redirects=False,
        )
        query = parse_qs(urlparse(start.headers["location"]).query)
        assert query["prompt"] == ["login"]
        assert query["max_age"] == ["0"]

        login(client, stack, admin)  # nova autenticação completa (senha e código)
        new_sid = client.cookies.get(SESSION_COOKIE)
        new_session = services.sessions.get(new_sid or "")

    assert new_sid and new_sid != old_sid
    assert services.sessions.get(old_sid or "") is None
    assert new_session is not None and time.time() - new_session.auth_time < 120


def test_troca_de_senha_sempre_reautentica(app: FastAPI, stack: Stack, admin: Person) -> None:
    with logged_in(app, stack, admin) as client:
        start = client.get("/api/v1/auth/password", follow_redirects=False)

    query = parse_qs(urlparse(start.headers["location"]).query)
    assert query["kc_action"] == ["UPDATE_PASSWORD"]
    assert query["max_age"] == ["0"]


def test_renovar_tokens_nao_muda_o_momento_do_login(
    app: FastAPI, services: Services, stack: Stack, admin: Person
) -> None:
    with logged_in(app, stack, admin) as client:
        sid = client.cookies.get(SESSION_COOKIE) or ""
        session = services.sessions.get(sid)
        assert session is not None
        before = session.auth_time

        services.sessions.replace_tokens(session, {"access_token": "novo"})

        after = services.sessions.get(sid)
    assert after is not None and after.auth_time == before
