"""Encadeamento por hash dos eventos de auditoria (T024; §39, Princípio VII).

Cada registro guarda o hash do anterior e o próprio:
`hash = SHA-256(hash_anterior ‖ JSON canônico do evento)`. Alterar ou remover um
registro quebra todos os elos seguintes. IP e navegador ficam fora da cadeia
(`audit_event_origin`), porque têm prazo de retenção (LGPD; data-model.md).
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

from cap_control_plane.core.logging import is_sensitive_key, redact_text

GENESIS_HASH = b"\x00" * 32

ActorKind = Literal["user", "system", "support"]
Result = Literal["success", "failure", "denied"]
Source = Literal["control_plane", "keycloak"]


def _check_details(details: dict[str, Any]) -> None:
    """`details` nunca leva senha, código, token, link, e-mail ou IP (contracts/audit-events.md)."""
    for key, value in details.items():
        if is_sensitive_key(key):
            raise ValueError(f"Campo sensível em details: {key}")
        if isinstance(value, str) and redact_text(value) != value:
            raise ValueError(f"Valor sensível em details: {key}")
        if isinstance(value, dict):
            _check_details(value)


@dataclass(frozen=True)
class AuditEvent:
    occurred_at: datetime
    recorded_at: datetime
    organization_id: uuid.UUID | None
    actor_user_id: uuid.UUID | None
    actor_kind: ActorKind
    event_type: str
    target_type: str | None
    target_id: str | None
    result: Result
    details: dict[str, Any] = field(default_factory=dict)
    source: Source = "control_plane"
    source_event_id: str | None = None
    # Gestão da instalação (ações do Super Administrador), visível a ele (US6, cenário 2).
    installation_scope: bool = False

    def __post_init__(self) -> None:
        _check_details(self.details)

    @classmethod
    def now(cls, **fields: Any) -> AuditEvent:
        """Evento ocorrido e registrado agora (eventos gerados pelo próprio Control Plane)."""
        moment = datetime.now(UTC)
        return cls(occurred_at=moment, recorded_at=moment, **fields)


@dataclass(frozen=True)
class ChainLink:
    event: AuditEvent
    prev_hash: bytes
    hash: bytes


def canonical_bytes(event: AuditEvent) -> bytes:
    payload: dict[str, Any] = {
        "occurred_at": event.occurred_at.isoformat(),
        "recorded_at": event.recorded_at.isoformat(),
        "organization_id": str(event.organization_id) if event.organization_id else None,
        "actor_user_id": str(event.actor_user_id) if event.actor_user_id else None,
        "actor_kind": event.actor_kind,
        "event_type": event.event_type,
        "target_type": event.target_type,
        "target_id": event.target_id,
        "result": event.result,
        "details": event.details,
        "source": event.source,
        "source_event_id": event.source_event_id,
    }
    # Só entra no hash quando verdadeiro: os eventos anteriores à revisão de 2026-10-03
    # continuam com o mesmo hash.
    if event.installation_scope:
        payload["installation_scope"] = True
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def link_hash(prev_hash: bytes, event: AuditEvent) -> bytes:
    return hashlib.sha256(prev_hash + canonical_bytes(event)).digest()


def first_broken_link(links: Sequence[ChainLink]) -> int | None:
    """Índice do primeiro elo inválido, ou None se a cadeia estiver íntegra."""
    expected_prev = GENESIS_HASH
    for index, link in enumerate(links):
        if link.prev_hash != expected_prev or link.hash != link_hash(link.prev_hash, link.event):
            return index
        expected_prev = link.hash
    return None
