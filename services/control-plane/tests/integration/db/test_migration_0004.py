"""Migração 0004 sobre dados do modelo anterior (T082; plano, seção 12).

Monta um banco parado na 0003, com Administrador da instalação, vínculos, organização
padrão e eventos de auditoria, e confere a conversão para o Super Administrador.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, create_engine, text

from cap_control_plane.audit.chain import GENESIS_HASH, AuditEvent, link_hash
from cap_control_plane.audit.verify import verify_chain
from cap_control_plane.core.db import DbContext, transaction
from tests.support.database import MigratedDatabase, run_migrations, temporary_database
from tests.support.stack import Stack


@pytest.fixture(scope="module")
def old_database(stack: Stack) -> Iterator[MigratedDatabase]:
    with temporary_database(stack) as db:
        run_migrations(db.migrator_url, "0003")
        yield db


@pytest.fixture(scope="module")
def migrated(old_database: MigratedDatabase) -> Iterator[tuple[Engine, dict[str, uuid.UUID]]]:
    owner = create_engine(old_database.migrator_url)
    ids = {"admin": uuid.uuid4(), "other": uuid.uuid4(), "org": uuid.uuid4()}
    with owner.begin() as conn:
        # Contexto do modelo antigo: escopo amplo do sistema.
        conn.execute(text("SELECT set_config('app.is_system', 'true', true)"))
        conn.execute(
            text(
                "INSERT INTO identity.organization (id, name, slug, is_default)"
                " VALUES (:id, 'Padrão', 'padrao', true)"
            ),
            {"id": ids["org"]},
        )
        for key in ("admin", "other"):
            conn.execute(
                text(
                    "INSERT INTO identity.user_account (id, email, name, status)"
                    " VALUES (:id, :e, :n, 'active')"
                ),
                {"id": ids[key], "e": f"{key}@exemplo.com.br", "n": key},
            )
            conn.execute(
                text(
                    "INSERT INTO identity.membership (organization_id, user_id, profile, status)"
                    " VALUES (:o, :u, 'administrator', 'active')"
                ),
                {"o": ids["org"], "u": ids[key]},
            )
        conn.execute(
            text("INSERT INTO identity.installation_admin (user_id) VALUES (:u)"),
            {"u": ids["admin"]},
        )
        # Evento gravado como no modelo anterior (sem installation_scope), com hash real.
        event = AuditEvent.now(
            organization_id=ids["org"], actor_user_id=ids["admin"], actor_kind="user",
            event_type="user.profile_changed", target_type="user",
            target_id=str(ids["other"]), result="success",
        )  # fmt: skip
        current = link_hash(GENESIS_HASH, event)
        conn.execute(
            text(
                "INSERT INTO audit.audit_event (seq, occurred_at, recorded_at, organization_id,"
                " actor_user_id, actor_kind, event_type, target_type, target_id, result,"
                " details, source, prev_hash, hash) VALUES (nextval('audit.audit_event_seq_seq'),"
                " :oa, :ra, :org, :actor, 'user', :et, 'user', :tid, 'success', '{}',"
                " 'control_plane', :prev, :hash)"
            ),
            {"oa": event.occurred_at, "ra": event.recorded_at, "org": ids["org"],
             "actor": ids["admin"], "et": event.event_type, "tid": event.target_id,
             "prev": GENESIS_HASH, "hash": current},
        )  # fmt: skip
        conn.execute(
            text("UPDATE audit.chain_head SET last_seq = 1, last_hash = :h"), {"h": current}
        )
    owner.dispose()

    run_migrations(old_database.migrator_url)
    engine = create_engine(old_database.app_url)
    yield engine, ids
    engine.dispose()


def test_administrador_da_instalacao_vira_super_administrador(
    migrated: tuple[Engine, dict[str, uuid.UUID]],
) -> None:
    engine, ids = migrated
    with transaction(engine, DbContext.system()) as s:
        supers = set(s.execute(text("SELECT user_id FROM identity.super_admin")).scalars())
        statuses = dict(
            s.execute(text("SELECT user_id, status::text FROM identity.membership")).all()
        )

    assert supers == {ids["admin"]}
    assert statuses == {ids["admin"]: "removed", ids["other"]: "active"}


def test_conversao_fica_no_audit_trail_e_a_cadeia_continua_valida(
    migrated: tuple[Engine, dict[str, uuid.UUID]],
) -> None:
    engine, ids = migrated
    with transaction(engine, DbContext.system()) as s:
        event = s.execute(
            text(
                "SELECT actor_kind, details, installation_scope FROM audit.audit_event"
                " WHERE event_type = 'super_admin.converted' AND target_id = :u"
            ),
            {"u": str(ids["admin"])},
        ).one()
        broken = verify_chain(s)

    assert event.actor_kind == "system"
    assert event.details == {"memberships_removed": 1}
    assert event.installation_scope is True
    assert broken is None


def test_organizacao_existente_fica_ativa_e_sem_organizacao_padrao(
    migrated: tuple[Engine, dict[str, uuid.UUID]],
) -> None:
    engine, ids = migrated
    with transaction(engine, DbContext.system()) as s:
        status = s.execute(
            text("SELECT status::text FROM identity.organization WHERE id = :o"), {"o": ids["org"]}
        ).scalar_one()
        has_default = s.execute(
            text(
                "SELECT count(*) FROM information_schema.columns WHERE table_schema = 'identity'"
                " AND table_name = 'organization' AND column_name = 'is_default'"
            )
        ).scalar_one()
        new_default = s.execute(
            text(
                "SELECT column_default FROM information_schema.columns"
                " WHERE table_schema = 'identity' AND table_name = 'organization'"
                " AND column_name = 'status'"
            )
        ).scalar_one()

    assert status == "active"
    assert has_default == 0
    assert "pending" in new_default
