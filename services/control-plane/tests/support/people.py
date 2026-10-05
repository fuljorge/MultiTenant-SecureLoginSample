"""Cadastro de pessoas e organizações para testes, no Keycloak e no Control Plane."""

from __future__ import annotations

import secrets
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from cap_control_plane.core.db import DbContext, transaction
from cap_control_plane.identity.cookies import CSRF_COOKIE, CSRF_HEADER
from tests.support.keycloak import BrowserLogin, KeycloakAdmin
from tests.support.mailpit import extract_code, wait_for_email
from tests.support.stack import Stack


@dataclass(frozen=True)
class Person:
    id: uuid.UUID
    email: str
    password: str
    name: str


def create_organization(
    engine: Engine, name: str | None = None, *, status: str = "active"
) -> uuid.UUID:
    """Organização pronta para uso (ativa, salvo pedido); o convite real é testado na US5."""
    org_id = uuid.uuid4()
    label = name or f"Org {org_id.hex[:6]}"
    with transaction(engine, DbContext.system()) as s:
        s.execute(
            text(
                "INSERT INTO identity.organization (id, name, slug, status)"
                " VALUES (:id, :n, :s, CAST(:status AS identity.organization_status))"
            ),
            {"id": org_id, "n": label, "s": f"org-{org_id.hex[:12]}", "status": status},
        )
    return org_id


def create_person(
    engine: Engine,
    admin: KeycloakAdmin,
    *,
    organizations: dict[uuid.UUID, str] | None = None,
    super_admin: bool = False,
    status: str = "active",
) -> Person:
    """Pessoa com senha no Keycloak e vínculos ativos no Control Plane."""
    email = f"pessoa-{secrets.token_hex(5)}@exemplo.com.br"
    password = f"Senha-Forte-{secrets.token_urlsafe(12)}"
    user_id = uuid.UUID(admin.create_user(email, password))
    name = f"Pessoa {email[7:12]}"
    with transaction(engine, DbContext.system()) as s:
        s.execute(
            text(
                "INSERT INTO identity.user_account (id, email, name, status)"
                " VALUES (:id, :email, :name, :status)"
            ),
            {"id": user_id, "email": email, "name": name, "status": status},
        )
        for org_id, profile in (organizations or {}).items():
            s.execute(
                text(
                    "INSERT INTO identity.membership (organization_id, user_id, profile, status)"
                    " VALUES (:org, :user, :profile, 'active')"
                ),
                {"org": org_id, "user": user_id, "profile": profile},
            )
        if super_admin:
            s.execute(
                text("INSERT INTO identity.super_admin (user_id) VALUES (:id)"),
                {"id": user_id},
            )
    return Person(user_id, email, password, name)


def authorize(client: TestClient, stack: Stack, person: Person) -> dict[str, str]:
    """Do /auth/login até o retorno do Keycloak; devolve code e state para o callback."""
    start = client.get("/api/v1/auth/login", follow_redirects=False)
    assert start.status_code == 303, start.text
    browser = BrowserLogin(stack)
    since = datetime.now(UTC)
    step = browser.password(
        browser.open_url(start.headers["location"]), person.email, person.password
    )
    code = extract_code(wait_for_email(stack.mailpit_url, person.email, since))
    params = browser.code(step, code).callback_params
    assert params is not None
    return params


def login(client: TestClient, stack: Stack, person: Person) -> TestClient:
    """Login completo pelo BFF: Control Plane → Keycloak (senha e código) → callback."""
    callback = client.get(
        "/api/v1/auth/callback", params=authorize(client, stack, person), follow_redirects=False
    )
    assert callback.status_code == 303, callback.text
    assert "/entrar/erro" not in callback.headers["location"], callback.headers["location"]
    return client


def csrf_headers(client: TestClient) -> dict[str, str]:
    return {CSRF_HEADER: client.cookies.get(CSRF_COOKIE) or ""}


@contextmanager
def logged_in(app: FastAPI, stack: Stack, person: Person) -> Iterator[TestClient]:
    """Cliente HTTPS com a pessoa logada pelo BFF (senha + código)."""
    with TestClient(app, base_url="https://testserver") as client:
        login(client, stack, person)
        yield client
