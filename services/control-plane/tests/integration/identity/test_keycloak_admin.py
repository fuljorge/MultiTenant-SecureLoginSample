"""Cliente da Admin REST API do Keycloak (T030; plano §4.3, §4.4, §4.7, §4.8)."""

from __future__ import annotations

import secrets
import time
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest

from cap_control_plane.core.settings import Settings
from cap_control_plane.identity.keycloak_admin import KeycloakAdminClient
from tests.support.keycloak import BrowserLogin
from tests.support.mailpit import extract_code, wait_for_email
from tests.support.stack import Stack


@pytest.fixture(scope="module")
def client(settings: Settings) -> KeycloakAdminClient:
    return KeycloakAdminClient(settings)


@pytest.fixture
def new_user(client: KeycloakAdminClient) -> Iterator[tuple[str, str]]:
    email = f"admin-api-{secrets.token_hex(4)}@exemplo.com.br"
    user_id = client.create_user(email)
    yield user_id, email
    client.delete_user(user_id)


def test_cria_usuario_e_encontra_pelo_email(
    client: KeycloakAdminClient, new_user: tuple[str, str]
) -> None:
    user_id, email = new_user

    found = client.find_user_by_email(email.upper())

    assert found is not None
    assert found["id"] == user_id
    assert found["requiredActions"] == ["UPDATE_PASSWORD"]


def test_envia_email_de_ativacao_em_portugues(
    client: KeycloakAdminClient, new_user: tuple[str, str], stack: Stack
) -> None:
    user_id, email = new_user
    since = datetime.now(UTC)

    client.send_activation_email(user_id, lifespan_seconds=72 * 3600)

    text = wait_for_email(stack.mailpit_url, email, since)
    assert "Você recebeu acesso ao SecureLogin" in text
    assert "/idp/realms/cap/login-actions/action-token" in text


def test_desativa_e_encerra_sessoes(
    client: KeycloakAdminClient, stack: Stack, new_user: tuple[str, str]
) -> None:
    user_id, email = new_user
    password = f"Senha-Forte-{secrets.token_urlsafe(10)}"
    client.set_password(user_id, password)
    browser = BrowserLogin(stack)
    since = datetime.now(UTC)
    step = browser.password(browser.open(), email, password)
    browser.code(step, extract_code(wait_for_email(stack.mailpit_url, email, since)))
    assert client.session_count(user_id) == 1

    client.set_enabled(user_id, enabled=False)
    client.logout(user_id)

    assert client.session_count(user_id) == 0
    assert client.get_user(user_id)["enabled"] is False


def test_altera_email(client: KeycloakAdminClient, new_user: tuple[str, str]) -> None:
    user_id, _ = new_user
    new_email = f"novo-{secrets.token_hex(4)}@exemplo.com.br"

    client.update_email(user_id, new_email)

    user = client.get_user(user_id)
    assert user["email"] == new_email
    assert user["username"] == new_email


def test_le_eventos_de_login_e_estado_de_bloqueio(
    client: KeycloakAdminClient, stack: Stack, new_user: tuple[str, str]
) -> None:
    user_id, email = new_user
    start_ms = int(time.time() * 1000)
    browser = BrowserLogin(stack)
    browser.password(browser.open(), email, "senha-errada-123")

    events = [e for e in client.login_events(since_ms=start_ms) if e.get("userId") == user_id]

    assert any(e["type"] == "LOGIN_ERROR" for e in events)
    assert client.brute_force_status(user_id)["numFailures"] >= 1
