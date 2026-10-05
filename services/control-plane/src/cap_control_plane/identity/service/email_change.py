"""Troca de e-mail pelo Administrador (T051; US3 cenário 6; RF-009).

O novo e-mail só vale depois que a pessoa o confirma pelo link (24 h, uso único). Na
confirmação, as sessões são encerradas e o e-mail antigo recebe um aviso.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import text

from cap_control_plane.audit.chain import AuditEvent
from cap_control_plane.audit.writer import Origin, append_event
from cap_control_plane.core.db import DbContext, transaction
from cap_control_plane.core.email import email_change_confirmation, email_changed_notice
from cap_control_plane.identity.authz import Principal
from cap_control_plane.identity.service.common import (
    ConflictError,
    NotFoundError,
    new_token,
    record,
    token_hash,
)
from cap_control_plane.identity.service.users import ensure_only_in_organization, get_user
from cap_control_plane.services import Services

CONFIRMATION_VALID_HOURS = 24


def _email_in_use(email: str, services: Services) -> bool:
    with transaction(services.engine, DbContext.system()) as s:
        return bool(
            s.execute(
                text("SELECT 1 FROM identity.user_account WHERE email = :e"), {"e": email}
            ).first()
        )


def request_email_change(
    services: Services,
    principal: Principal,
    origin: Origin,
    *,
    user_id: uuid.UUID,
    new_email: str,
) -> None:
    view = get_user(services, principal, user_id, origin)
    ensure_only_in_organization(services, principal, user_id)
    new_email = new_email.strip().lower()
    if new_email == view.email:
        raise ConflictError("O novo e-mail é igual ao atual.")
    if _email_in_use(new_email, services):
        raise ConflictError("Este e-mail já pertence a outra pessoa.")
    token, hashed = new_token()
    with transaction(services.engine, principal.db_context()) as s:
        # Só o pedido mais recente vale.
        s.execute(
            text(
                "UPDATE identity.email_change_request SET status = 'revoked'"
                " WHERE user_id = :u AND status = 'pending'"
            ),
            {"u": user_id},
        )
        s.execute(
            text(
                "INSERT INTO identity.email_change_request"
                " (user_id, new_email, token_hash, expires_at, requested_by)"
                " VALUES (:u, :e, :h, :x, :by)"
            ),
            {"u": user_id, "e": new_email, "h": hashed,
             "x": datetime.now(UTC) + timedelta(hours=CONFIRMATION_VALID_HOURS),
             "by": principal.user_id},
        )  # fmt: skip
        record(
            s, principal, origin,
            event_type="user.email_change_requested", target_type="user", target_id=user_id,
        )  # fmt: skip
    link = f"{services.settings.public_url}/confirmar-email/{token}"
    services.mailer.send(email_change_confirmation(new_email, link, CONFIRMATION_VALID_HOURS))


def confirm_email_change(services: Services, origin: Origin, *, token: str) -> None:
    """Confirmação pelo link (sem sessão): troca o e-mail no Keycloak e no Control Plane."""
    with transaction(services.engine, DbContext.system()) as s:
        request = s.execute(
            text(
                "SELECT r.id, r.user_id, r.new_email, r.expires_at, r.status, u.email AS old_email"
                " FROM identity.email_change_request r"
                " JOIN identity.user_account u ON u.id = r.user_id"
                " WHERE r.token_hash = :h FOR UPDATE OF r"
            ),
            {"h": token_hash(token)},
        ).one_or_none()
        if request is None or request.status != "pending":
            raise NotFoundError("Link inválido ou já utilizado")
        if request.expires_at <= datetime.now(UTC):
            s.execute(
                text("UPDATE identity.email_change_request SET status = 'expired' WHERE id = :id"),
                {"id": request.id},
            )
            raise ConflictError("Este link expirou. Peça uma nova troca ao Administrador.")
        taken = s.execute(
            text("SELECT 1 FROM identity.user_account WHERE email = :e AND id <> :u"),
            {"e": request.new_email, "u": request.user_id},
        ).first()
        if taken:
            raise ConflictError("Este e-mail já pertence a outra pessoa.")
        s.execute(
            text(
                "UPDATE identity.user_account SET email = :e, version = version + 1,"
                " updated_at = now() WHERE id = :u"
            ),
            {"e": request.new_email, "u": request.user_id},
        )
        s.execute(
            text(
                "UPDATE identity.email_change_request SET status = 'confirmed',"
                " confirmed_at = now() WHERE id = :id"
            ),
            {"id": request.id},
        )
        # Keycloak antes do commit: se falhar, nada muda e o link continua valendo.
        services.keycloak_admin.update_email(str(request.user_id), str(request.new_email))
        services.keycloak_admin.logout(str(request.user_id))
        append_event(
            s,
            AuditEvent.now(
                organization_id=None,
                actor_user_id=request.user_id,
                actor_kind="user",
                event_type="user.email_changed",
                target_type="user",
                target_id=str(request.user_id),
                result="success",
            ),
            origin,
        )
    services.sessions.delete_all_for_user(uuid.UUID(str(request.user_id)))
    services.mailer.send(email_changed_notice(str(request.old_email)))
