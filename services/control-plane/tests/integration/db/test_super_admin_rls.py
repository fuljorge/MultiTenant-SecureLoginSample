"""RLS do Super Administrador direto no banco (T081; RF-028, RNF-001; plano §4.11).

O Super Administrador vê as organizações, os seus Administradores e os convites de
Administrador, e nada mais de dentro delas. A barreira está no banco: vale para qualquer
consulta, mesmo com erro no serviço.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError

from cap_control_plane.audit.chain import AuditEvent
from cap_control_plane.audit.writer import append_event
from cap_control_plane.core.db import DbContext, transaction
from tests.support.people import create_organization


def _person(engine: Engine, label: str) -> uuid.UUID:
    user_id = uuid.uuid4()
    with transaction(engine, DbContext.system()) as s:
        s.execute(
            text(
                "INSERT INTO identity.user_account (id, email, name, status)"
                " VALUES (:id, :e, :n, 'active')"
            ),
            {"id": user_id, "e": f"{label}-{user_id.hex[:8]}@exemplo.com.br", "n": label},
        )
    return user_id


def _membership(engine: Engine, org: uuid.UUID, user: uuid.UUID, profile: str) -> None:
    with transaction(engine, DbContext.system()) as s:
        s.execute(
            text(
                "INSERT INTO identity.membership (organization_id, user_id, profile, status)"
                " VALUES (:o, :u, :p, 'active')"
            ),
            {"o": org, "u": user, "p": profile},
        )


@pytest.fixture(scope="module")
def data(engine: Engine) -> dict[str, uuid.UUID]:
    org_a, org_b = create_organization(engine), create_organization(engine)
    ids = {"org_a": org_a, "org_b": org_b}
    for label in ("admin_a", "analyst_a", "admin_b", "super", "not_super"):
        ids[label] = _person(engine, label)
    _membership(engine, org_a, ids["admin_a"], "administrator")
    _membership(engine, org_a, ids["analyst_a"], "business_analyst")
    _membership(engine, org_b, ids["admin_b"], "administrator")
    _membership(engine, org_b, ids["not_super"], "supervisor")
    expires = datetime.now(UTC) + timedelta(days=1)
    with transaction(engine, DbContext.system()) as s:
        s.execute(
            text("INSERT INTO identity.super_admin (user_id) VALUES (:u)"), {"u": ids["super"]}
        )
        for profile in ("administrator", "developer"):
            s.execute(
                text(
                    "INSERT INTO identity.invitation"
                    " (organization_id, email, profile, expires_at, invited_by)"
                    " VALUES (:o, :e, :p, :x, :by)"
                ),
                {"o": org_a, "e": f"{profile}-{uuid.uuid4().hex[:6]}@exemplo.com.br",
                 "p": profile, "x": expires, "by": ids["admin_a"]},
            )  # fmt: skip
        s.execute(
            text(
                "INSERT INTO identity.email_change_request"
                " (user_id, new_email, token_hash, expires_at, requested_by)"
                " VALUES (:u, :e, :h, :x, :by)"
            ),
            {"u": ids["admin_a"], "e": f"novo-{uuid.uuid4().hex[:6]}@exemplo.com.br",
             "h": uuid.uuid4().bytes * 2, "x": expires, "by": ids["admin_a"]},
        )  # fmt: skip
    return ids


def _super(data: dict[str, uuid.UUID]) -> DbContext:
    return DbContext(user_id=data["super"], is_super_admin=True)


def _ids(engine: Engine, ctx: DbContext, sql: str, **params: object) -> set[uuid.UUID]:
    with transaction(engine, ctx) as s:
        return {r[0] for r in s.execute(text(sql), params)}


def test_ve_todas_as_organizacoes(engine: Engine, data: dict[str, uuid.UUID]) -> None:
    visible = _ids(engine, _super(data), "SELECT id FROM identity.organization")

    assert {data["org_a"], data["org_b"]} <= visible


def test_ve_so_vinculos_de_administrador(engine: Engine, data: dict[str, uuid.UUID]) -> None:
    users = _ids(engine, _super(data), "SELECT user_id FROM identity.membership")

    assert {data["admin_a"], data["admin_b"]} <= users
    assert data["analyst_a"] not in users
    assert data["not_super"] not in users


def test_ve_so_administradores_e_super_administradores(
    engine: Engine, data: dict[str, uuid.UUID]
) -> None:
    people = _ids(engine, _super(data), "SELECT id FROM identity.user_account")

    assert {data["admin_a"], data["admin_b"], data["super"]} <= people
    assert data["analyst_a"] not in people


def test_ve_so_convites_de_administrador(engine: Engine, data: dict[str, uuid.UUID]) -> None:
    with transaction(engine, _super(data)) as s:
        profiles = set(
            s.execute(
                text("SELECT profile::text FROM identity.invitation WHERE organization_id = :o"),
                {"o": data["org_a"]},
            ).scalars()
        )

    assert profiles == {"administrator"}


def test_nao_ve_trocas_de_email(engine: Engine, data: dict[str, uuid.UUID]) -> None:
    assert _ids(engine, _super(data), "SELECT id FROM identity.email_change_request") == set()


def test_nao_cria_vinculo_de_outro_perfil(engine: Engine, data: dict[str, uuid.UUID]) -> None:
    with pytest.raises(DBAPIError, match="row-level security"):
        with transaction(engine, _super(data)) as s:
            s.execute(
                text(
                    "INSERT INTO identity.membership (organization_id, user_id, profile, status)"
                    " VALUES (:o, :u, 'developer', 'pending')"
                ),
                {"o": data["org_b"], "u": data["admin_a"]},
            )


def test_marca_sem_linha_em_super_admin_nao_da_acesso(
    engine: Engine, data: dict[str, uuid.UUID]
) -> None:
    """A marca da sessão sozinha não basta: o banco confere a tabela super_admin."""
    ctx = DbContext(user_id=data["not_super"], is_super_admin=True)

    visible = _ids(
        engine, ctx, "SELECT user_id FROM identity.membership WHERE profile = 'administrator'"
    )

    assert visible <= {data["not_super"]}


def test_super_administrador_nao_recebe_vinculo(engine: Engine, data: dict[str, uuid.UUID]) -> None:
    with pytest.raises(DBAPIError, match="RF-028"):
        _membership(engine, data["org_a"], data["super"], "administrator")


def test_pessoa_com_vinculo_nao_vira_super_administrador(
    engine: Engine, data: dict[str, uuid.UUID]
) -> None:
    with pytest.raises(DBAPIError, match="RF-028"):
        with transaction(engine, DbContext.system()) as s:
            s.execute(
                text("INSERT INTO identity.super_admin (user_id) VALUES (:u)"),
                {"u": data["admin_b"]},
            )


def test_auditoria_so_da_instalacao(engine: Engine, data: dict[str, uuid.UUID]) -> None:
    """US6, cenário 2: eventos internos da organização não aparecem ao Super Administrador."""
    kinds = {
        "interno": dict(actor_user_id=data["admin_a"], installation_scope=False),
        "instalacao": dict(actor_user_id=data["super"], installation_scope=True),
    }
    seqs = {}
    with transaction(engine, DbContext.system()) as s:
        for label, extra in kinds.items():
            seqs[label] = append_event(
                s,
                AuditEvent.now(
                    organization_id=data["org_a"], actor_kind="user",
                    event_type="user.profile_changed", target_type="user",
                    target_id=str(data["analyst_a"]), result="success", **extra,
                ),
            )  # fmt: skip

    seen_by_super = _ids(engine, _super(data), "SELECT seq FROM audit.audit_event")  # type: ignore[arg-type]
    seen_by_admin = _ids(
        engine,
        DbContext(user_id=data["admin_a"], organization_id=data["org_a"]),
        "SELECT seq FROM audit.audit_event",
    )  # type: ignore[arg-type]

    assert seqs["instalacao"] in seen_by_super
    assert seqs["interno"] not in seen_by_super
    assert {seqs["instalacao"], seqs["interno"]} <= seen_by_admin
