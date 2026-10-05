"""Gestão de usuários pelo Administrador da organização (T050, T087; US3; RF-009, RF-011,
RF-012, RF-017).

O isolamento entre organizações vem do RLS (contexto do principal). O Administrador só
age sobre a organização ativa. Desativar e reativar agem sobre o **vínculo** com a
organização: na instalação compartilhada, uma organização não pode tirar o acesso de uma
pessoa a outra (plano §4.4). A conta só é desativada quando a pessoa fica sem nenhum
vínculo ativo.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from cap_control_plane.audit.writer import Origin
from cap_control_plane.core.db import DbContext, transaction
from cap_control_plane.identity.authz import Principal
from cap_control_plane.identity.permissions import Profile
from cap_control_plane.identity.service.common import (
    ConflictError,
    NotFoundError,
    VersionMismatchError,
    record,
)
from cap_control_plane.services import Services


@dataclass(frozen=True)
class MembershipView:
    organization_id: uuid.UUID
    organization_name: str
    profile: str
    status: str
    version: int


@dataclass(frozen=True)
class UserView:
    id: uuid.UUID
    name: str
    email: str
    # Situação na organização: convidado, ativo ou desativado (conta ou vínculo).
    status: str
    last_login_at: datetime | None
    version: int
    memberships: list[MembershipView]


# Situação na organização: a conta ou o vínculo desativados contam como desativado.
_USERS_SQL = """
SELECT u.id, u.name, u.email, u.last_login_at, u.version,
       CASE WHEN u.status = 'invited' THEN 'invited'
            WHEN u.status = 'disabled' OR om.status = 'disabled' THEN 'disabled'
            ELSE 'active' END AS status,
       coalesce(
         json_agg(json_build_object(
           'organization_id', m.organization_id, 'organization_name', o.name,
           'profile', m.profile, 'status', m.status, 'version', m.version
         ) ORDER BY o.name) FILTER (WHERE m.id IS NOT NULL),
         '[]'::json
       ) AS memberships
FROM identity.user_account u
JOIN identity.membership om
  ON om.user_id = u.id AND om.organization_id = :org AND om.status <> 'removed'
LEFT JOIN identity.membership m ON m.user_id = u.id AND m.status <> 'removed'
LEFT JOIN identity.organization o ON o.id = m.organization_id
WHERE u.anonymized_at IS NULL
  AND (CAST(:profile AS text) IS NULL OR om.profile::text = :profile)
  AND (CAST(:q AS text) IS NULL OR u.name ILIKE :q OR u.email ILIKE :q)
  {extra}
GROUP BY u.id, om.status
HAVING (CAST(:status AS text) IS NULL OR CASE WHEN u.status = 'invited' THEN 'invited'
            WHEN u.status = 'disabled' OR om.status = 'disabled' THEN 'disabled'
            ELSE 'active' END = :status)
