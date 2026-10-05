"""Expurgo de IP e navegador antigos (T067; RNF-002; data-model.md, audit_event_origin)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import Engine, text

from cap_control_plane.audit.chain import AuditEvent
from cap_control_plane.audit.purge import purge_origins
from cap_control_plane.audit.verify import verify_chain
from cap_control_plane.audit.writer import Origin, append_event
from cap_control_plane.core.db import DbContext, transaction
from cap_control_plane.services import Services


def _event_at(engine: Engine, moment: datetime) -> int:
    with transaction(engine, DbContext.system()) as s:
        return append_event(
            s,
            AuditEvent(
                occurred_at=moment, recorded_at=moment, organization_id=None,
                actor_user_id=uuid.uuid4(), actor_kind="user", event_type="auth.login",
                target_type="user", target_id=str(uuid.uuid4()), result="success",
            ),
            Origin(source_ip="198.51.100.4", user_agent="pytest"),
        )  # fmt: skip


def _has_origin(engine: Engine, seq: int) -> bool:
    with transaction(engine, DbContext.system()) as s:
        return bool(
            s.execute(
                text("SELECT count(*) FROM audit.audit_event_origin WHERE seq = :s"), {"s": seq}
            ).scalar_one()
        )


def test_expurgo_remove_so_a_origem_antiga_e_mantem_a_cadeia(
    services: Services, engine: Engine
) -> None:
    now = datetime.now(UTC)
    old = _event_at(engine, now - timedelta(days=400))
    recent = _event_at(engine, now - timedelta(days=10))

    removed = purge_origins(services, retention_days=365)

    assert removed >= 1
    assert not _has_origin(engine, old)
    assert _has_origin(engine, recent)
    with transaction(engine, DbContext.system()) as s:
        event = s.execute(
            text(
                "SELECT actor_kind, details, installation_scope FROM audit.audit_event"
                " WHERE event_type = 'audit.origin_purged' ORDER BY seq DESC LIMIT 1"
            )
        ).one()
        broken = verify_chain(s)
        still_there = s.execute(
            text("SELECT count(*) FROM audit.audit_event WHERE seq = :s"), {"s": old}
        ).scalar_one()
    assert event.actor_kind == "system"
    assert event.details["rows"] == removed
    assert event.installation_scope is True
    assert still_there == 1
    assert broken is None


def test_sem_nada_antigo_nao_grava_evento(services: Services, engine: Engine) -> None:
    purge_origins(services, retention_days=365)
    with transaction(engine, DbContext.system()) as s:
        before = s.execute(
            text("SELECT count(*) FROM audit.audit_event WHERE event_type = 'audit.origin_purged'")
        ).scalar_one()

    assert purge_origins(services, retention_days=365) == 0

    with transaction(engine, DbContext.system()) as s:
        after = s.execute(
            text("SELECT count(*) FROM audit.audit_event WHERE event_type = 'audit.origin_purged'")
        ).scalar_one()
    assert after == before
