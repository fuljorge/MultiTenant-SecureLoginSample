"""Consulta e exportação do Audit Trail (T068; US6; RF-022, RF-023; contracts/identity-api.md).

O escopo vem do RLS do contexto de quem consulta: o Administrador vê a organização ativa e
os eventos de identidade das pessoas dela; o Super Administrador, a gestão da instalação
(migrações 0002, 0004 e 0005). Nenhum filtro aqui amplia esse escopo.
"""

from __future__ import annotations

import csv
import io
import uuid
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import text

from cap_control_plane.core.db import transaction
from cap_control_plane.identity.authz import Principal, origin_of, require_any, require_recent
from cap_control_plane.identity.permissions import Permission
from cap_control_plane.identity.service.common import record
from cap_control_plane.services import Services, get_services

router = APIRouter(prefix="/audit-events", tags=["audit"])

ServicesDep = Annotated[Services, Depends(get_services)]
CanRead = Annotated[
    Principal, Depends(require_any(Permission.AUDIT_READ, Permission.AUDIT_READ_INSTALLATION))
]
# Exportar é ação sensível (RF-031).
CanExport = Annotated[
    Principal,
    Depends(require_recent(Permission.AUDIT_READ, Permission.AUDIT_READ_INSTALLATION)),
]

Result = Literal["success", "failure", "denied"]
EXPORT_LIMIT = 10_000


class AuditFilter(BaseModel):
    """Filtros da consulta (US6, cenário 1). Todos opcionais."""

    q: str | None = Field(default=None, max_length=200, description="Nome ou e-mail da pessoa")
    user_id: uuid.UUID | None = None
    event_type: str | None = Field(default=None, max_length=100)
    result: Result | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None


class AuditEventOut(BaseModel):
    seq: int
    occurred_at: datetime
    event_type: str
    result: str
    actor_kind: str
    actor_user_id: uuid.UUID | None
    actor_name: str | None
    target_type: str | None
    target_id: str | None
    target_name: str | None
    organization_id: uuid.UUID | None
    installation_scope: bool
    details: dict[str, Any]
    source: str
    source_ip: str | None
    user_agent: str | None


# Nomes das pessoas também passam pelo RLS: quem não é visível aparece sem nome.
_QUERY = """
SELECT e.seq, e.occurred_at, e.event_type, e.result::text AS result,
       e.actor_kind::text AS actor_kind, e.actor_user_id, a.name AS actor_name,
       e.target_type, e.target_id, t.name AS target_name, e.organization_id,
       e.installation_scope, e.details, e.source::text AS source,
       host(o.source_ip) AS source_ip, o.user_agent
FROM audit.audit_event e
LEFT JOIN identity.user_account a ON a.id = e.actor_user_id
LEFT JOIN identity.user_account t ON e.target_type = 'user' AND t.id::text = e.target_id
LEFT JOIN audit.audit_event_origin o ON o.seq = e.seq
WHERE (CAST(:user_id AS uuid) IS NULL OR e.actor_user_id = :user_id
       OR (e.target_type = 'user' AND e.target_id = CAST(:user_id AS text)))
  AND (CAST(:q AS text) IS NULL OR a.name ILIKE :q OR a.email ILIKE :q
       OR t.name ILIKE :q OR t.email ILIKE :q)
  AND (CAST(:event_type AS text) IS NULL OR e.event_type = :event_type)
  AND (CAST(:result AS text) IS NULL OR e.result::text = :result)
  AND (CAST(:date_from AS timestamptz) IS NULL OR e.occurred_at >= :date_from)
  AND (CAST(:date_to AS timestamptz) IS NULL OR e.occurred_at < :date_to)
ORDER BY e.seq DESC
LIMIT :limit OFFSET :offset
"""


def _search(
    services: Services, principal: Principal, filters: AuditFilter, limit: int, offset: int
) -> list[AuditEventOut]:
    params = filters.model_dump()
    params["q"] = f"%{filters.q.strip()}%" if filters.q and filters.q.strip() else None
    with transaction(services.engine, principal.db_context()) as s:
        rows = s.execute(text(_QUERY), {**params, "limit": limit, "offset": offset}).mappings()
        return [AuditEventOut.model_validate(dict(r)) for r in rows]


@router.get("", response_model=list[AuditEventOut], summary="Consulta o Audit Trail")
def list_audit_events(
    services: ServicesDep,
    principal: CanRead,
    q: Annotated[str | None, Query(max_length=200)] = None,
    user_id: uuid.UUID | None = None,
    event_type: Annotated[str | None, Query(max_length=100)] = None,
    result: Result | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[AuditEventOut]:
    filters = AuditFilter(
        q=q, user_id=user_id, event_type=event_type, result=result,
        date_from=date_from, date_to=date_to,
    )  # fmt: skip
    return _search(services, principal, filters, limit, offset)


_COLUMNS = [
    "seq", "occurred_at", "event_type", "result", "actor_kind", "actor_user_id", "actor_name",
    "target_type", "target_id", "target_name", "organization_id", "source_ip", "user_agent",
    "details",
]  # fmt: skip


def csv_cell(value: object) -> str:
    """Texto seguro para planilhas: neutraliza fórmulas (injeção de CSV)."""
    if value is None:
        return ""
    if isinstance(value, datetime):
        value = value.astimezone(UTC).isoformat()
    cell = str(value)
    if cell[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + cell
    return cell


@router.post(
    "/export",
    response_class=Response,
    responses={200: {"content": {"text/csv": {}}}},
    summary="Exporta o filtro em CSV (registra audit.exported)",
)
def export_audit_events(
    filters: AuditFilter, request: Request, services: ServicesDep, principal: CanExport
) -> Response:
    events = _search(services, principal, filters, EXPORT_LIMIT, 0)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(_COLUMNS)
    for event in events:
        data = event.model_dump()
        writer.writerow([csv_cell(data[c]) for c in _COLUMNS])
    used = {k: str(v) for k, v in filters.model_dump(exclude_none=True).items()}
    if "q" in used:
        # O texto buscado pode ser nome ou e-mail: o Audit Trail não guarda dado pessoal.
        used["q"] = "informado"
    with transaction(services.engine, principal.db_context()) as s:
        record(
            s, principal, origin_of(request),
            event_type="audit.exported", target_type="audit_event", target_id="export",
            details={"filters": used, "rows": len(events)},
        )  # fmt: skip
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="auditoria-{stamp}.csv"'},
    )
