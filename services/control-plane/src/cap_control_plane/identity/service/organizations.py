"""Gestão de organizações pelo Super Administrador (T063; US5; RF-018, RF-025 a RF-027).

O Super Administrador age com o próprio contexto: o RLS só lhe mostra organizações,
vínculos e convites de Administrador e as pessoas que são Administradores (migração
0004). Nada aqui lê dados de dentro das organizações.
"""

from __future__ import annotations

import re
import unicodedata
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from cap_control_plane.audit.chain import AuditEvent
from cap_control_plane.audit.writer import Origin, append_event
from cap_control_plane.core.db import DbContext, transaction
from cap_control_plane.identity.authz import Principal
from cap_control_plane.identity.permissions import Profile
from cap_control_plane.identity.service import invitations, users
from cap_control_plane.identity.service.common import (
    ConflictError,
    NotFoundError,
    VersionMismatchError,
    record,
)
from cap_control_plane.services import Services


@dataclass(frozen=True)
class AdministratorView:
    id: uuid.UUID
    name: str
    email: str
    # Situação do vínculo de Administrador: pending (convite), active ou disabled.
    status: str


@dataclass(frozen=True)
class OrganizationView:
    id: uuid.UUID
    name: str
    status: str
    created_at: datetime
    version: int
    administrators: list[AdministratorView]


def slugify(value: str) -> str:
    ascii_text = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")
    return slug or "organizacao"


_ORGS_SQL = """
SELECT o.id, o.name, o.status::text AS status, o.created_at, o.version,
       coalesce(
         json_agg(json_build_object(
           'id', u.id, 'name', u.name, 'email', u.email, 'status', m.status
         ) ORDER BY u.name) FILTER (WHERE m.id IS NOT NULL),
         '[]'::json
       ) AS administrators
FROM identity.organization o
LEFT JOIN identity.membership m
  ON m.organization_id = o.id AND m.profile = 'administrator' AND m.status <> 'removed'
LEFT JOIN identity.user_account u ON u.id = m.user_id
WHERE (CAST(:status AS text) IS NULL OR o.status::text = :status)
  AND (CAST(:q AS text) IS NULL OR o.name ILIKE :q OR EXISTS (
        SELECT 1 FROM identity.membership fm
        JOIN identity.user_account fu ON fu.id = fm.user_id
        WHERE fm.organization_id = o.id AND fm.profile = 'administrator'
          AND (fu.name ILIKE :q OR fu.email ILIKE :q)))
  {extra}
GROUP BY o.id
ORDER BY o.name
LIMIT :limit OFFSET :offset
"""


def _to_view(row: Any) -> OrganizationView:
    return OrganizationView(
        id=row.id,
        name=row.name,
        status=row.status,
        created_at=row.created_at,
        version=row.version,
        administrators=[
            AdministratorView(uuid.UUID(a["id"]), a["name"], str(a["email"]), a["status"])
            for a in row.administrators
        ],
    )


