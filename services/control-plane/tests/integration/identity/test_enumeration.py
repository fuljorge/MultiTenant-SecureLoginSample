"""Enumeração de contas (T035; US1 cenários 5 e 8; RNF-005, OWASP ASVS V2)."""

from __future__ import annotations

import re
import secrets
import statistics
import time
from collections.abc import Iterator

import pytest
from sqlalchemy import Engine

from tests.support.keycloak import BrowserLogin, KeycloakAdmin, LoginStep
from tests.support.people import Person, create_organization, create_person
from tests.support.stack import Stack

SAMPLES = 4
# Diferença aceita entre as medianas. Acima disso, o tempo de resposta revelaria se a
# conta existe. O hash Argon2 do Keycloak leva dezenas de milissegundos.
MAX_TIMING_GAP_SECONDS = 0.15


@pytest.fixture
def person(engine: Engine, kc: KeycloakAdmin) -> Iterator[Person]:
    created = create_person(engine, kc, organizations={create_organization(engine): "supervisor"})
    yield created
    kc.delete_user(str(created.id))


def _visible_text(step: LoginStep) -> str:
    """Texto visível da página, sem URLs e identificadores que mudam a cada requisição."""
    html = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", step.response.text, flags=re.S)
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\S*(tab_id|client_data|session_code|execution)=\S*", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _timed_wrong_login(stack: Stack, email: str) -> tuple[float, LoginStep]:
    browser = BrowserLogin(stack)
    page = browser.open()
    started = time.perf_counter()
    step = browser.password(page, email, f"Errada-{secrets.token_hex(6)}")
    return time.perf_counter() - started, step


def test_login_responde_igual_para_conta_existente_e_inexistente(
    stack: Stack, person: Person, kc: KeycloakAdmin
) -> None:
    missing = f"ninguem-{secrets.token_hex(5)}@exemplo.com.br"
    existing_times, missing_times = [], []
    for _ in range(SAMPLES):
        t_existing, existing_step = _timed_wrong_login(stack, person.email)
        t_missing, missing_step = _timed_wrong_login(stack, missing)
        existing_times.append(t_existing)
        missing_times.append(t_missing)
        time.sleep(1.2)  # abaixo de 1 s entre falhas o Keycloak aplica a proteção de login rápido

    kc.clear_brute_force(str(person.id))
    assert _visible_text(existing_step) == _visible_text(missing_step)
    gap = abs(statistics.median(existing_times) - statistics.median(missing_times))
    assert gap < MAX_TIMING_GAP_SECONDS, f"diferença de {gap * 1000:.0f} ms revela a conta"


def _request_reset(stack: Stack, email: str) -> LoginStep:
    browser = BrowserLogin(stack)
    login_page = browser.open()
    match = re.search(r'href="([^"]*reset-credentials[^"]*)"', login_page.response.text)
    assert match, "Link de recuperação de senha ausente"
    form = browser.open_url(match.group(1).replace("&amp;", "&"))
    return browser.submit(form, {"username": email})


def test_recuperacao_de_senha_responde_igual(stack: Stack, person: Person) -> None:
    missing = f"ninguem-{secrets.token_hex(5)}@exemplo.com.br"

    existing = _request_reset(stack, person.email)
    unknown = _request_reset(stack, missing)

    assert existing.response.status_code == unknown.response.status_code
    assert _visible_text(existing) == _visible_text(unknown)
