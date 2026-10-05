"""CLI de operação: Super Administrador inicial e reemissão do link (T042, T089; US2, §53.2)."""

from __future__ import annotations

import secrets
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from sqlalchemy import Engine, text

from cap_control_plane.cli.cap_admin import (
    AdminAlreadyExistsError,
    bootstrap_super_admin,
    reissue_activation,
)
from cap_control_plane.core.db import DbContext, transaction
from cap_control_plane.services import Services
from tests.support.keycloak import KeycloakAdmin
from tests.support.mailpit import wait_for_email
from tests.support.people import create_organization, create_person
from tests.support.stack import Stack


def _clear_super_admins(engine: Engine) -> None:
    with transaction(engine, DbContext.system()) as s:
        s.execute(text("DELETE FROM identity.super_admin"))


@pytest.fixture(autouse=True)
def clean_installation(engine: Engine) -> Iterator[None]:
    """O bootstrap só roda numa instalação sem Super Administrador."""
    _clear_super_admins(engine)
    yield
    _clear_super_admins(engine)


def _email() -> str:
    return f"super-{secrets.token_hex(4)}@exemplo.com.br"


def test_bootstrap_cria_super_administrador_sem_organizacao_e_envia_boas_vindas(
    services: Services, engine: Engine, stack: Stack, kc: KeycloakAdmin
) -> None:
    email, since = _email(), datetime.now(UTC)

    result = bootstrap_super_admin(services, email=email, name="Ana Super")

    with transaction(engine, DbContext.system()) as s:
        user = s.execute(
            text("SELECT email, name, status FROM identity.user_account WHERE id = :id"),
            {"id": result.user_id},
        ).one()
        memberships = s.execute(
            text("SELECT count(*) FROM identity.membership WHERE user_id = :id"),
            {"id": result.user_id},
        ).scalar_one()
        is_super = s.execute(
            text("SELECT count(*) FROM identity.super_admin WHERE user_id = :id"),
            {"id": result.user_id},
        ).scalar_one()
        events = s.execute(
            text(
                "SELECT event_type, installation_scope FROM audit.audit_event"
                " WHERE target_id = :u AND actor_kind = 'system'"
            ),
            {"u": str(result.user_id)},
        ).all()

    assert tuple(user) == (email, "Ana Super", "invited")
    assert memberships == 0
    assert is_super == 1
    assert [tuple(e) for e in events] == [("super_admin.invited", True)]
    assert kc.get(f"/users/{result.user_id}")["requiredActions"] == ["UPDATE_PASSWORD"]
    assert "Você recebeu acesso ao SecureLogin" in wait_for_email(stack.mailpit_url, email, since)
    kc.delete_user(str(result.user_id))


def test_bootstrap_recusa_segunda_execucao(services: Services, kc: KeycloakAdmin) -> None:
    first = bootstrap_super_admin(services, email=_email(), name="Primeira")

    with pytest.raises(AdminAlreadyExistsError):
        bootstrap_super_admin(services, email=_email(), name="Segunda")
    kc.delete_user(str(first.user_id))


def test_reemite_link_para_novo_email_com_registro_do_chamado(
    services: Services, engine: Engine, stack: Stack, kc: KeycloakAdmin
) -> None:
    created = bootstrap_super_admin(services, email=_email(), name="Bia")
    new_email, since = _email(), datetime.now(UTC)

    reissue_activation(services, email=created.email, ticket="CHAMADO-1234", new_email=new_email)

    with transaction(engine, DbContext.system()) as s:
        stored = s.execute(
            text("SELECT email FROM identity.user_account WHERE id = :id"),
            {"id": created.user_id},
        ).scalar_one()
        event = s.execute(
            text(
                "SELECT actor_kind, details FROM audit.audit_event"
                " WHERE event_type = 'support.activation_reissued' AND target_id = :id"
            ),
            {"id": str(created.user_id)},
        ).one()
    assert stored == new_email
    assert kc.get(f"/users/{created.user_id}")["email"] == new_email
    assert event.actor_kind == "support"
    assert event.details == {"ticket": "CHAMADO-1234", "address_changed": True}
    assert "Você recebeu acesso" in wait_for_email(stack.mailpit_url, new_email, since)
    kc.delete_user(str(created.user_id))


def test_reemissao_exige_numero_do_chamado(services: Services) -> None:
    with pytest.raises(ValueError, match="chamado"):
        reissue_activation(services, email="qualquer@cliente.com.br", ticket=" ")


def test_reemissao_para_pessoa_inexistente_falha(services: Services) -> None:
    with pytest.raises(LookupError):
        reissue_activation(services, email=f"{uuid.uuid4().hex}@cliente.com.br", ticket="C-1")


def test_reemissao_nao_vale_para_administrador_de_organizacao(
    services: Services, engine: Engine, kc: KeycloakAdmin
) -> None:
    """Administradores de organização são geridos pelo Super Administrador (RF-027)."""
    admin = create_person(engine, kc, organizations={create_organization(engine): "administrator"})

    with pytest.raises(LookupError, match="Super Administrador"):
        reissue_activation(services, email=admin.email, ticket="C-2")
    kc.delete_user(str(admin.id))
