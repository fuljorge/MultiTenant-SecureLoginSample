"""Gravação de eventos no Audit Trail (T024).

O evento é gravado na mesma transação da operação auditada: se a operação falha, o
evento também não é gravado, e vice-versa. A linha `audit.chain_head` é travada durante
a gravação, o que serializa os gravadores e dá o hash anterior sem depender de RLS.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session

from cap_control_plane.audit.chain import AuditEvent, link_hash


@dataclass(frozen=True)
class Origin:
    """De onde veio a ação (RF-022). Fica fora da cadeia de hash (retenção LGPD)."""

    source_ip: str | None = None
    user_agent: str | None = None


_LOCK_HEAD = text("SELECT last_hash FROM audit.chain_head FOR UPDATE")
# Reservado antes do INSERT: com a ponta travada, a ordem dos seq segue a da cadeia.
_NEXT_SEQ = text("SELECT nextval('audit.audit_event_seq_seq')")
_INSERT_EVENT = text(
    "INSERT INTO audit.audit_event ("
    " seq, occurred_at, recorded_at, organization_id, actor_user_id, actor_kind, event_type,"
    " target_type, target_id, result, details, source, source_event_id, installation_scope,"
    " prev_hash, hash"
    ") VALUES ("
    " :seq, :occurred_at, :recorded_at, :organization_id, :actor_user_id, :actor_kind, :event_type,"
    " :target_type, :target_id, :result, CAST(:details AS jsonb), :source, :source_event_id,"
    " :installation_scope, :prev_hash, :hash"
    ")"
)
_INSERT_ORIGIN = text(
    "INSERT INTO audit.audit_event_origin (seq, source_ip, user_agent)"
    " VALUES (:seq, CAST(:source_ip AS inet), :user_agent)"
)
_MOVE_HEAD = text("UPDATE audit.chain_head SET last_seq = :seq, last_hash = :hash")


def append_event(session: Session, event: AuditEvent, origin: Origin | None = None) -> int:
    """Grava o evento encadeado e devolve o `seq` atribuído."""
    prev_hash = bytes(session.execute(_LOCK_HEAD).scalar_one())
    current_hash = link_hash(prev_hash, event)
    seq = int(session.execute(_NEXT_SEQ).scalar_one())
    session.execute(
        _INSERT_EVENT,
        {
            "seq": seq,
            "occurred_at": event.occurred_at,
            "recorded_at": event.recorded_at,
            "organization_id": event.organization_id,
            "actor_user_id": event.actor_user_id,
            "actor_kind": event.actor_kind,
            "event_type": event.event_type,
            "target_type": event.target_type,
            "target_id": event.target_id,
            "result": event.result,
            "details": json.dumps(event.details, ensure_ascii=False),
            "source": event.source,
            "source_event_id": event.source_event_id,
            "installation_scope": event.installation_scope,
            "prev_hash": prev_hash,
            "hash": current_hash,
        },
    )
    if origin and (origin.source_ip or origin.user_agent):
        session.execute(
            _INSERT_ORIGIN,
            {"seq": seq, "source_ip": origin.source_ip, "user_agent": origin.user_agent},
        )
    session.execute(_MOVE_HEAD, {"seq": seq, "hash": current_hash})
    return seq