def list_organizations(
    services: Services,
    principal: Principal,
    *,
    query: str | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[OrganizationView]:
    """Todas as organizações da instalação, com os seus Administradores (RF-025)."""
    with transaction(services.engine, principal.db_context()) as s:
        rows = s.execute(
            text(_ORGS_SQL.format(extra="")),
            {
                "status": status,
                "q": f"%{query.strip()}%" if query and query.strip() else None,
                "limit": min(max(limit, 1), 200),
                "offset": max(offset, 0),
            },
        ).all()
    return [_to_view(r) for r in rows]


def get_organization(
    services: Services, principal: Principal, organization_id: uuid.UUID
) -> OrganizationView:
    with transaction(services.engine, principal.db_context()) as s:
        return _to_view(_fetch(s, organization_id))


def _fetch(session: Session, organization_id: uuid.UUID) -> Any:
    row = session.execute(
        text(_ORGS_SQL.format(extra="AND o.id = :id")),
        {"id": organization_id, "status": None, "q": None, "limit": 1, "offset": 0},
    ).one_or_none()
    if row is None:
        raise NotFoundError("Organização não encontrada")
    return row


def _lock_status(session: Session, organization_id: uuid.UUID) -> str:
    status = session.execute(
        text("SELECT status::text FROM identity.organization WHERE id = :id FOR UPDATE"),
        {"id": organization_id},
    ).scalar_one_or_none()
    if status is None:
        raise NotFoundError("Organização não encontrada")
    return str(status)


def _set_status(
    session: Session,
    principal: Principal,
    origin: Origin,
    organization_id: uuid.UUID,
    status: str,
    event_type: str,
    details: dict[str, Any] | None = None,
) -> None:
    session.execute(
        text(
            "UPDATE identity.organization SET status = CAST(:s AS identity.organization_status),"
            " status_changed_at = now(), status_changed_by = :by, version = version + 1"
            " WHERE id = :id"
        ),
        {"s": status, "by": principal.user_id, "id": organization_id},
    )
    record(
        session, principal, origin,
        event_type=event_type, target_type="organization", target_id=organization_id,
        organization_id=organization_id, details=details,
    )  # fmt: skip


def invite_organization(
    services: Services,
    principal: Principal,
    origin: Origin,
    *,
    name: str,
    admin_name: str,
    admin_email: str,
) -> uuid.UUID:
    """Cria a organização `pending` e convida quem será o seu Administrador (RF-018)."""
    name = name.strip()
    organization_id = uuid.uuid4()
    try:
        with transaction(services.engine, principal.db_context()) as s:
            s.execute(
                text(
                    "INSERT INTO identity.organization (id, name, slug, status, created_by)"
                    " VALUES (:id, :name, :slug, 'pending', :by)"
                ),
                {
                    "id": organization_id,
                    "name": name,
                    "slug": f"{slugify(name)[:48]}-{organization_id.hex[:6]}",
                    "by": principal.user_id,
                },
            )
            record(
                s, principal, origin,
                event_type="org.created", target_type="organization",
                target_id=organization_id, organization_id=organization_id,
                details={"name": name},
            )  # fmt: skip
    except IntegrityError as exc:
        raise ConflictError("Já existe uma organização com este nome.") from exc
    try:
        invitations.invite(
            services, principal, origin,
            email=admin_email, name=admin_name, organization_id=organization_id,
            profile=Profile.ADMINISTRATOR,
        )  # fmt: skip
    except Exception:
        # Sem convite não há organização: cancela a que acabou de nascer.
        with transaction(services.engine, principal.db_context()) as s:
            _set_status(s, principal, origin, organization_id, "cancelled", "org.cancelled")
        raise
    return organization_id


def rename_organization(
    services: Services,
    principal: Principal,
    origin: Origin,
    *,
    organization_id: uuid.UUID,
    name: str,
    expected_version: int | None,
) -> None:
    name = name.strip()
    try:
        with transaction(services.engine, principal.db_context()) as s:
            current = s.execute(
                text("SELECT name, version FROM identity.organization WHERE id = :id FOR UPDATE"),
                {"id": organization_id},
            ).one_or_none()
            if current is None:
                raise NotFoundError("Organização não encontrada")
            if expected_version is not None and current.version != expected_version:
                raise VersionMismatchError(
                    "Outra pessoa alterou esta organização. Recarregue e tente de novo."
                )
            if current.name == name:
                return
            s.execute(
                text(
                    "UPDATE identity.organization SET name = :n, version = version + 1"
                    " WHERE id = :id"
                ),
                {"n": name, "id": organization_id},
            )
            record(
                s, principal, origin,
                event_type="org.renamed", target_type="organization",
                target_id=organization_id, organization_id=organization_id,
                details={"name": name},
            )  # fmt: skip
    except IntegrityError as exc:
        raise ConflictError("Já existe uma organização com este nome.") from exc


def _members(services: Services, organization_id: uuid.UUID) -> list[tuple[uuid.UUID, bool]]:
    """Pessoas da organização e se têm outra organização ativa.

    Contexto de sistema: o Super Administrador não vê os vínculos de outros perfis. Só os
    ids saem daqui, para encerrar sessões; nenhum dado chega à resposta.
    """
    with transaction(services.engine, DbContext.system()) as s:
        rows = s.execute(
            text(
                "SELECT m.user_id, EXISTS ("
                "  SELECT 1 FROM identity.membership o"
                "  JOIN identity.organization og ON og.id = o.organization_id"
                "  WHERE o.user_id = m.user_id AND o.organization_id <> :o"
                "  AND o.status = 'active' AND og.status = 'active') AS elsewhere"
                " FROM identity.membership m WHERE m.organization_id = :o"
                " AND m.status IN ('active', 'pending')"
            ),
            {"o": organization_id},
        ).all()
    return [(r.user_id, r.elsewhere) for r in rows]


def suspend_organization(
    services: Services, principal: Principal, origin: Origin, *, organization_id: uuid.UUID
) -> int:
    """Bloqueia o acesso de todos à organização e preserva os dados (RF-026, CS-009)."""
    members = _members(services, organization_id)
    revoked = 0
    with transaction(services.engine, principal.db_context()) as s:
        status = _lock_status(s, organization_id)
        if status == "suspended":
            return 0
        if status != "active":
            raise ConflictError("Só organizações ativas podem ser suspensas.")
        for user_id, elsewhere in members:
            if elsewhere:
                revoked += services.sessions.delete_for_user_in_organization(
                    user_id, organization_id
                )
            else:
                # BFF antes do Keycloak: o logout no Keycloak dispara o back-channel logout,
                # que também apagaria as sessões e deixaria a contagem errada.
                revoked += services.sessions.delete_all_for_user(user_id)
                services.keycloak_admin.logout(str(user_id))
        _set_status(
            s, principal, origin, organization_id, "suspended", "org.suspended",
            {"sessions_revoked": revoked},
        )  # fmt: skip
    return revoked


def reactivate_organization(
    services: Services, principal: Principal, origin: Origin, *, organization_id: uuid.UUID
) -> None:
    with transaction(services.engine, principal.db_context()) as s:
        status = _lock_status(s, organization_id)
        if status == "active":
            return
        if status != "suspended":
            raise ConflictError("Só organizações suspensas podem ser reativadas.")
        _set_status(s, principal, origin, organization_id, "active", "org.reactivated")


def _pending_invitation(session: Session, organization_id: uuid.UUID) -> Any:
    return session.execute(
        text(
            "SELECT i.id, i.email, i.token_hash IS NOT NULL AS existing_person, u.name"
            " FROM identity.invitation i"
            " LEFT JOIN identity.user_account u ON u.email = i.email"
            " WHERE i.organization_id = :o AND i.status = 'pending'"
            " ORDER BY i.created_at DESC LIMIT 1"
        ),
        {"o": organization_id},
    ).one_or_none()


def resend_invitation(
    services: Services, principal: Principal, origin: Origin, *, organization_id: uuid.UUID
) -> None:
    """Novo link para o Administrador de uma organização ainda pendente."""
    with transaction(services.engine, principal.db_context()) as s:
        if _lock_status(s, organization_id) != "pending":
            raise ConflictError("Só organizações pendentes têm convite para reenviar.")
        pending = _pending_invitation(s, organization_id)
    if pending is None:
        raise NotFoundError("Convite não encontrado")
    if pending.existing_person:
        # Pessoa já cadastrada: o convite tem token próprio; troca por um novo.
        invitations.revoke_invitation(services, principal, origin, invitation_id=pending.id)
    # Pessoa nova ainda sem senha: o mesmo convite reenvia o link de ativação.
    invitations.invite(
        services, principal, origin,
        email=str(pending.email), name=pending.name or str(pending.email),
        organization_id=organization_id, profile=Profile.ADMINISTRATOR,
    )  # fmt: skip
    with transaction(services.engine, principal.db_context()) as s:
        record(
            s, principal, origin,
            event_type="org.invitation_resent", target_type="organization",
            target_id=organization_id, organization_id=organization_id,
        )  # fmt: skip


def cancel_organization(
    services: Services, principal: Principal, origin: Origin, *, organization_id: uuid.UUID
) -> None:
    """Desiste de uma organização pendente; nada é apagado (spec, casos de borda)."""
    with transaction(services.engine, principal.db_context()) as s:
        if _lock_status(s, organization_id) != "pending":
            raise ConflictError("Só organizações pendentes podem ser canceladas.")
        pending = _pending_invitation(s, organization_id)
    if pending is not None:
        invitations.revoke_invitation(services, principal, origin, invitation_id=pending.id)
    with transaction(services.engine, principal.db_context()) as s:
        _set_status(s, principal, origin, organization_id, "cancelled", "org.cancelled")


def invite_administrator(
    services: Services,
    principal: Principal,
    origin: Origin,
    *,
    organization_id: uuid.UUID,
    name: str,
    email: str,
) -> uuid.UUID:
    """Mais um Administrador para uma organização ativa (RF-027)."""
    with transaction(services.engine, principal.db_context()) as s:
        if _lock_status(s, organization_id) != "active":
            raise ConflictError("Só organizações ativas recebem novos Administradores.")
    return invitations.invite(
        services, principal, origin,
        email=email, name=name, organization_id=organization_id,
        profile=Profile.ADMINISTRATOR,
    )  # fmt: skip


def disable_administrator(
    services: Services,
    principal: Principal,
    origin: Origin,
    *,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
) -> None:
    """O RLS só mostra vínculos de Administrador: outros perfis respondem 404."""
    users.disable_membership(
        services, principal, origin, user_id=user_id, organization_id=organization_id
    )


def enable_administrator(
    services: Services,
    principal: Principal,
    origin: Origin,
    *,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
) -> None:
    users.enable_membership(
        services, principal, origin, user_id=user_id, organization_id=organization_id
    )


def activate_pending(session: Session, principal_user: uuid.UUID, origin: Origin) -> None:
    """Organizações pendentes passam a ativas quando o Administrador ativa o acesso (RF-018).

    Chamado na mesma transação que ativa os vínculos (primeiro login ou aceite).
    """
    rows = session.execute(
        text(
            "UPDATE identity.organization o SET status = 'active', status_changed_at = now(),"
            " status_changed_by = :u, version = o.version + 1"
            " FROM identity.membership m WHERE m.organization_id = o.id AND m.user_id = :u"
            " AND m.profile = 'administrator' AND m.status = 'active' AND o.status = 'pending'"
            " RETURNING o.id"
        ),
        {"u": principal_user},
    ).scalars()
    for organization_id in rows.all():
        append_event(
            session,
            AuditEvent.now(
                organization_id=organization_id,
                actor_user_id=principal_user,
                actor_kind="user",
                event_type="org.activated",
                target_type="organization",
                target_id=str(organization_id),
                result="success",
                installation_scope=True,
            ),
            origin,
        )
