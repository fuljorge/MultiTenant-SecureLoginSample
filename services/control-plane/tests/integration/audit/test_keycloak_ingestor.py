"""Importação dos eventos do Keycloak para o Audit Trail (T033; RF-005, RF-021, research R4)."""

from __future__ import annotations

import subprocess
import time
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from cap_control_plane.audit.keycloak_ingestor import KeycloakEventIngestor
from cap_control_plane.core.db import DbContext, transaction
from cap_control_plane.services import Services
from tests.support.keycloak import BrowserLogin, KeycloakAdmin
from tests.support.mailpit import extract_code, wait_for_email
from tests.support.people import Person, create_organization, create_person, login
from tests.support.stack import COMPOSE_DIR, Stack


@pytest.fixture
def person(engine: Engine, kc: KeycloakAdmin) -> Iterator[Person]:
    org = create_organization(engine)
    created = create_person(engine, kc, organizations={org: "supervisor"})
    yield created
    kc.delete_user(str(created.id))


@pytest.fixture
def ingestor(services: Services) -> KeycloakEventIngestor:
    return KeycloakEventIngestor(services)


def _audit_rows(engine: Engine, user_id: uuid.UUID) -> list[tuple[str, str, dict[str, object]]]:
    with transaction(engine, DbContext.system()) as s:
        rows = s.execute(
            text(
                "SELECT event_type, result, details FROM audit.audit_event"
                " WHERE source = 'keycloak' AND target_id = :uid ORDER BY seq"
            ),
            {"uid": str(user_id)},
        ).all()
    return [(r.event_type, r.result, r.details) for r in rows]


def _full_login(stack: Stack, person: Person) -> None:
    browser = BrowserLogin(stack)
    since = datetime.now(UTC)
    step = browser.password(browser.open(), person.email, person.password)
    browser.code(step, extract_code(wait_for_email(stack.mailpit_url, person.email, since)))


def test_importa_login_e_falha_sem_duplicar(
    ingestor: KeycloakEventIngestor, engine: Engine, stack: Stack, person: Person
) -> None:
    wrong = BrowserLogin(stack)
    wrong.password(wrong.open(), person.email, "senha-errada-123")
    _full_login(stack, person)

    ingestor.poll_once()
    ingestor.poll_once()

    rows = _audit_rows(engine, person.id)
    assert [r[0] for r in rows] == ["auth.login_failed", "auth.login"]
    assert rows[0][1] == "failure" and rows[0][2] == {"reason": "invalid_credentials"}
    assert rows[1][1] == "success"
    with transaction(engine, DbContext.system()) as s:
        last_login = s.execute(
            text("SELECT last_login_at FROM identity.user_account WHERE id = :id"),
            {"id": person.id},
        ).scalar_one()
    assert last_login is not None


def test_eventos_importados_nao_levam_email_nem_ip_na_cadeia(
    ingestor: KeycloakEventIngestor, engine: Engine, stack: Stack, person: Person
) -> None:
    _full_login(stack, person)

    ingestor.poll_once()

    with transaction(engine, DbContext.system()) as s:
        details = (
            s.execute(
                text("SELECT details::text FROM audit.audit_event WHERE target_id = :uid"),
                {"uid": str(person.id)},
            )
            .scalars()
            .all()
        )
    assert details
    assert all(person.email not in d and "redirect_uri" not in d for d in details)


