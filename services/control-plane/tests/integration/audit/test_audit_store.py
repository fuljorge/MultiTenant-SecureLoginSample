"""Gravação append-only do Audit Trail (T022; §39, Princípio VII, US6 cenário 3)."""

from __future__ import annotations

import threading
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import DBAPIError

from cap_control_plane.audit.chain import AuditEvent
from cap_control_plane.audit.verify import verify_chain
from cap_control_plane.audit.writer import Origin, append_event
from cap_control_plane.core.db import DbContext, transaction
from tests.support.database import MigratedDatabase


def _event(org: uuid.UUID | None = None, target: str = "t") -> AuditEvent:
    now = datetime.now(UTC)
    return AuditEvent(
        occurred_at=now,
        recorded_at=now,
        organization_id=org,
        actor_user_id=uuid.uuid4(),
        actor_kind="user",
        event_type="user.invited",
        target_type="user",
        target_id=target,
        result="success",
        details={"profile": "supervisor"},
    )


def test_grava_evento_e_origem(engine: Engine) -> None:
    with transaction(engine, DbContext(user_id=uuid.uuid4())) as s:
        seq = append_event(s, _event(), Origin(source_ip="203.0.113.9", user_agent="pytest"))

    with transaction(engine, DbContext.system()) as s:
        row = s.execute(
            text(
                "SELECT e.event_type, host(o.source_ip) FROM audit.audit_event e "
                "JOIN audit.audit_event_origin o USING (seq) WHERE e.seq = :seq"
            ),
            {"seq": seq},
        ).one()

    assert tuple(row) == ("user.invited", "203.0.113.9")


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE audit.audit_event SET result = 'denied'",
        "DELETE FROM audit.audit_event",
        "TRUNCATE audit.audit_event CASCADE",
    ],
)
def test_aplicacao_nao_altera_nem_apaga_eventos(engine: Engine, statement: str) -> None:
    with transaction(engine, DbContext.system()) as s:
        append_event(s, _event())

    with pytest.raises(DBAPIError), transaction(engine, DbContext.system()) as s:
        s.execute(text(statement))


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE audit.audit_event SET result = 'denied'",
        "DELETE FROM audit.audit_event",
        "TRUNCATE audit.audit_event CASCADE",
    ],
)
def test_nem_o_dono_do_schema_altera_eventos(
    engine: Engine, database: MigratedDatabase, statement: str
) -> None:
    with transaction(engine, DbContext.system()) as s:
        append_event(s, _event())
    owner = create_engine(database.migrator_url)
    try:
        with pytest.raises(DBAPIError, match="append-only"), owner.begin() as conn:
            conn.execute(text("SELECT set_config('app.is_system', 'true', true)"))
            conn.execute(text(statement))
    finally:
        owner.dispose()


def test_gravacoes_simultaneas_mantem_a_cadeia_integra(engine: Engine) -> None:
    errors: list[BaseException] = []

    def write(n: int) -> None:
        try:
            for i in range(5):
                with transaction(engine, DbContext(user_id=uuid.uuid4())) as s:
                    append_event(s, _event(target=f"{n}-{i}"))
        except BaseException as exc:
            errors.append(exc)

    threads = [threading.Thread(target=write, args=(n,)) for n in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    with transaction(engine, DbContext.system()) as s:
        assert verify_chain(s) is None


def test_eventos_de_outra_organizacao_nao_sao_visiveis(engine: Engine) -> None:
    org_a, org_b = uuid.uuid4(), uuid.uuid4()
    with transaction(engine, DbContext.system()) as s:
        append_event(s, _event(org=org_a, target="a"))
        append_event(s, _event(org=org_b, target="b"))

    with transaction(engine, DbContext(user_id=uuid.uuid4(), organization_id=org_a)) as s:
        orgs = {
            r[0] for r in s.execute(text("SELECT DISTINCT organization_id FROM audit.audit_event"))
        }

    assert orgs == {org_a}
