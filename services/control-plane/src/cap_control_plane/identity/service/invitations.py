"""Convites (T050; US3 cenário 1; RF-009, RF-010; plano §4.3).

- Pessoa nova: criada no Keycloak sem senha, `invited`, com vínculo `pending`; recebe o
  e-mail de ativação do Keycloak. Reconvidar quem ainda não ativou reenvia o link.
- Pessoa já cadastrada: convite com token próprio (só o hash no banco), aceito com a
  pessoa logada; o vínculo nasce no aceite.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import text

from cap_control_plane.audit.writer import Origin
from cap_control_plane.core.db import DbContext, transaction
from cap_control_plane.core.email import invitation_existing_user
from cap_control_plane.identity.authz import Principal
from cap_control_plane.identity.permissions import Profile
from cap_control_plane.identity.service.common import (
    ConflictError,
    NotFoundError,
    ScopeError,
    new_token,
    record,
    token_hash,
)
from cap_control_plane.services import Services


@dataclass(frozen=True)
class InvitationView:
    id: uuid.UUID
    email: str
    profile: str
    status: str
    expires_at: datetime
    existing_person: bool


def _check_org_scope(principal: Principal, organization_id: uuid.UUID) -> None:
    if principal.is_super_admin:
        return  # Super Administrador: só convites de Administrador, garantidos pelo RLS.
    if organization_id != principal.organization_id:
        raise ScopeError("Você só pode convidar para a sua organização.")


def invite(
    services: Services,
    principal: Principal,
    origin: Origin,
    *,
    email: str,
    name: str,
    organization_id: uuid.UUID,
    profile: Profile,
) -> uuid.UUID:
    _check_org_scope(principal, organization_id)
    email = email.strip().lower()
    valid_hours = services.security.invitation_valid_hours()
    expires_at = datetime.now(UTC) + timedelta(hours=valid_hours)

    # A pessoa pode existir em outra organização: a busca ignora o RLS de propósito.
    with transaction(services.engine, DbContext.system()) as s:
        person = s.execute(
            text(
                "SELECT u.id, u.status, u.name,"
                " EXISTS (SELECT 1 FROM identity.super_admin a WHERE a.user_id = u.id)"
                " AS is_super_admin FROM identity.user_account u WHERE u.email = :e"
            ),
            {"e": email},
        ).one_or_none()
        organization = s.execute(
            text("SELECT name FROM identity.organization WHERE id = :o"), {"o": organization_id}
        ).scalar_one_or_none()
        if organization is None:
            raise NotFoundError("Organização não encontrada")
        if person is not None:
            membership = s.execute(
                text(
                    "SELECT status FROM identity.membership"
                    " WHERE user_id = :u AND organization_id = :o"
                ),
                {"u": person.id, "o": organization_id},
            ).scalar_one_or_none()

    if person is None:
        return _invite_new_person(
            services, principal, origin, email, name, organization_id, profile, expires_at
        )
    if person.is_super_admin:
        # RF-028: o Super Administrador não tem vínculo com organizações.
        raise ConflictError("Este e-mail é de um Super Administrador e não pode ser convidado.")
    if person.status == "disabled":
        raise ConflictError("Esta pessoa está desativada. Reative a conta antes de convidar.")
    if person.status == "invited" and membership == "pending":
        # Ainda não ativou: reenvia o link (novo prazo).
        services.keycloak_admin.send_activation_email(
            str(person.id), lifespan_seconds=valid_hours * 3600
        )
        with transaction(services.engine, principal.db_context()) as s:
            invitation_id = s.execute(
                text(
                    "UPDATE identity.invitation SET expires_at = :x WHERE organization_id = :o"
                    " AND email = :e AND status = 'pending' AND token_hash IS NULL RETURNING id"
                ),
                {"x": expires_at, "o": organization_id, "e": email},
            ).scalar_one()
            record(
                s, principal, origin,
                event_type="user.invited", target_type="user", target_id=person.id,
                organization_id=organization_id,
                details={"profile": profile.value, "resent": True},
            )  # fmt: skip
        return uuid.UUID(str(invitation_id))
    if membership in ("active", "pending"):
        raise ConflictError("Esta pessoa já pertence à organização.")
    return _invite_existing_person(
        services, principal, origin, person.id, email, organization, organization_id, profile,
        expires_at, valid_hours,
    )  # fmt: skip


def _invite_new_person(
    services: Services,
    principal: Principal,
    origin: Origin,
    email: str,
    name: str,
    organization_id: uuid.UUID,
    profile: Profile,
    expires_at: datetime,
) -> uuid.UUID:
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
            text(
                "INSERT INTO identity.membership"
                " (organization_id, user_id, profile, status, created_by)"
                " VALUES (:o, :u, :p, 'pending', :by)"
            ),
            {"o": organization_id, "u": user_id, "p": profile.value, "by": principal.user_id},
        )
        invitation_id = s.execute(
            text(
                "INSERT INTO identity.invitation"
                " (organization_id, email, profile, expires_at, invited_by)"
                " VALUES (:o, :e, :p, :x, :by) RETURNING id"
            ),
            {"o": organization_id, "e": email, "p": profile.value, "x": expires_at,
             "by": principal.user_id},
        ).scalar_one()  # fmt: skip
        record(
            s, principal, origin,
            event_type="user.invited", target_type="user", target_id=user_id,
            organization_id=organization_id, details={"profile": profile.value},
        )  # fmt: skip
    lifespan = int((expires_at - datetime.now(UTC)).total_seconds())
    kc.send_activation_email(str(user_id), lifespan_seconds=lifespan)
    return uuid.UUID(str(invitation_id))


def _invite_existing_person(
    services: Services,
    principal: Principal,
    origin: Origin,
    user_id: uuid.UUID,
    email: str,
    organization_name: str,
    organization_id: uuid.UUID,
    profile: Profile,
    expires_at: datetime,
    valid_hours: int,
) -> uuid.UUID:
    token, hashed = new_token()
    with transaction(services.engine, principal.db_context()) as s:
        pending = s.execute(
            text(
                "SELECT 1 FROM identity.invitation WHERE organization_id = :o AND email = :e"
                " AND status = 'pending' AND expires_at > now()"
            ),
            {"o": organization_id, "e": email},
        ).first()
        if pending:
            raise ConflictError("Já existe um convite pendente para esta pessoa.")
        invitation_id = s.execute(
            text(
                "INSERT INTO identity.invitation"
                " (organization_id, email, profile, token_hash, expires_at, invited_by)"
                " VALUES (:o, :e, :p, :h, :x, :by) RETURNING id"
            ),
            {"o": organization_id, "e": email, "p": profile.value, "h": hashed,
             "x": expires_at, "by": principal.user_id},
        ).scalar_one()  # fmt: skip
        record(
            s, principal, origin,
            event_type="user.invited", target_type="user", target_id=user_id,
            organization_id=organization_id,
            details={"profile": profile.value, "existing_person": True},
        )  # fmt: skip
    link = f"{services.settings.public_url}/convites/{token}"
    services.mailer.send(invitation_existing_user(email, organization_name, link, valid_hours))
    return uuid.UUID(str(invitation_id))


def list_invitations(
    services: Services, principal: Principal, organization_id: uuid.UUID | None = None
) -> list[InvitationView]:
    org = organization_id if principal.is_super_admin else principal.organization_id
    with transaction(services.engine, principal.db_context()) as s:
        rows = s.execute(
            text(
                "SELECT id, email, profile::text AS profile,"
                " CASE WHEN status = 'pending' AND expires_at <= now() THEN 'expired'"
                "      ELSE status::text END AS status,"
                " expires_at, token_hash IS NOT NULL AS existing_person"
                " FROM identity.invitation WHERE organization_id = :o AND status = 'pending'"
                " ORDER BY created_at DESC"
            ),
            {"o": org},
        ).all()
    return [
        InvitationView(r.id, str(r.email), r.profile, r.status, r.expires_at, r.existing_person)
        for r in rows
    ]


def revoke_invitation(
    services: Services, principal: Principal, origin: Origin, *, invitation_id: uuid.UUID
) -> None:
    with transaction(services.engine, principal.db_context()) as s:
        invitation = s.execute(
            text(
                "UPDATE identity.invitation SET status = 'revoked' WHERE id = :id"
                " AND status = 'pending' RETURNING organization_id, email, token_hash"
            ),
            {"id": invitation_id},
        ).one_or_none()
        if invitation is None:
            raise NotFoundError("Convite não encontrado")
        _check_org_scope(principal, invitation.organization_id)
        user_id = None
        if invitation.token_hash is None:
            # Pessoa nova que ainda não ativou: o vínculo pendente deixa de existir.
            user_id = s.execute(
                text(
                    "UPDATE identity.membership m SET status = 'removed', updated_at = now()"
                    " FROM identity.user_account u WHERE u.id = m.user_id AND u.email = :e"
                    " AND m.organization_id = :o AND m.status = 'pending' RETURNING m.user_id"
                ),
                {"e": invitation.email, "o": invitation.organization_id},
            ).scalar_one_or_none()
        record(
            s, principal, origin,
            event_type="user.invitation_revoked", target_type="invitation",
            target_id=invitation_id, organization_id=invitation.organization_id,
        )  # fmt: skip
    if user_id is not None:
        _disable_if_orphan(services, uuid.UUID(str(user_id)))


def _disable_if_orphan(services: Services, user_id: uuid.UUID) -> None:
    """Convidada sem nenhum vínculo restante não pode ativar a conta."""
    with transaction(services.engine, DbContext.system()) as s:
        orphan = s.execute(
            text(
                "UPDATE identity.user_account SET status = 'disabled', version = version + 1"
                " WHERE id = :u AND status = 'invited' AND NOT EXISTS ("
                "  SELECT 1 FROM identity.membership WHERE user_id = :u AND status <> 'removed')"
                " RETURNING id"
            ),
            {"u": user_id},
        ).scalar_one_or_none()
    if orphan is not None:
        services.keycloak_admin.set_enabled(str(user_id), enabled=False)


def accept_invitation(
    services: Services, principal: Principal, origin: Origin, *, token: str
) -> uuid.UUID:
    """Aceite pela pessoa logada. Devolve a organização; outro e-mail recebe 404."""
    with transaction(services.engine, DbContext.system()) as s:
        invitation = s.execute(
            text(
                "SELECT i.id, i.organization_id, i.profile::text AS profile, i.invited_by,"
                " i.expires_at, i.status FROM identity.invitation i"
                " JOIN identity.user_account u ON u.email = i.email"
                " WHERE i.token_hash = :h AND u.id = :u FOR UPDATE OF i"
            ),
            {"h": token_hash(token), "u": principal.user_id},
        ).one_or_none()
        if invitation is None or invitation.status != "pending":
            raise NotFoundError("Convite não encontrado ou já utilizado")
        if invitation.expires_at <= datetime.now(UTC):
            s.execute(
                text("UPDATE identity.invitation SET status = 'expired' WHERE id = :id"),
                {"id": invitation.id},
            )
            raise ConflictError("Este convite expirou. Peça um novo ao Administrador.")
        s.execute(
            text(
                "INSERT INTO identity.membership"
                " (organization_id, user_id, profile, status, created_by)"
                " VALUES (:o, :u, :p, 'active', :by)"
                " ON CONFLICT (organization_id, user_id) DO UPDATE SET status = 'active',"
                " profile = EXCLUDED.profile, version = identity.membership.version + 1,"
                " updated_at = now()"
            ),
            {"o": invitation.organization_id, "u": principal.user_id,
             "p": invitation.profile, "by": invitation.invited_by},
        )  # fmt: skip
        s.execute(
            text(
                "UPDATE identity.invitation SET status = 'accepted', accepted_at = now()"
                " WHERE id = :id"
            ),
            {"id": invitation.id},
        )
        record(
            s, principal, origin,
            event_type="user.membership_added", target_type="user", target_id=principal.user_id,
            organization_id=invitation.organization_id, details={"profile": invitation.profile},
        )  # fmt: skip
        # Convite de organização aceito por quem já tem conta: a organização fica ativa.
        # Import local: organizations importa este módulo.
        from cap_control_plane.identity.service.organizations import activate_pending

        activate_pending(s, principal.user_id, origin)
    return uuid.UUID(str(invitation.organization_id))
