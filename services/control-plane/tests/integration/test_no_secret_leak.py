"""Nenhum segredo em logs, respostas ou Audit Trail (T071; CS-007; RNF-005).

Percorre login (senha e código), convite de pessoa já cadastrada e troca de e-mail com os
logs do Control Plane capturados no formato de produção (JSON), e procura os valores
secretos usados: senha, código, tokens dos links, cookies de sessão e tokens JWT.
"""

from __future__ import annotations

import io
import logging
import re
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from cap_control_plane.core.db import DbContext, transaction
from cap_control_plane.core.logging import JsonFormatter
from cap_control_plane.identity.cookies import CSRF_COOKIE, SESSION_COOKIE
from tests.support.keycloak import BrowserLogin, KeycloakAdmin
from tests.support.mailpit import extract_code, wait_for_email
from tests.support.people import Person, create_organization, create_person, csrf_headers
from tests.support.stack import Stack

JWT = re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}")


@pytest.fixture
def captured_logs() -> Iterator[io.StringIO]:
    buffer = io.StringIO()
    handler = logging.StreamHandler(buffer)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    previous = root.level
    root.addHandler(handler)
    root.setLevel(logging.DEBUG)
    yield buffer
    root.removeHandler(handler)
    root.setLevel(previous)


def _login(client: TestClient, stack: Stack, person: Person) -> str:
    """Login completo; devolve o código de 6 dígitos usado."""
    start = client.get("/api/v1/auth/login", follow_redirects=False)
    browser = BrowserLogin(stack)
    since = datetime.now(UTC)
    step = browser.password(
        browser.open_url(start.headers["location"]), person.email, person.password
    )
    code = extract_code(wait_for_email(stack.mailpit_url, person.email, since))
    params = browser.code(step, code).callback_params
    assert params is not None
    callback = client.get("/api/v1/auth/callback", params=params, follow_redirects=False)
    assert callback.status_code == 303
    return code


def _link_token(email_text: str, path: str) -> str:
    match = re.search(rf"/{path}/([A-Za-z0-9_-]+)", email_text)
    assert match is not None, path
    return match.group(1)


def test_segredos_nao_aparecem_em_logs_respostas_nem_auditoria(
    app: FastAPI,
    engine: Engine,
    stack: Stack,
    kc: KeycloakAdmin,
    captured_logs: io.StringIO,
) -> None:
    org = create_organization(engine)
    admin = create_person(engine, kc, organizations={org: "administrator"})
    guest = create_person(engine, kc, organizations={create_organization(engine): "developer"})
    target = create_person(engine, kc, organizations={org: "supervisor"})
    responses: list[str] = []

    with TestClient(app, base_url="https://testserver") as client:
        code = _login(client, stack, admin)
        session_cookie = client.cookies.get(SESSION_COOKIE) or ""
        csrf_cookie = client.cookies.get(CSRF_COOKIE) or ""
        responses.append(client.get("/api/v1/me").text)

        since = datetime.now(UTC)
        invited = client.post(
            "/api/v1/invitations",
            json={"email": guest.email, "name": guest.name, "organization_id": str(org),
                  "profile": "supervisor"},
            headers=csrf_headers(client),
        )  # fmt: skip
        responses.append(invited.text)
        invitation_token = _link_token(
            wait_for_email(stack.mailpit_url, guest.email, since), "convites"
        )
        responses.append(client.get("/api/v1/invitations").text)

        new_email, since = f"novo-{uuid.uuid4().hex[:8]}@exemplo.com.br", datetime.now(UTC)
        changed = client.post(
            f"/api/v1/users/{target.id}/email-change",
            json={"new_email": new_email},
            headers=csrf_headers(client),
        )
        responses.append(changed.text)
        email_token = _link_token(
            wait_for_email(stack.mailpit_url, new_email, since), "confirmar-email"
        )
        responses.append(client.get(f"/api/v1/users/{target.id}").text)
        responses.append(client.get("/api/v1/audit-events", params={"limit": 200}).text)

    with transaction(engine, DbContext.system()) as s:
        audit = "\n".join(
            s.execute(
                text(
                    "SELECT concat_ws(' ', event_type, target_id, details::text)"
                    " FROM audit.audit_event WHERE actor_user_id IN (:a, :g, :t)"
                    " OR target_id IN (:sa, :sg, :st)"
                ),
                {"a": admin.id, "g": guest.id, "t": target.id,
                 "sa": str(admin.id), "sg": str(guest.id), "st": str(target.id)},
            ).scalars()
        )  # fmt: skip

    # Sem os horários: os microssegundos poderiam coincidir com o código de 6 dígitos.
    logs = re.sub(r'"timestamp": "[^"]*"', "", captured_logs.getvalue())
    assert logs, "nenhum log capturado"
    secrets = {
        "senha": admin.password,
        "código": code,
        "token do convite": invitation_token,
        "token da troca de e-mail": email_token,
        "cookie de sessão": session_cookie,
        "cookie anti-CSRF": csrf_cookie,
    }
    for where, content in (
        ("logs", logs), ("respostas", "\n".join(responses)), ("auditoria", audit),
    ):  # fmt: skip
        leaked = [name for name, value in secrets.items() if value and value in content]
        assert leaked == [], f"{leaked} em {where}"
        assert not JWT.search(content), f"token JWT em {where}"
    for p in (admin, guest, target):
        kc.delete_user(str(p.id))
