"""Ativação da pessoa convidada no primeiro login (T045; US2, US3).

Quem foi convidado (ou criado pelo provisionamento) fica `invited`, com vínculos `pending`, até
concluir o primeiro login com senha e código. Vínculos removidos antes disso continuam
removidos.
"""

from __future__ import annotations

import uuid

from sqlalchemy import Engine, text

from cap_control_plane.audit.chain import AuditEvent
from cap_control_plane.audit.writer import Origin, append_event
from cap_control_plane.core.db import DbContext, transaction
from cap_control_plane.identity.service.organizations import activate_pending


def activate_on_first_login(engine: Engine, user_id: uuid.UUID, origin: Origin) -> bool:
    """Ativa a pessoa se ainda estiver convidada. Devolve True se ativou agora."""
    with transaction(engine, DbContext.system()) as s:
        activated = s.execute(
            text(
                "UPDATE identity.user_account SET status = 'active', updated_at = now(),"
                " version = version + 1 WHERE id = :id AND status = 'invited' RETURNING id"
            ),
            {"id": user_id},
        ).scalar_one_or_none()
        if activated is None:
            return False
        rows = s.execute(
            text(
                "UPDATE identity.membership SET status = 'active', updated_at = now(),"
                " version = version + 1 WHERE user_id = :id AND status = 'pending'"
                " RETURNING organization_id, created_by"
            ),
            {"id": user_id},
        ).all()
        activate_pending(s, user_id, origin)
        # Convite de pessoa nova (sem token próprio) passa a aceito.
        s.execute(
            text(
                "UPDATE identity.invitation i SET status = 'accepted', accepted_at = now()"
                " FROM identity.user_account u WHERE u.id = :id AND i.email = u.email"
                " AND i.status = 'pending' AND i.token_hash IS NULL"
            ),
            {"id": user_id},
        )
        super_admin = s.execute(
            text("SELECT granted_by FROM identity.super_admin WHERE user_id = :id"),
            {"id": user_id},
        ).one_or_none()
        # Super Administrador sem quem o convidou: criado pelo provisionamento (§53.2).
        bootstrap = super_admin is not None and super_admin.granted_by is None
        via = "bootstrap" if bootstrap else "invitation"
        append_event(
            s,
            AuditEvent.now(
                organization_id=rows[0].organization_id if rows else None,
                actor_user_id=user_id,
                actor_kind="user",
                event_type="user.activated",
                target_type="user",
                target_id=str(user_id),
                result="success",
                details={"via": via},
                installation_scope=super_admin is not None,
            ),
            origin,
        )
    return True
