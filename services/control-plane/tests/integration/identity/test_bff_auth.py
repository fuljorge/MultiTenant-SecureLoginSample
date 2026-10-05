"""Fluxo de login do BFF (T032; RF-001, RF-006, RNF-005, research R3)."""

from __future__ import annotations

import threading
import time
import uuid
from collections.abc import Iterator

import httpx
import pytest
import uvicorn
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from cap_control_plane.identity.cookies import CSRF_COOKIE, SESSION_COOKIE
from cap_control_plane.services import Services
from tests.support.keycloak import KeycloakAdmin
from tests.support.people import (
    Person,
    authorize,
    create_organization,
    create_person,
    csrf_headers,
    login,
)
from tests.support.stack import Stack


@pytest.fixture
def org(engine: Engine) -> uuid.UUID:
    return create_organization(engine)


@pytest.fixture
def person(engine: Engine, kc: KeycloakAdmin, org: uuid.UUID) -> Iterator[Person]:
    created = create_person(engine, kc, organizations={org: "agent_designer"})
    yield created
    kc.delete_user(str(created.id))


def _set_cookie_headers(response_headers: list[str], name: str) -> str:
    return next(h for h in response_headers if h.startswith(f"{name}="))


def test_login_cria_sessao_com_cookies_seguros(
    client: TestClient, stack: Stack, person: Person
) -> None:
    start = client.get("/api/v1/auth/login", follow_redirects=False)
    location = start.headers["location"]

    assert "code_challenge_method=S256" in location
    assert "state=" in location and "nonce=" in location

    # Reaproveita o fluxo completo e inspeciona os cookies definidos no callback.
    login(client, stack, person)
    session_cookie = client.cookies.get(SESSION_COOKIE)
    assert session_cookie and len(session_cookie) >= 43


def test_atributos_dos_cookies(client: TestClient, stack: Stack, person: Person) -> None:
    params = authorize(client, stack, person)
    callback = client.get("/api/v1/auth/callback", params=params, follow_redirects=False)
    headers = callback.headers.get_list("set-cookie")

    session = _set_cookie_headers(headers, SESSION_COOKIE).lower()
    csrf = _set_cookie_headers(headers, CSRF_COOKIE).lower()
    for cookie in (session, csrf):
        assert "secure" in cookie
        assert "path=/" in cookie
        assert "samesite=lax" in cookie
        assert "domain=" not in cookie
    assert "httponly" in session
    assert "httponly" not in csrf
    assert callback.headers["location"] == "http://localhost:3000/"


def test_me_traz_organizacao_ativa_e_permissoes(
    client: TestClient, stack: Stack, person: Person, org: uuid.UUID
) -> None:
    login(client, stack, person)

    me = client.get("/api/v1/me").json()

    assert me["email"] == person.email
    assert me["active_organization_id"] == str(org)
    assert me["organizations"] == [
        {"id": str(org), "name": me["organizations"][0]["name"], "profile": "agent_designer"}
    ]
    assert "agents:publish" in me["permissions"]
    assert "users:manage" not in me["permissions"]


def test_sem_sessao_responde_401(client: TestClient) -> None:
    assert client.get("/api/v1/me").status_code == 401


def test_callback_sem_cookie_de_login_e_recusado(
    client: TestClient, app: FastAPI, stack: Stack, person: Person
) -> None:
    params = authorize(client, stack, person)

    # Outro navegador (sem o cookie que liga a tentativa) tenta usar o mesmo retorno.
    with TestClient(app, base_url="https://testserver") as attacker:
        response = attacker.get("/api/v1/auth/callback", params=params, follow_redirects=False)

    assert "/entrar/erro?motivo=expirado" in response.headers["location"]
    assert SESSION_COOKIE not in attacker.cookies


def test_logout_exige_csrf_e_encerra_a_sessao(
    client: TestClient, stack: Stack, person: Person
) -> None:
    login(client, stack, person)

    without_csrf = client.post("/api/v1/auth/logout")
    logout = client.post("/api/v1/auth/logout", headers=csrf_headers(client))

    assert without_csrf.status_code == 403
    assert logout.status_code == 204
    assert client.get("/api/v1/me").status_code == 401


def test_logout_encerra_a_sessao_mesmo_com_o_keycloak_falhando(
    client: TestClient, stack: Stack, person: Person, services: Services,
    monkeypatch: pytest.MonkeyPatch,
) -> None:  # fmt: skip
    """Bug: com o Keycloak lento ou fora do ar, "Sair" deixava a sessão do Studio viva."""
    login(client, stack, person)

    def keycloak_down(_: str) -> None:
        raise httpx.ConnectError("Keycloak indisponível")

    monkeypatch.setattr(services.keycloak_admin, "delete_session", keycloak_down)
    logout = client.post("/api/v1/auth/logout", headers=csrf_headers(client))

    assert logout.status_code == 204
    assert client.get("/api/v1/me").status_code == 401


def test_lista_e_encerra_as_proprias_sessoes(app: FastAPI, stack: Stack, person: Person) -> None:
    with (
        TestClient(app, base_url="https://testserver") as first,
        TestClient(app, base_url="https://testserver") as second,
    ):
        login(first, stack, person)
        login(second, stack, person)

        sessions = first.get("/api/v1/me/sessions").json()
        other = next(s for s in sessions if not s["current"])
        ended = first.delete(f"/api/v1/me/sessions/{other['id']}", headers=csrf_headers(first))

        assert len(sessions) == 2
        assert ended.status_code == 204
        assert second.get("/api/v1/me").status_code == 401
        assert first.get("/api/v1/me").status_code == 200


@pytest.fixture(scope="module")
def live_server(app: FastAPI) -> Iterator[str]:
    """Servidor real na porta 8000, alcançável pelo Keycloak (back-channel logout)."""
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=8000, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.1)
    yield "http://127.0.0.1:8000"
    server.should_exit = True
    thread.join(timeout=10)


def test_back_channel_logout_encerra_a_sessao_do_bff(
    live_server: str, client: TestClient, stack: Stack, person: Person, kc: KeycloakAdmin
) -> None:
    login(client, stack, person)
    assert client.get("/api/v1/me").status_code == 200

    # Encerrar as sessões no Keycloak dispara o back-channel logout para o Control Plane.
    kc.logout_user(str(person.id))

    deadline = time.monotonic() + 10
    while client.get("/api/v1/me").status_code == 200 and time.monotonic() < deadline:
        time.sleep(0.5)
    assert client.get("/api/v1/me").status_code == 401
