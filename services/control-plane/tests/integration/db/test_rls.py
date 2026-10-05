"""Isolamento entre organizações no banco (T018; RF-020, RNF-001, Princípio IV)."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import Engine, text

from cap_control_plane.core.db import DbContext, transaction


@pytest.fixture
def data(engine: Engine) -> dict[str, uuid.UUID]:
    """Duas organizações, uma pessoa em cada e uma pessoa nas duas."""
    ids = {k: uuid.uuid4() for k in ("org_a", "org_b", "ana", "bia", "caio")}
    with transaction(engine, DbContext.system()) as s:
        for org in ("org_a", "org_b"):
            s.execute(
                text("INSERT INTO identity.organization (id, name, slug) VALUES (:id, :n, :s)"),
                {
                    "id": ids[org],
                    "n": f"{org} {ids[org].hex[:6]}",
                    "s": f"{org.replace('_', '-')}-{ids[org].hex[:6]}",
                },
            )
        for person in ("ana", "bia", "caio"):
            s.execute(
                text(
                    "INSERT INTO identity.user_account (id, email, name, status) "
                    "VALUES (:id, :email, :name, 'active')"
                ),
                {
                    "id": ids[person],
                    "email": f"{person}-{ids[person].hex[:6]}@ex.com",
                    "name": person,
                },
            )
        for person, org in (
            ("ana", "org_a"),
            ("bia", "org_b"),
            ("caio", "org_a"),
            ("caio", "org_b"),
        ):
            s.execute(
                text(
                    "INSERT INTO identity.membership (organization_id, user_id, profile, status) "
                    "VALUES (:org, :user, 'agent_designer', 'active')"
                ),
                {"org": ids[org], "user": ids[person]},
            )
            s.execute(
                text(
                    "INSERT INTO identity.invitation "
                    "(organization_id, email, profile, token_hash, expires_at, invited_by) "
                    "VALUES (:org, :email, 'supervisor', :hash, now() + interval '1 day', :by)"
                ),
                {
                    "org": ids[org],
                    "email": f"convite-{uuid.uuid4().hex[:6]}@ex.com",
                    "hash": uuid.uuid4().bytes,
                    "by": ids[person],
                },
            )
    return ids


def _orgs_visible(engine: Engine, ctx: DbContext, table: str) -> set[uuid.UUID]:
    with transaction(engine, ctx) as s:
        rows = s.execute(text(f"SELECT DISTINCT organization_id FROM identity.{table}"))  # noqa: S608
        return {r[0] for r in rows}


def test_sem_contexto_nada_e_visivel(engine: Engine, data: dict[str, uuid.UUID]) -> None:
    with transaction(engine, DbContext()) as s:
        assert s.execute(text("SELECT count(*) FROM identity.membership")).scalar() == 0
        assert s.execute(text("SELECT count(*) FROM identity.invitation")).scalar() == 0
        assert s.execute(text("SELECT count(*) FROM identity.user_account")).scalar() == 0


@pytest.mark.parametrize("table", ["membership", "invitation"])
def test_organizacao_a_nao_ve_dados_da_b(
    engine: Engine, data: dict[str, uuid.UUID], table: str
) -> None:
    ctx = DbContext(user_id=data["ana"], organization_id=data["org_a"])

    visible = _orgs_visible(engine, ctx, table)

    assert data["org_a"] in visible
    assert data["org_b"] not in visible


def test_usuario_da_a_nao_ve_pessoas_so_da_b(engine: Engine, data: dict[str, uuid.UUID]) -> None:
    ctx = DbContext(user_id=data["ana"], organization_id=data["org_a"])

    with transaction(engine, ctx) as s:
        users = {r[0] for r in s.execute(text("SELECT id FROM identity.user_account"))}

    assert {data["ana"], data["caio"]} <= users
    assert data["bia"] not in users


def test_pessoa_ve_os_proprios_vinculos_em_todas_as_organizacoes(
    engine: Engine, data: dict[str, uuid.UUID]
) -> None:
    ctx = DbContext(user_id=data["caio"], organization_id=data["org_a"])

    with transaction(engine, ctx) as s:
        rows = s.execute(
            text("SELECT organization_id FROM identity.membership WHERE user_id = :u"),
            {"u": data["caio"]},
        )
        orgs = {r[0] for r in rows}

    assert orgs == {data["org_a"], data["org_b"]}


def test_organizacao_a_nao_altera_dados_da_b(engine: Engine, data: dict[str, uuid.UUID]) -> None:
    ctx = DbContext(user_id=data["ana"], organization_id=data["org_a"])

    with transaction(engine, ctx) as s:
        updated = s.execute(
            text(
                "UPDATE identity.membership SET profile = 'supervisor' WHERE organization_id = :b"
            ),
            {"b": data["org_b"]},
        ).rowcount

    assert updated == 0


def test_papel_da_aplicacao_nao_ignora_rls_nem_e_dono(engine: Engine) -> None:
    with transaction(engine, DbContext()) as s:
        bypass = s.execute(
            text("SELECT rolbypassrls, rolsuper FROM pg_roles WHERE rolname = current_user")
        ).one()
        owned = s.execute(
            text(
                "SELECT count(*) FROM pg_tables "
                "WHERE schemaname = 'identity' AND tableowner = current_user"
            )
        ).scalar()

    assert tuple(bypass) == (False, False)
    assert owned == 0
