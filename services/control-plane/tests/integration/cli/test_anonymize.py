"""Pedido de esquecimento: `cap-admin anonymize-user` (T072; RNF-002, LGPD; spec, seção 8).

Os dados pessoais saem de todos os armazenamentos da feature (conta, Keycloak, sessões,
convites, trocas de e-mail, IP e navegador); os eventos de auditoria ficam, apontando para
um registro sem nome nem e-mail, e a cadeia continua válida.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from sqlalchemy import Engine, text

from cap_control_plane.audit.chain import AuditEvent
from cap_control_plane.audit.verify import verify_chain
from cap_control_plane.audit.writer import Origin, append_event
from cap_control_plane.cli.cap_admin import anonymize_user
from cap_control_plane.core.db import DbContext, transaction
from cap_control_plane.services import Services
from tests.support.keycloak import KeycloakAdmin
from tests.support.people import create_organization, create_person, logged_in
from tests.support.stack import Stack


def test_anonimiza_todos_os_dados_pessoais_e_preserva_a_auditoria(
    app: FastAPI, services: Services, engine: Engine, stack: Stack, kc: KeycloakAdmin
) -> None:
    org = create_organization(engine)
    other_admin = create_person(engine, kc, organizations={org: "administrator"})  # não é o último
    person = create_person(engine, kc, organizations={org: "administrator"})
    with transaction(engine, DbContext.system()) as s:
        seq = append_event(
            s,
            AuditEvent.now(
                organization_id=org, actor_user_id=person.id, actor_kind="user",
                event_type="user.profile_changed", target_type="user",
                target_id=str(uuid.uuid4()), result="success",
            ),
            Origin(source_ip="203.0.113.50", user_agent="Navegador da pessoa"),
        )  # fmt: skip
        expires = datetime.now(UTC) + timedelta(days=1)
        s.execute(
            text(
                "INSERT INTO identity.invitation (organization_id, email, profile, token_hash,"
                " expires_at, invited_by) VALUES (:o, :e, 'supervisor', :h, :x, :by)"
            ),
            {"o": create_organization(engine), "e": person.email, "h": uuid.uuid4().bytes,
             "x": expires, "by": uuid.uuid4()},
        )  # fmt: skip
        s.execute(
            text(
                "INSERT INTO identity.email_change_request"
                " (user_id, new_email, token_hash, expires_at, requested_by)"
                " VALUES (:u, :e, :h, :x, :by)"
            ),
            {"u": person.id, "e": f"novo-{uuid.uuid4().hex[:6]}@exemplo.com.br",
             "h": uuid.uuid4().bytes * 2, "x": expires, "by": person.id},
        )  # fmt: skip

    with logged_in(app, stack, person) as client:
        assert client.get("/api/v1/me").status_code == 200
        anonymize_user(services, email=person.email, ticket="LGPD-77")
        assert client.get("/api/v1/me").status_code == 401

    with transaction(engine, DbContext.system()) as s:
        account = s.execute(
            text(
                "SELECT name, email, status::text AS status, anonymized_at"
                " FROM identity.user_account WHERE id = :id"
            ),
            {"id": person.id},
        ).one()
        memberships = set(
            s.execute(
                text("SELECT status::text FROM identity.membership WHERE user_id = :id"),
                {"id": person.id},
            ).scalars()
        )
        leftovers = s.execute(
            text(
                "SELECT (SELECT count(*) FROM identity.invitation WHERE email = :e)"
                " + (SELECT count(*) FROM identity.email_change_request"
                "    WHERE user_id = :id AND new_email NOT LIKE 'anonimo-%')"
                " + (SELECT count(*) FROM audit.audit_event_origin o"
                "    JOIN audit.audit_event e ON e.seq = o.seq WHERE e.actor_user_id = :id)"
            ),
            {"e": person.email, "id": person.id},
        ).scalar_one()
        event = s.execute(
            text(
                "SELECT actor_kind, details, installation_scope FROM audit.audit_event"
                " WHERE event_type = 'user.anonymized' AND target_id = :id"
            ),
            {"id": str(person.id)},
        ).one()
        kept = s.execute(
            text("SELECT count(*) FROM audit.audit_event WHERE seq = :s"), {"s": seq}
        ).scalar_one()
        broken = verify_chain(s)

    assert account.name == "Pessoa anonimizada"
    assert account.email.startswith("anonimo-") and person.email not in account.email
    assert account.status == "disabled" and account.anonymized_at is not None
    assert memberships == {"removed"}
    assert leftovers == 0
    assert event.actor_kind == "support"
    assert event.details == {"ticket": "LGPD-77"}
    assert event.installation_scope is True
    assert kept == 1 and broken is None
    assert services.keycloak_admin.find_user_by_email(person.email) is None
    assert services.sessions.list_for_user(person.id) == []
    kc.delete_user(str(other_admin.id))


def test_recusa_o_ultimo_administrador_de_organizacao_ativa(
    services: Services, engine: Engine, kc: KeycloakAdmin
) -> None:
    only = create_person(engine, kc, organizations={create_organization(engine): "administrator"})

    with pytest.raises(ValueError, match="último Administrador"):
        anonymize_user(services, email=only.email, ticket="LGPD-78")
    kc.delete_user(str(only.id))


def test_exige_chamado_e_pessoa_existente(services: Services) -> None:
    with pytest.raises(ValueError, match="chamado"):
        anonymize_user(services, email="x@exemplo.com.br", ticket=" ")
    with pytest.raises(LookupError):
        anonymize_user(services, email=f"{uuid.uuid4().hex}@exemplo.com.br", ticket="C-1")
