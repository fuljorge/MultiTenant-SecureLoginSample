"""Rotas de usuários, convites e troca de e-mail (T052; contracts/identity-api.md)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request, Response, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, EmailStr, Field

from cap_control_plane.identity.authz import Principal, origin_of, require, require_recent
from cap_control_plane.identity.permissions import Permission, Profile
from cap_control_plane.identity.service import email_change, invitations, users
from cap_control_plane.identity.session_auth import require_session
from cap_control_plane.services import Services, get_services

router = APIRouter(tags=["users"])

ServicesDep = Annotated[Services, Depends(get_services)]
CanRead = Annotated[Principal, Depends(require(Permission.USERS_READ))]
CanManage = Annotated[Principal, Depends(require(Permission.USERS_MANAGE))]
# Ações sensíveis (RF-031): permissão e login completo recente.
CanManageRecent = Annotated[Principal, Depends(require_recent(Permission.USERS_MANAGE))]
SessionOnly = Annotated[Principal, Depends(require_session)]


class MembershipOut(BaseModel):
    organization_id: uuid.UUID
    organization_name: str
    profile: str
    status: str
    version: int


class UserOut(BaseModel):
    id: uuid.UUID
    name: str
    email: str
    status: str
    last_login_at: datetime | None
    version: int
    memberships: list[MembershipOut]


class UserDetailOut(UserOut):
    blocked: bool


class InvitationIn(BaseModel):
    email: EmailStr
    name: str = Field(min_length=1, max_length=200)
    organization_id: uuid.UUID
    profile: Profile


class InvitationOut(BaseModel):
    id: uuid.UUID
    email: str
    profile: str
    status: str
    expires_at: datetime
    existing_person: bool


class InvitationCreatedOut(BaseModel):
    id: uuid.UUID


class AcceptedOut(BaseModel):
    organization_id: uuid.UUID


class ProfileIn(BaseModel):
    profile: Profile


class EmailChangeIn(BaseModel):
    new_email: EmailStr


class RevokedOut(BaseModel):
    sessions_ended: int


def _user_out(view: users.UserView) -> dict[str, object]:
    return {
        **{k: getattr(view, k) for k in UserOut.model_fields if k != "memberships"},
        "memberships": [MembershipOut(**vars(m)) for m in view.memberships],
    }


def if_match_version(if_match: str | None) -> int | None:
    """Versão esperada (If-Match); aspas e prefixo W/ são ignorados."""
    if not if_match:
        return None
    value = if_match.removeprefix("W/").strip('"')
    return int(value) if value.isdigit() else None


@router.get("/users", response_model=list[UserOut], summary="Lista usuários com filtros")
def list_users(
    services: ServicesDep,
    principal: CanRead,
    q: str | None = None,
    profile: Profile | None = None,
    user_status: Annotated[str | None, Field(pattern="^(invited|active|disabled)$")] = None,
    limit: int = 50,
    offset: int = 0,
) -> list[UserOut]:
    views = users.list_users(
        services,
        principal,
        query=q,
        profile=profile.value if profile else None,
        status=user_status,
        limit=limit,
        offset=offset,
    )
    return [UserOut.model_validate(_user_out(v)) for v in views]


@router.get("/users/{user_id}", response_model=UserDetailOut, summary="Detalhe do usuário")
def get_user(
    user_id: uuid.UUID, request: Request, services: ServicesDep, principal: CanRead
) -> UserDetailOut:
    view = users.get_user(services, principal, user_id, origin_of(request))
    return UserDetailOut.model_validate(
        {**_user_out(view), "blocked": users.is_blocked(services, user_id)}
    )


@router.patch(
    "/users/{user_id}/memberships/{organization_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Altera o perfil na organização",
)
def change_profile(
    user_id: uuid.UUID,
    organization_id: uuid.UUID,
    body: ProfileIn,
    request: Request,
    services: ServicesDep,
    principal: CanManage,
    if_match: Annotated[str | None, Header()] = None,
) -> Response:
    users.change_profile(
        services, principal, origin_of(request),
        user_id=user_id, organization_id=organization_id, profile=body.profile,
        expected_version=if_match_version(if_match),
    )  # fmt: skip
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/users/{user_id}/memberships/{organization_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a pessoa da organização",
)
def remove_membership(
    user_id: uuid.UUID,
    organization_id: uuid.UUID,
    request: Request,
    services: ServicesDep,
    principal: CanManageRecent,
) -> Response:
    users.remove_membership(
        services, principal, origin_of(request), user_id=user_id, organization_id=organization_id
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/users/{user_id}/disable", status_code=status.HTTP_204_NO_CONTENT, summary="Desativa")
async def disable_user(
    user_id: uuid.UUID, request: Request, services: ServicesDep, principal: CanManageRecent
) -> Response:
    await run_in_threadpool(
        users.disable_user, services, principal, origin_of(request), user_id=user_id
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/users/{user_id}/enable", status_code=status.HTTP_204_NO_CONTENT, summary="Reativa")
async def enable_user(
    user_id: uuid.UUID, request: Request, services: ServicesDep, principal: CanManageRecent
) -> Response:
    await run_in_threadpool(
        users.enable_user, services, principal, origin_of(request), user_id=user_id
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/users/{user_id}/sessions/revoke",
    response_model=RevokedOut,
    summary="Encerra todas as sessões do usuário",
)
def revoke_user_sessions(
    user_id: uuid.UUID, request: Request, services: ServicesDep, principal: CanManageRecent
) -> RevokedOut:
    count = users.revoke_sessions(services, principal, origin_of(request), user_id=user_id)
    return RevokedOut(sessions_ended=count)


@router.post(
    "/users/{user_id}/email-change",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Inicia a troca de e-mail (confirmação pelo novo e-mail)",
)
def request_email_change(
    user_id: uuid.UUID,
    body: EmailChangeIn,
    request: Request,
    services: ServicesDep,
    principal: CanManageRecent,
) -> Response:
    email_change.request_email_change(
        services, principal, origin_of(request), user_id=user_id, new_email=str(body.new_email)
    )
    return Response(status_code=status.HTTP_202_ACCEPTED)


@router.post(
    "/email-change/{token}/confirm",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Confirma a troca de e-mail (link enviado ao novo e-mail)",
)
def confirm_email_change(token: str, request: Request, services: ServicesDep) -> Response:
    email_change.confirm_email_change(services, origin_of(request), token=token)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/invitations",
    response_model=InvitationCreatedOut,
    status_code=status.HTTP_201_CREATED,
    summary="Convida uma pessoa",
)
def create_invitation(
    body: InvitationIn, request: Request, services: ServicesDep, principal: CanManage
) -> InvitationCreatedOut:
    invitation_id = invitations.invite(
        services, principal, origin_of(request),
        email=str(body.email), name=body.name,
        organization_id=body.organization_id, profile=body.profile,
    )  # fmt: skip
    return InvitationCreatedOut(id=invitation_id)


@router.get("/invitations", response_model=list[InvitationOut], summary="Convites pendentes")
def list_invitations(
    services: ServicesDep, principal: CanRead, organization_id: uuid.UUID | None = None
) -> list[InvitationOut]:
    return [
        InvitationOut(**vars(i))
        for i in invitations.list_invitations(services, principal, organization_id)
    ]


@router.delete(
    "/invitations/{invitation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoga um convite pendente",
)
def revoke_invitation(
    invitation_id: uuid.UUID, request: Request, services: ServicesDep, principal: CanManage
) -> Response:
    invitations.revoke_invitation(
        services, principal, origin_of(request), invitation_id=invitation_id
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/invitations/{token}/accept",
    response_model=AcceptedOut,
    summary="Aceita um convite (pessoa já cadastrada, logada)",
)
def accept_invitation(
    token: str, request: Request, services: ServicesDep, principal: SessionOnly
) -> AcceptedOut:
    org = invitations.accept_invitation(services, principal, origin_of(request), token=token)
    return AcceptedOut(organization_id=org)
