"""Comportamento do realm `cap` (T012; RF-001, RF-003, RF-007, RF-024; research R1, R5)."""

from __future__ import annotations

import secrets
import time
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest

from tests.support.keycloak import BrowserLogin, KeycloakAdmin
from tests.support.mailpit import extract_code, wait_for_email
from tests.support.stack import Stack

EXPECTED_CLIENTS = {
    # Clientes internos que o Keycloak cria em todo realm.
    "account",
    "account-console",
    "admin-cli",
    "broker",
    "realm-management",
    "security-admin-console",
    # Clientes da plataforma.
    "cap-control-plane",
    "cap-admin-bridge",
}


@pytest.fixture(scope="module")
def admin(stack: Stack) -> KeycloakAdmin:
    return KeycloakAdmin(stack)


@pytest.fixture
def user(admin: KeycloakAdmin) -> Iterator[tuple[str, str, str]]:
    email = f"teste-{secrets.token_hex(4)}@exemplo.com.br"
    password = f"Senha-Forte-{secrets.token_urlsafe(12)}"
    user_id = admin.create_user(email, password)
    yield user_id, email, password
    admin.delete_user(user_id)


def test_login_exige_codigo_enviado_ao_email(stack: Stack, user: tuple[str, str, str]) -> None:
    _, email, password = user
    browser = BrowserLogin(stack)
    since = datetime.now(UTC)

    after_password = browser.password(browser.open(), email, password)

    assert after_password.asks_for_email_code
    assert after_password.authorization_code is None

    code = extract_code(wait_for_email(stack.mailpit_url, email, since))
    after_code = browser.code(after_password, code)

    assert after_code.authorization_code is not None


def test_codigo_incorreto_nao_conclui_login(stack: Stack, user: tuple[str, str, str]) -> None:
    _, email, password = user
    browser = BrowserLogin(stack)

    after_password = browser.password(browser.open(), email, password)
    after_code = browser.code(after_password, "000000")

    assert after_code.authorization_code is None
    assert after_code.asks_for_email_code


def test_senha_incorreta_tem_mensagem_generica_e_nao_envia_codigo(
    stack: Stack, user: tuple[str, str, str]
) -> None:
    _, email, _ = user
    browser = BrowserLogin(stack)

    wrong_password = browser.password(browser.open(), email, "senha-errada-123")
    unknown_user = browser.password(browser.open(), "ninguem@exemplo.com.br", "senha-errada-123")

    assert not wrong_password.asks_for_email_code
    assert "E-mail ou senha inválidos." in wrong_password.response.text
    assert "E-mail ou senha inválidos." in unknown_user.response.text


def _pause() -> None:
    # Tentativas com menos de 1 s de intervalo disparam a proteção contra login rápido
    # do Keycloak, que bloquearia antes da regra das 5 falhas.
    time.sleep(1.2)


def test_bloqueio_apos_cinco_falhas_de_senha(
    stack: Stack, admin: KeycloakAdmin, user: tuple[str, str, str]
) -> None:
    user_id, email, _ = user
    browser = BrowserLogin(stack)

    for _ in range(4):
        browser.password(browser.open(), email, "senha-errada-123")
        _pause()
    assert admin.brute_force_status(user_id)["disabled"] is False

    browser.password(browser.open(), email, "senha-errada-123")

    status = admin.brute_force_status(user_id)
    assert status["numFailures"] == 5
    assert status["disabled"] is True


def test_codigo_invalidado_apos_cinco_tentativas(stack: Stack, user: tuple[str, str, str]) -> None:
    """RF-002: o código deixa de valer após o limite de tentativas."""
    _, email, password = user
    browser = BrowserLogin(stack)
    since = datetime.now(UTC)
    step = browser.password(browser.open(), email, password)
    real_code = extract_code(wait_for_email(stack.mailpit_url, email, since))

    for attempt in range(5):
        _pause()
        step = browser.code(step, f"{(int(real_code) + attempt + 1) % 1_000_000:06d}")
    _pause()
    final = browser.code(step, real_code)

    assert final.authorization_code is None


def test_falhas_de_codigo_contam_para_o_bloqueio(
    stack: Stack, admin: KeycloakAdmin, user: tuple[str, str, str]
) -> None:
    """RF-003: falhas de senha e de código somam para o bloqueio temporário."""
    user_id, email, password = user
    browser = BrowserLogin(stack)

    for _ in range(3):
        browser.password(browser.open(), email, "senha-errada-123")
        _pause()
    step = browser.password(browser.open(), email, password)
    for wrong in ("000000", "111111"):
        _pause()
        step = browser.code(step, wrong)

    assert admin.brute_force_status(user_id)["disabled"] is True


def test_registro_de_novos_usuarios_desligado(stack: Stack, admin: KeycloakAdmin) -> None:
    realm = admin.get("")
    login_page = BrowserLogin(stack).open()

    assert realm["registrationAllowed"] is False
    assert "kc-registration" not in login_page.response.text


def test_politica_recusa_senha_vazada(admin: KeycloakAdmin, user: tuple[str, str, str]) -> None:
    user_id, _, _ = user

    # Presente na lista de senhas vazadas (Pwdb top 1M) e com 12 caracteres.
    response = admin.reset_password(user_id, "qwerty123456")

    assert response.status_code == 400


def test_politica_aceita_64_e_recusa_mais_de_128_caracteres(
    admin: KeycloakAdmin, user: tuple[str, str, str]
) -> None:
    """OWASP ASVS 2.1.2 (T076)."""
    user_id, _, _ = user

    assert admin.reset_password(user_id, "Frase-longa-" + "x7" * 26).status_code == 204
    assert admin.reset_password(user_id, "Frase-longa-" + "y8" * 59).status_code == 400


def test_realm_sem_administradores_ou_clientes_extras(admin: KeycloakAdmin) -> None:
    """RF-024: nenhuma forma de acesso além das previstas."""
    clients = admin.get("/clients")
    client_ids = {c["clientId"] for c in clients}
    realm_management = next(c for c in clients if c["clientId"] == "realm-management")
    role_holders: set[str] = set()
    for role in admin.get(f"/clients/{realm_management['id']}/roles"):
        for holder in admin.get(f"/clients/{realm_management['id']}/roles/{role['name']}/users"):
            role_holders.add(holder["username"])

    assert client_ids == EXPECTED_CLIENTS
    assert role_holders <= {"service-account-cap-admin-bridge"}
    assert next(c for c in clients if c["clientId"] == "account-console")["enabled"] is False


def test_configuracao_do_codigo_por_email(admin: KeycloakAdmin) -> None:
    executions = admin.get("/authentication/flows/cap-browser/executions")
    email_step = next(e for e in executions if e.get("providerId") == "email-authenticator")
    config = admin.get(f"/authentication/config/{email_step['authenticationConfig']}")["config"]

    assert email_step["requirement"] == "REQUIRED"
    assert config["simulationMode"] == "false"
    assert config["length"] == "6"
    assert config["ttl"] == "600"
    assert config["resendCooldown"] == "300"