ORDER BY u.name
LIMIT :limit OFFSET :offset
"""


def _to_view(row: Any) -> UserView:
    return UserView(
        id=row.id,
        name=row.name,
        email=str(row.email),
        status=row.status,
        last_login_at=row.last_login_at,
        version=row.version,
        memberships=[
            MembershipView(
                organization_id=uuid.UUID(m["organization_id"]),
                organization_name=m["organization_name"],
                profile=m["profile"],
                status=m["status"],
                version=m["version"],
            )
            for m in row.memberships
        ],
    )


def list_users(
    services: Services,
    principal: Principal,
    *,
    query: str | None = None,
    profile: str | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[UserView]:
    """Pessoas da organização ativa."""
    with transaction(services.engine, principal.db_context()) as s:
        rows = s.execute(
            text(_USERS_SQL.format(extra="")),
            {
                "org": principal.organization_id,
                "profile": profile,
                "status": status,
                "q": f"%{query.strip()}%" if query and query.strip() else None,
                "limit": min(max(limit, 1), 200),
                "offset": max(offset, 0),
            },
        ).all()
    return [_to_view(r) for r in rows]


def get_user(
    services: Services, principal: Principal, user_id: uuid.UUID, origin: Origin | None = None
) -> UserView:
    with transaction(services.engine, principal.db_context()) as s:
        row = s.execute(
            text(_USERS_SQL.format(extra="AND u.id = :id")),
            {
                "id": user_id, "org": principal.organization_id, "profile": None,
                "status": None, "q": None, "limit": 1, "offset": 0,
            },
        ).one_or_none()  # fmt: skip
    if row is None:
        raise not_found(services, principal, user_id, origin)
    return _to_view(row)


def not_found(
    services: Services, principal: Principal, user_id: uuid.UUID, origin: Origin | None
) -> NotFoundError:
    """Pessoa fora da organização responde como inexistente (não revela que existe).

    Se ela existe em outra organização, a tentativa fica no Audit Trail como acesso negado
    (US5, cenário 8). A consulta ignora o RLS e só devolve se a pessoa existe fora daqui.
    """
    if principal.organization_id is not None:
        with transaction(services.engine, DbContext.system()) as s:
            elsewhere = s.execute(
                text(
                    "SELECT EXISTS (SELECT 1 FROM identity.user_account WHERE id = :u)"
                    " AND NOT EXISTS (SELECT 1 FROM identity.membership WHERE user_id = :u"
                    "  AND organization_id = :o AND status <> 'removed')"
                ),
                {"u": user_id, "o": principal.organization_id},
            ).scalar_one()
        if elsewhere:
            with transaction(services.engine, principal.db_context()) as s:
                record(
                    s, principal, origin or Origin(),
                    event_type="access.denied", target_type="user", target_id=user_id,
                    result="denied", details={"reason": "other_organization"},
                )  # fmt: skip
    return NotFoundError("Pessoa não encontrada")


def _active_organization(principal: Principal) -> uuid.UUID:
    """Organização ativa de quem age; as rotas de usuários exigem uma (RF-028)."""
    if principal.organization_id is None:
        raise NotFoundError("Pessoa não encontrada")
    return principal.organization_id


def belongs_elsewhere(services: Services, user_id: uuid.UUID, organization_id: uuid.UUID) -> bool:
    """Se a pessoa tem vínculo ativo ou pendente com outra organização.

    Consulta em contexto de sistema: com RLS, o Administrador de organização não enxerga os
    vínculos com outras organizações. Só o booleano sai daqui; nenhum dado de outra
    organização chega ao chamador.
    """
    with transaction(services.engine, DbContext.system()) as s:
        others = s.execute(
            text(
                "SELECT count(*) FROM identity.membership WHERE user_id = :u"
                " AND organization_id <> :o AND status IN ('active', 'pending')"
            ),
            {"u": user_id, "o": organization_id},
        ).scalar_one()
    return bool(others)


def ensure_only_in_organization(
    services: Services, principal: Principal, user_id: uuid.UUID
) -> None:
    """Ações sobre a conta inteira (ex.: trocar o e-mail) só para quem é só desta organização."""
    if belongs_elsewhere(services, user_id, _active_organization(principal)):
        raise ConflictError(
            "Esta pessoa também pertence a outras organizações; "
            "a alteração afetaria o acesso dela a elas."
        )


def ensure_not_last_admin(session: Session, organization_id: uuid.UUID, user_id: uuid.UUID) -> None:
    """RF-012: uma organização nunca fica sem Administrador ativo.

    Trava os vínculos de Administrador da organização: duas desativações simultâneas não
    passam juntas. Trava também as contas: com READ COMMITTED, quem espera reavalia só as
    linhas travadas.
    """
    admins = (
        session.execute(
            text(
                "SELECT m.user_id FROM identity.membership m"
                " JOIN identity.user_account u ON u.id = m.user_id"
                " WHERE m.organization_id = :o AND m.profile = 'administrator'"
                " AND m.status = 'active' AND u.status = 'active' FOR UPDATE OF m, u"
            ),
            {"o": organization_id},
        )
        .scalars()
        .all()
    )
    if user_id in admins and len(admins) == 1:
        raise ConflictError("A organização precisa de pelo menos um Administrador ativo.")


def change_profile(
    services: Services,
    principal: Principal,
    origin: Origin,
    *,
    user_id: uuid.UUID,
    organization_id: uuid.UUID,
    profile: Profile,
    expected_version: int | None,
) -> None:
    """Altera o perfil na organização (RF-009); vale na próxima ação da pessoa (RF-017)."""
    with transaction(services.engine, principal.db_context()) as s:
        current = s.execute(
            text(
                "SELECT profile::text, version FROM identity.membership"
                " WHERE user_id = :u AND organization_id = :o AND status <> 'removed' FOR UPDATE"
            ),
            {"u": user_id, "o": organization_id},
        ).one_or_none()
        if current is None:
            raise not_found(services, principal, user_id, origin)
        if expected_version is not None and current.version != expected_version:
            raise VersionMismatchError(
                "Outra pessoa alterou este vínculo. Recarregue e tente de novo."
            )
        if current.profile == profile.value:
            return
        if current.profile == Profile.ADMINISTRATOR.value:
            ensure_not_last_admin(s, organization_id, user_id)
        s.execute(
            text(
                "UPDATE identity.membership SET profile = :p, version = version + 1,"
                " updated_at = now() WHERE user_id = :u AND organization_id = :o"
            ),
            {"p": profile.value, "u": user_id, "o": organization_id},
        )
        record(
            s, principal, origin,
            event_type="user.profile_changed", target_type="user", target_id=user_id,
            organization_id=organization_id,
            details={"from": current.profile, "to": profile.value},
        )  # fmt: skip


def remove_membership(
    services: Services,
    principal: Principal,
    origin: Origin,
    *,
    user_id: uuid.UUID,
    organization_id: uuid.UUID,
) -> None:
    with transaction(services.engine, principal.db_context()) as s:
        ensure_not_last_admin(s, organization_id, user_id)
        profile = s.execute(
            text(
                "UPDATE identity.membership SET status = 'removed', version = version + 1,"
                " updated_at = now() WHERE user_id = :u AND organization_id = :o"
                " AND status <> 'removed' RETURNING profile::text"
            ),
            {"u": user_id, "o": organization_id},
        ).scalar_one_or_none()
        if profile is None:
            raise not_found(services, principal, user_id, origin)
        record(
            s, principal, origin,
            event_type="user.membership_removed", target_type="user", target_id=user_id,
            organization_id=organization_id, details={"profile": profile},
        )  # fmt: skip
    services.sessions.delete_for_user_in_organization(user_id, organization_id)


def disable_membership(
    services: Services,
    principal: Principal,
    origin: Origin,
    *,
    user_id: uuid.UUID,
    organization_id: uuid.UUID,
) -> None:
    """Tira o acesso da pessoa à organização e encerra as sessões nela (RF-011).

    Sem outro vínculo ativo, a conta também é desativada no Keycloak. Usado pelo
    Administrador da organização (US3) e pelo Super Administrador (RF-027).
    """
    if user_id == principal.user_id:
        raise ConflictError("Você não pode desativar o seu próprio acesso.")
    elsewhere = belongs_elsewhere(services, user_id, organization_id)
    with transaction(services.engine, principal.db_context()) as s:
        membership = s.execute(
            text(
                "SELECT status::text, profile::text FROM identity.membership"
                " WHERE user_id = :u AND organization_id = :o AND status <> 'removed'"
                " FOR UPDATE"
            ),
            {"u": user_id, "o": organization_id},
        ).one_or_none()
        if membership is None:
            raise not_found(services, principal, user_id, origin)
        if membership.status == "disabled":
            return
        if membership.profile == Profile.ADMINISTRATOR.value:
            ensure_not_last_admin(s, organization_id, user_id)
        s.execute(
            text(
                "UPDATE identity.membership SET status = 'disabled', version = version + 1,"
                " updated_at = now() WHERE user_id = :u AND organization_id = :o"
            ),
            {"u": user_id, "o": organization_id},
        )
        record(
            s, principal, origin,
            event_type="user.membership_disabled", target_type="user", target_id=user_id,
            organization_id=organization_id, details={"profile": membership.profile},
        )  # fmt: skip
        if not elsewhere:
            s.execute(
                text(
                    "UPDATE identity.user_account SET status = 'disabled',"
                    " version = version + 1, updated_at = now()"
                    " WHERE id = :id AND status <> 'disabled'"
                ),
                {"id": user_id},
            )
            # Keycloak antes do commit: se falhar, a desativação é desfeita e pode ser
            # repetida.
            services.keycloak_admin.set_enabled(str(user_id), enabled=False)
            services.keycloak_admin.logout(str(user_id))
            record(
                s, principal, origin,
                event_type="user.disabled", target_type="user", target_id=user_id,
                organization_id=organization_id,
            )  # fmt: skip
    if elsewhere:
        services.sessions.delete_for_user_in_organization(user_id, organization_id)
    else:
        services.sessions.delete_all_for_user(user_id)


def enable_membership(
    services: Services,
    principal: Principal,
    origin: Origin,
    *,
    user_id: uuid.UUID,
    organization_id: uuid.UUID,
) -> None:
    """Devolve o acesso à organização, com o mesmo perfil, após novo login (US3, cenário 4)."""
    with transaction(services.engine, principal.db_context()) as s:
        state = s.execute(
            text(
                "SELECT m.status::text AS membership, m.profile::text AS profile,"
                " u.status::text AS account FROM identity.membership m"
                " JOIN identity.user_account u ON u.id = m.user_id"
                " WHERE m.user_id = :u AND m.organization_id = :o AND m.status <> 'removed'"
                " FOR UPDATE OF m"
            ),
            {"u": user_id, "o": organization_id},
        ).one_or_none()
        if state is None:
            raise not_found(services, principal, user_id, origin)
        if state.membership == "disabled":
            s.execute(
                text(
                    "UPDATE identity.membership SET status = 'active', version = version + 1,"
                    " updated_at = now() WHERE user_id = :u AND organization_id = :o"
                ),
                {"u": user_id, "o": organization_id},
            )
            record(
                s, principal, origin,
                event_type="user.membership_enabled", target_type="user", target_id=user_id,
                organization_id=organization_id, details={"profile": state.profile},
            )  # fmt: skip
        if state.account == "disabled":
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
                event_type="user.enabled", target_type="user", target_id=user_id,
                organization_id=organization_id,
            )  # fmt: skip


def disable_user(
    services: Services, principal: Principal, origin: Origin, *, user_id: uuid.UUID
) -> None:
    """Desativação pelo Administrador da organização ativa (US3, cenário 3)."""
    disable_membership(
        services, principal, origin, user_id=user_id,
        organization_id=_active_organization(principal),
    )  # fmt: skip


def enable_user(
    services: Services, principal: Principal, origin: Origin, *, user_id: uuid.UUID
) -> None:
    enable_membership(
        services, principal, origin, user_id=user_id,
        organization_id=_active_organization(principal),
    )  # fmt: skip


def revoke_sessions(
    services: Services, principal: Principal, origin: Origin, *, user_id: uuid.UUID
) -> int:
    """Encerra as sessões da pessoa nesta organização; se ela não tem outra, todas."""
    organization_id = _active_organization(principal)
    get_user(services, principal, user_id, origin)  # 404 para pessoa fora da organização
    if belongs_elsewhere(services, user_id, organization_id):
        count = services.sessions.delete_for_user_in_organization(user_id, organization_id)
    else:
        services.keycloak_admin.logout(str(user_id))
        count = services.sessions.delete_all_for_user(user_id)
    with transaction(services.engine, principal.db_context()) as s:
        record(
            s, principal, origin,
            event_type="auth.session_revoked", target_type="user", target_id=user_id,
            details={"revoked_by": "administrator", "count": count},
        )  # fmt: skip
    return count


def is_blocked(services: Services, user_id: uuid.UUID) -> bool:
    """Bloqueio temporário por tentativas (Keycloak). Consultado só no detalhe da pessoa."""
    try:
        return bool(services.keycloak_admin.brute_force_status(str(user_id)).get("disabled"))
    except Exception:  # Keycloak indisponível não impede ver o detalhe.
        return False
