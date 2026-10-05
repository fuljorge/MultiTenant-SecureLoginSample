"""Cadeia de hash do Audit Trail (T021; §39, Princípio VII)."""

import uuid
from dataclasses import replace
from datetime import UTC, datetime

import pytest

from cap_control_plane.audit.chain import (
    GENESIS_HASH,
    AuditEvent,
    ChainLink,
    canonical_bytes,
    first_broken_link,
    link_hash,
)


def _event(**changes: object) -> AuditEvent:
    base = AuditEvent(
        occurred_at=datetime(2026, 10, 2, 12, 0, 0, 123456, tzinfo=UTC),
        recorded_at=datetime(2026, 10, 2, 12, 0, 1, tzinfo=UTC),
        organization_id=uuid.UUID("00000000-0000-0000-0000-00000000000a"),
        actor_user_id=uuid.UUID("00000000-0000-0000-0000-00000000000b"),
        actor_kind="user",
        event_type="user.invited",
        target_type="user",
        target_id="u-1",
        result="success",
        details={"profile": "supervisor", "organization_id": "org-1"},
        source="control_plane",
        source_event_id=None,
    )
    return replace(base, **changes)  # type: ignore[arg-type]


def _chain(events: list[AuditEvent]) -> list[ChainLink]:
    links, prev = [], GENESIS_HASH
    for event in events:
        current = link_hash(prev, event)
        links.append(ChainLink(event=event, prev_hash=prev, hash=current))
        prev = current
    return links


def test_json_canonico_independe_da_ordem_das_chaves() -> None:
    a = _event(details={"a": 1, "b": 2})
    b = _event(details={"b": 2, "a": 1})

    assert canonical_bytes(a) == canonical_bytes(b)


def test_hash_depende_do_anterior_e_do_conteudo() -> None:
    event = _event()

    assert link_hash(GENESIS_HASH, event) != link_hash(b"\x01" * 32, event)
    assert link_hash(GENESIS_HASH, event) != link_hash(GENESIS_HASH, _event(result="failure"))
    assert len(link_hash(GENESIS_HASH, event)) == 32


def test_cadeia_integra_nao_tem_elo_quebrado() -> None:
    links = _chain([_event(target_id=str(i)) for i in range(5)])

    assert first_broken_link(links) is None


def test_alteracao_de_conteudo_e_detectada() -> None:
    links = _chain([_event(target_id=str(i)) for i in range(5)])
    links[2] = replace(links[2], event=replace(links[2].event, result="denied"))

    assert first_broken_link(links) == 2


def test_remocao_de_registro_e_detectada() -> None:
    links = _chain([_event(target_id=str(i)) for i in range(5)])
    del links[1]

    assert first_broken_link(links) == 1


@pytest.mark.parametrize(
    "details",
    [
        {"password": "x"},
        {"email": "ana@empresa.com.br"},
        {"source_ip": "203.0.113.1"},
        {"link": "https://cap.exemplo/convite/abc"},
        {"reason": "falha de ana@empresa.com.br"},
    ],
)
def test_detalhes_com_dado_sensivel_sao_recusados(details: dict[str, str]) -> None:
    with pytest.raises(ValueError, match="sensível"):
        _event(details=details)
