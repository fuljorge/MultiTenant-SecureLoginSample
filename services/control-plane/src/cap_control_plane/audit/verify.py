"""Verificação de integridade do Audit Trail (T024; `cap-admin audit verify`)."""

from __future__ import annotations

from datetime import UTC

from sqlalchemy import text
from sqlalchemy.orm import Session

from cap_control_plane.audit.chain import AuditEvent, ChainLink, first_broken_link

_ALL_EVENTS = text(
    "SELECT seq, occurred_at, recorded_at, organization_id, actor_user_id, actor_kind,"
    " event_type, target_type, target_id, result, details, source, source_event_id,"
    " installation_scope, prev_hash, hash FROM audit.audit_event ORDER BY seq"
)


def verify_chain(session: Session) -> int | None:
    """`seq` do primeiro registro adulterado, ou None se a cadeia estiver íntegra.

    Exige contexto de sistema: com RLS, outro contexto veria só parte da cadeia.
    """
    rows = session.execute(_ALL_EVENTS).all()
    links = [
        ChainLink(
            event=AuditEvent(
                occurred_at=r.occurred_at.astimezone(UTC),
                recorded_at=r.recorded_at.astimezone(UTC),
                organization_id=r.organization_id,
                actor_user_id=r.actor_user_id,
                actor_kind=r.actor_kind,
                event_type=r.event_type,
                target_type=r.target_type,
                target_id=r.target_id,
                result=r.result,
                details=r.details,
                source=r.source,
                source_event_id=r.source_event_id,
                installation_scope=r.installation_scope,
            ),
            prev_hash=bytes(r.prev_hash),
            hash=bytes(r.hash),
        )
        for r in rows
    ]
    broken = first_broken_link(links)
    return None if broken is None else int(rows[broken].seq)
