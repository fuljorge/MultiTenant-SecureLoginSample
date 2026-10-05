"""Expurgo de IP e navegador antigos do Audit Trail (T069; RNF-002; data-model.md).

`audit_event_origin` fica fora da cadeia de hash justamente para poder ser apagada após
o prazo de retenção: os eventos continuam e a cadeia continua verificável. Roda uma vez
por dia no `cap-worker`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import text

from cap_control_plane.audit.chain import AuditEvent
from cap_control_plane.audit.writer import append_event
from cap_control_plane.core.db import DbContext, transaction
from cap_control_plane.services import Services


def purge_origins(services: Services, *, retention_days: int | None = None) -> int:
    """Apaga a origem dos eventos gravados antes do prazo; devolve quantas linhas saíram."""
    days = retention_days or services.settings.audit_origin_retention_days
    cutoff = datetime.now(UTC) - timedelta(days=days)
    with transaction(services.engine, DbContext.system()) as s:
        removed = s.execute(
            text(
                "DELETE FROM audit.audit_event_origin o USING audit.audit_event e"
                " WHERE e.seq = o.seq AND e.recorded_at < :cutoff RETURNING o.seq"
            ),
            {"cutoff": cutoff},
        ).scalars().all()  # fmt: skip
        if removed:
            append_event(
                s,
                AuditEvent.now(
                    organization_id=None,
                    actor_user_id=None,
                    actor_kind="system",
                    event_type="audit.origin_purged",
                    target_type="audit_event_origin",
                    target_id=None,
                    result="success",
                    details={
                        "rows": len(removed),
                        "first_seq": min(removed),
                        "last_seq": max(removed),
                        "retention_days": days,
                    },
                    installation_scope=True,
                ),
            )
    return len(removed)