def test_troca_de_senha_encerra_sessoes_do_bff_e_avisa_por_email(
    app: FastAPI,
    engine: Engine,
    ingestor: KeycloakEventIngestor,
    stack: Stack,
    person: Person,
    kc: KeycloakAdmin,
) -> None:
    with TestClient(app, base_url="https://testserver") as studio:
        login(studio, stack, person)
        assert studio.get("/api/v1/me").status_code == 200

        # A pessoa troca a senha pelo próprio Keycloak (ação obrigatória no próximo login).
        kc.require_action(str(person.id), "UPDATE_PASSWORD")
        browser = BrowserLogin(stack)
        since = datetime.now(UTC)
        step = browser.password(browser.open(), person.email, person.password)
        step = browser.code(
            step, extract_code(wait_for_email(stack.mailpit_url, person.email, since))
        )
        new_password = f"Nova-Senha-{uuid.uuid4().hex[:12]}"
        step = browser.follow(step)
        browser.submit(step, {"password-new": new_password, "password-confirm": new_password})
        notice_since = datetime.now(UTC)

        ingestor.poll_once()

        assert studio.get("/api/v1/me").status_code == 401
        notice = wait_for_email(stack.mailpit_url, person.email, notice_since)
        assert "foi alterada" in notice
        # Também acabam as sessões SSO do Keycloak (sem login automático em outro navegador).
        assert kc.get(f"/users/{person.id}/sessions") == []
        # Uma troca, um registro (o Keycloak emite dois eventos para a mesma troca).
        changes = [r for r in _audit_rows(engine, person.id) if r[0] == "auth.password_changed"]
        assert len(changes) == 1


def test_smtp_indisponivel_impede_o_login_e_fica_no_log(stack: Stack, person: Person) -> None:
    compose = ["docker", "compose", "-f", str(COMPOSE_DIR / "docker-compose.yml")]
    started = datetime.now(UTC)
    subprocess.run([*compose, "stop", "mailpit"], check=True, capture_output=True)  # noqa: S603
    try:
        browser = BrowserLogin(stack)
        step = browser.password(browser.open(), person.email, person.password)
        assert step.asks_for_email_code
        assert step.authorization_code is None
        logs = subprocess.run(  # noqa: S603
            [*compose, "logs", "--since", started.isoformat(), "keycloak"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        assert "Failed to send" in logs
    finally:
        subprocess.run([*compose, "start", "mailpit"], check=True, capture_output=True)  # noqa: S603
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            try:
                if httpx.get(f"{stack.mailpit_url}/readyz", timeout=2).status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(1)


def test_senha_inicial_da_ativacao_nao_encerra_o_primeiro_login(
    app: FastAPI,
    engine: Engine,
    ingestor: KeycloakEventIngestor,
    stack: Stack,
    person: Person,
    kc: KeycloakAdmin,
) -> None:
    """Bug: a senha definida na ativação era tratada como troca de senha.

    O worker encerrava a sessão aberta logo depois e avisava "sua senha foi alterada". A
    senha de quem ainda não fez nenhum login é a inicial: só é auditada.
    """
    kc.require_action(str(person.id), "UPDATE_PASSWORD")
    browser = BrowserLogin(stack)
    since = datetime.now(UTC)
    step = browser.password(browser.open(), person.email, person.password)
    step = browser.code(step, extract_code(wait_for_email(stack.mailpit_url, person.email, since)))
    initial_password = f"Senha-Inicial-{uuid.uuid4().hex[:12]}"
    browser.submit(
        browser.follow(step),
        {"password-new": initial_password, "password-confirm": initial_password},
    )
    activated = Person(person.id, person.email, initial_password, person.name)
    notice_since = datetime.now(UTC)

    with TestClient(app, base_url="https://testserver") as studio:
        login(studio, stack, activated)
        ingestor.poll_once()

        assert studio.get("/api/v1/me").status_code == 200
    assert kc.get(f"/users/{person.id}/sessions") != []
    notices = httpx.get(
        f"{stack.mailpit_url}/api/v1/search",
        params={"query": f'to:{person.email} "foi alterada"'},
    ).json()["messages"]
    assert [m for m in notices if m["Created"] >= notice_since.isoformat()[:19]] == []
    changes = [r for r in _audit_rows(engine, person.id) if r[0] == "auth.password_changed"]
    assert [r[2] for r in changes] == [{"initial": True}]
