"""Rotas da própria pessoa: /me e "Minhas sessões" (T037, T039; RF-006)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel

from cap_control_plane.audit.chain import AuditEvent
from cap_control_plane.audit.writer import append_event
from cap_control_plane.core.db import transaction
from cap_control_plane.identity.api.auth import last_org_key
from cap_control_plane.identity.authz import Principal, origin_of
from cap_control_plane.identity.directory import get_user, organizations_for
from cap_control_plane.identity.session_auth import require_session
from cap_control_plane.services import Services, get_services

router = APIRouter(prefix="/me", tags=["me"])

ServicesDep = Annotated[Services, Depends(get_services)]
PrincipalDep = Annotated[Principal, Depends(require_session)]


class OrganizationOut(BaseModel):
    id: uuid.UUID
    name: str
    profile: str


class MeOut(BaseModel):
    id: uuid.UUID
    name: str
    email: str
    # Membro de organização ou Super Administrador (sem organização ativa; RF-028).
    kind: Literal["member", "super_admin"]
    active_organization_id: uuid.UUID | None
    organizations: list[OrganizationOut]
    permissions: list[str]


class ActiveOrganizationIn(BaseModel):
    organization_id: uuid.UUID


class SessionOut(BaseModel):
    id: str
    created_at: datetime
    last_seen_at: datetime
    user_agent: str | None
    source_ip_partial: str | None
    current: bool


@router.get("", response_model=MeOut, summary="Pessoa logada, organizações e permissões")
def me(services: ServicesDep, principal: PrincipalDep) -> MeOut:
    user = get_user(services.engine, principal.user_id)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED)
    return MeOut(
        id=user.id,
        name=user.name,
        email=user.email,
        kind="super_admin" if user.is_super_admin else "member",
        active_organization_id=principal.organization_id,
        organizations=[
            OrganizationOut(id=o.id, name=o.name, profile=o.profile.value)
            for o in organizations_for(services.engine, user)
        ],
        permissions=sorted(p.value for p in principal.permissions),
    )


@router.put(
    "/active-organization",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Troca a organização ativa sem novo login",
)
def switch_organization(
    body: ActiveOrganizationIn, request: Request, services: ServicesDep, principal: PrincipalDep
) -> Response:
    """RF-019: só para organizações ativas em que a pessoa tem vínculo ativo."""
    user = get_user(services.engine, principal.user_id)
    available = {o.id for o in organizations_for(services.engine, user)} if user else set()
    if body.organization_id not in available:
        # Não revela se a organização existe.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Organização não encontrada")
    session = request.state.session
    previous = session.organization_id
    session.organization_id = body.organization_id
    services.sessions.save(session)
    services.valkey.set(last_org_key(principal.user_id), str(body.organization_id))
    now = datetime.now(UTC)
    with transaction(services.engine, principal.db_context()) as db:
        append_event(
            db,
            AuditEvent(
                occurred_at=now,
                recorded_at=now,
                organization_id=body.organization_id,
                actor_user_id=principal.user_id,
                actor_kind="user",
                event_type="org.switched",
                target_type="organization",
                target_id=str(body.organization_id),
                result="success",
                details={
                    "from": str(previous) if previous else None,
                    "to": str(body.organization_id),
                },
            ),
            origin_of(request),
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/sessions", response_model=list[SessionOut], summary="Minhas sessões ativas")
def my_sessions(
    request: Request, services: ServicesDep, principal: PrincipalDep
) -> list[SessionOut]:
    current = services.sessions.public_id(request.state.session_id)
    return [
        SessionOut(
            id=s.public_id,
            created_at=datetime.fromtimestamp(s.created_at, UTC),
            last_seen_at=datetime.fromtimestamp(s.last_seen_at, UTC),
            user_agent=s.user_agent,
            source_ip_partial=s.source_ip_partial,
            current=s.public_id == current,
        )
        for s in services.sessions.list_for_user(principal.user_id)
    ]


@router.delete(
    "/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Encerra uma das minhas sessões",
)
def end_my_session(
    session_id: str, request: Request, services: ServicesDep, principal: PrincipalDep
) -> Response:
    if not services.sessions.delete_by_public_id(principal.user_id, session_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sessão não encontrada")
    now = datetime.now(UTC)
    with transaction(services.engine, principal.db_context()) as db:
        append_event(
            db,
            AuditEvent(
                occurred_at=now,
                recorded_at=now,
                organization_id=principal.organization_id,
                actor_user_id=principal.user_id,
                actor_kind="user",
                event_type="auth.session_revoked",
                target_type="session",
                target_id=session_id,
                result="success",
                details={"revoked_by": "self"},
            ),
            origin_of(request),
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
