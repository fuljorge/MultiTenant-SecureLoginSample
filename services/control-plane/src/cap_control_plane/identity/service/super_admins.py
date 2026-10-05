"""Gestão de Super Administradores (T092; US5; RF-012, RF-028, RF-030).

Só Super Administradores gerem Super Administradores; o inicial vem do provisionamento
(`cap-admin bootstrap-super-admin`). A instalação nunca fica sem nenhum ativo.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.orm import Session

from cap_control_plane.audit.writer import Origin
from cap_control_plane.core.db import DbContext, transaction
from cap_control_plane.identity.authz import Principal
from cap_control_plane.identity.service.common import ConflictError, NotFoundError, record
from cap_control_plane.services import Services


@dataclass(frozen=True)
class SuperAdminView:
    id: uuid.UUID
    name: str
    email: str
    status: str
    last_login_at: datetime | None


def list_super_admins(services: Services, principal: Principal) -> list[SuperAdminView]:
    with transaction(services.engine, principal.db_context()) as s:
        rows = s.execute(
            text(
                "SELECT u.id, u.name, u.email, u.status::text AS status, u.last_login_at"
                " FROM identity.super_admin a JOIN identity.user_account u ON u.id = a.user_id"
                " ORDER BY u.name"
            )
        ).all()
    return [SuperAdminView(r.id, r.name, str(r.email), r.status, r.last_login_at) for r in rows]


def invite_super_admin(
    services: Services, principal: Principal, origin: Origin, *, email: str, name: str
) -> uuid.UUID:
    """Convida outro Super Administrador; o link de ativação vai por e-mail (RF-030)."""
    email = email.strip().lower()
    # A pessoa pode existir em uma organização, invisível ao Super Administrador: a busca
    # ignora o RLS de propósito e só devolve se existe.
    with transaction(services.engine, DbContext.system()) as s:
        exists = s.execute(
            text("SELECT 1 FROM identity.user_account WHERE email = :e"), {"e": email}
        ).first()
    if exists:
        # RF-028: quem tem vínculo com organização não pode ser Super Administrador.
        raise ConflictError("Este e-mail já pertence a uma pessoa cadastrada.")

    kc = services.keycloak_admin
    existing = kc.find_user_by_email(email)
    user_id = uuid.UUID(existing["id"] if existing else kc.create_user(email))
    with transaction(services.engine, principal.db_context()) as s:
        s.execute(
            text(
                "INSERT INTO identity.user_account (id, email, name, status)"
                " VALUES (:id, :email, :name, 'invited')"
            ),
            {"id": user_id, "email": email, "name": name.strip()},
        )
        s.execute(
            text("INSERT INTO identity.super_admin (user_id, granted_by) VALUES (:u, :by)"),
            {"u": user_id, "by": principal.user_id},
        )
        record(
            s, principal, origin,
            event_type="super_admin.invited", target_type="user", target_id=user_id,
        )  # fmt: skip
    kc.send_activation_email(
        str(user_id), lifespan_seconds=services.security.invitation_valid_hours() * 3600
    )
    return user_id


def _ensure_not_last(session: Session, user_id: uuid.UUID) -> None:
    """RF-012: trava os Super Administradores ativos; dois pedidos simultâneos não passam."""
    active = (
        session.execute(
            text(
                "SELECT a.user_id FROM identity.super_admin a"
                " JOIN identity.user_account u ON u.id = a.user_id"
                " WHERE u.status = 'active' FOR UPDATE OF a, u"
            )
        )
        .scalars()
        .all()
    )
    if user_id in active and len(active) == 1:
        raise ConflictError("A instalação precisa de pelo menos um Super Administrador ativo.")


def _status(session: Session, user_id: uuid.UUID) -> str:
    status = session.execute(
        text(
            "SELECT u.status::text FROM identity.super_admin a"
            " JOIN identity.user_account u ON u.id = a.user_id WHERE a.user_id = :u"
        ),
        {"u": user_id},
    ).scalar_one_or_none()
    if status is None:
        raise NotFoundError("Super Administrador não encontrado")
    return str(status)


def disable_super_admin(
    services: Services, principal: Principal, origin: Origin, *, user_id: uuid.UUID
) -> None:
    if user_id == principal.user_id:
        raise ConflictError("Você não pode desativar a sua própria conta.")
    with transaction(services.engine, principal.db_context()) as s:
        if _status(s, user_id) == "disabled":
            return
        _ensure_not_last(s, user_id)
        s.execute(
            text(
                "UPDATE identity.user_account SET status = 'disabled', version = version + 1,"
                " updated_at = now() WHERE id = :id"
            ),
            {"id": user_id},
        )
        services.keycloak_admin.set_enabled(str(user_id), enabled=False)
        services.keycloak_admin.logout(str(user_id))
        record(
            s, principal, origin,
            event_type="super_admin.disabled", target_type="user", target_id=user_id,
        )  # fmt: skip
    services.sessions.delete_all_for_user(user_id)


def enable_super_admin(
    services: Services, principal: Principal, origin: Origin, *, user_id: uuid.UUID
) -> None:
    with transaction(services.engine, principal.db_context()) as s:
        if _status(s, user_id) != "disabled":
            return
        s.execute(
            text(
                "UPDATE identity.user_account SET status = 'active', version = version + 1,"
                " updated_at = now() WHERE id = :id"
            ),
            {"id": user_id},
        )
        services.keycloak_admin.set_enabled(str(user_id), enabled=True)
        record(
            s, principal, origin,
            event_type="super_admin.enabled", target_type="user", target_id=user_id,
        )  # fmt: skip
