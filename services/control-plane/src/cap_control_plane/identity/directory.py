"""Consultas de identidade usadas pelo login e pela sessão (T036, T037, T085)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import Engine, text

from cap_control_plane.core.db import DbContext, transaction
from cap_control_plane.identity.authz import Principal
from cap_control_plane.identity.permissions import Profile, effective_permissions


@dataclass(frozen=True)
class UserRecord:
    id: uuid.UUID
    email: str
    name: str
    status: str
    is_super_admin: bool


@dataclass(frozen=True)
class OrganizationAccess:
    id: uuid.UUID
    name: str
    profile: Profile


def get_user(engine: Engine, user_id: uuid.UUID) -> UserRecord | None:
    with transaction(engine, DbContext(user_id=user_id)) as s:
        row = s.execute(
            text(
                "SELECT u.id, u.email, u.name, u.status,"
                " EXISTS (SELECT 1 FROM identity.super_admin a WHERE a.user_id = u.id)"
                " AS is_super_admin"
                " FROM identity.user_account u WHERE u.id = :id"
            ),
            {"id": user_id},
        ).one_or_none()
    if row is None:
        return None
    return UserRecord(row.id, str(row.email), row.name, row.status, row.is_super_admin)


def organizations_for(engine: Engine, user: UserRecord) -> list[OrganizationAccess]:
    """Organizações ativas em que a pessoa atua, com o perfil em cada uma (RF-019).

    O Super Administrador não tem nenhuma (RF-028): gere as organizações de fora delas.
    """
    if user.is_super_admin:
        return []
    with transaction(engine, DbContext(user_id=user.id)) as s:
        rows = s.execute(
            text(
                "SELECT o.id, o.name, m.profile::text AS profile"
                " FROM identity.membership m"
                " JOIN identity.organization o ON o.id = m.organization_id"
                " WHERE m.user_id = :uid AND m.status = 'active' AND o.status = 'active'"
                " ORDER BY o.name"
            ),
            {"uid": user.id},
        ).all()
    return [OrganizationAccess(r.id, r.name, Profile(r.profile)) for r in rows]


def principal_for(
    engine: Engine, user_id: uuid.UUID, organization_id: uuid.UUID | None
) -> Principal | None:
    """Principal da requisição; None se a pessoa não está ativa ou perdeu o acesso.

    Revalidado a cada requisição: vínculo desativado ou removido e organização suspensa
    tiram o acesso na próxima ação (RF-017, RF-026).
    """
    user = get_user(engine, user_id)
    if user is None or user.status != "active":
        return None
    if user.is_super_admin:
        return Principal(
            user_id=user_id,
            organization_id=None,
            profile=None,
            is_super_admin=True,
            permissions=effective_permissions(None, is_super_admin=True),
        )
    if organization_id is None:
        return None
    ctx = DbContext(user_id=user_id, organization_id=organization_id)
    with transaction(engine, ctx) as s:
        value = s.execute(
            text(
                "SELECT m.profile::text FROM identity.membership m"
                " JOIN identity.organization o ON o.id = m.organization_id"
                " WHERE m.user_id = :uid AND m.organization_id = :org"
                " AND m.status = 'active' AND o.status = 'active'"
            ),
            {"uid": user_id, "org": organization_id},
        ).scalar_one_or_none()
    if value is None:
        return None
    profile = Profile(value)
    return Principal(
        user_id=user_id,
        organization_id=organization_id,
        profile=profile,
        is_super_admin=False,
        permissions=effective_permissions(profile, is_super_admin=False),
    )
