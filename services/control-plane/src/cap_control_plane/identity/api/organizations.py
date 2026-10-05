"""Rotas de organizações e dos seus Administradores (T063; US5; contracts/identity-api.md).

Todas exigem permissões de instalação, que só o Super Administrador tem (RF-016, RF-028).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, Request, Response, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, EmailStr, Field

from cap_control_plane.identity.api.users import if_match_version
from cap_control_plane.identity.authz import Principal, origin_of, require, require_recent
from cap_control_plane.identity.permissions import Permission
from cap_control_plane.identity.service import organizations
from cap_control_plane.services import Services, get_services

router = APIRouter(prefix="/organizations", tags=["organizations"])

ServicesDep = Annotated[Services, Depends(get_services)]
CanManage = Annotated[Principal, Depends(require(Permission.ORGANIZATIONS_MANAGE))]
# Ações sensíveis (RF-031): permissão e login completo recente.
CanManageRecent = Annotated[Principal, Depends(require_recent(Permission.ORGANIZATIONS_MANAGE))]
CanManageAdmins = Annotated[
    Principal, Depends(require_recent(Permission.ORGANIZATION_ADMINS_MANAGE))
]

OrganizationStatus = Literal["pending", "active", "suspended", "cancelled"]


class AdministratorOut(BaseModel):
    id: uuid.UUID
    name: str
    email: str
    status: str


class OrganizationOut(BaseModel):
    id: uuid.UUID
    name: str
    status: OrganizationStatus
    created_at: datetime
    version: int
    administrators: list[AdministratorOut]


class OrganizationInviteIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    admin_name: str = Field(min_length=1, max_length=200)
    admin_email: EmailStr


class OrganizationRenameIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class AdministratorInviteIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    email: EmailStr


class CreatedOut(BaseModel):
    id: uuid.UUID


class SuspendedOut(BaseModel):
    sessions_ended: int


def _out(view: organizations.OrganizationView) -> OrganizationOut:
    return OrganizationOut.model_validate(
        {**vars(view), "administrators": [vars(a) for a in view.administrators]}
    )


@router.get("", response_model=list[OrganizationOut], summary="Lista as organizações")
def list_organizations(
    services: ServicesDep,
    principal: CanManage,
    q: str | None = None,
    org_status: OrganizationStatus | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[OrganizationOut]:
    views = organizations.list_organizations(
        services, principal, query=q, status=org_status, limit=limit, offset=offset
    )
    return [_out(v) for v in views]


@router.get("/{organization_id}", response_model=OrganizationOut, summary="Detalhe")
def get_organization(
    organization_id: uuid.UUID, services: ServicesDep, principal: CanManage
) -> OrganizationOut:
    return _out(organizations.get_organization(services, principal, organization_id))


@router.post(
    "",
    response_model=CreatedOut,
    status_code=status.HTTP_201_CREATED,
    summary="Convida uma nova organização e o seu Administrador",
)
async def invite_organization(
    body: OrganizationInviteIn, request: Request, services: ServicesDep, principal: CanManageRecent
) -> CreatedOut:
    organization_id = await run_in_threadpool(
        organizations.invite_organization, services, principal, origin_of(request),
        name=body.name, admin_name=body.admin_name, admin_email=str(body.admin_email),
    )  # fmt: skip
    return CreatedOut(id=organization_id)


@router.patch("/{organization_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Renomeia")
def rename_organization(
    organization_id: uuid.UUID,
    body: OrganizationRenameIn,
    request: Request,
    services: ServicesDep,
    principal: CanManage,
    if_match: Annotated[str | None, Header()] = None,
) -> Response:
    organizations.rename_organization(
        services, principal, origin_of(request), organization_id=organization_id,
        name=body.name, expected_version=if_match_version(if_match),
    )  # fmt: skip
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{organization_id}/suspend",
    response_model=SuspendedOut,
    summary="Suspende: encerra as sessões e bloqueia o acesso",
)
async def suspend_organization(
    organization_id: uuid.UUID, request: Request, services: ServicesDep, principal: CanManageRecent
) -> SuspendedOut:
    count = await run_in_threadpool(
        organizations.suspend_organization, services, principal, origin_of(request),
        organization_id=organization_id,
    )  # fmt: skip
    return SuspendedOut(sessions_ended=count)


@router.post(
    "/{organization_id}/reactivate", status_code=status.HTTP_204_NO_CONTENT, summary="Reativa"
)
def reactivate_organization(
    organization_id: uuid.UUID, request: Request, services: ServicesDep, principal: CanManageRecent
) -> Response:
    organizations.reactivate_organization(
        services, principal, origin_of(request), organization_id=organization_id
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{organization_id}/invitation/resend",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Reenvia o convite da organização pendente",
)
async def resend_invitation(
    organization_id: uuid.UUID, request: Request, services: ServicesDep, principal: CanManage
) -> Response:
    await run_in_threadpool(
        organizations.resend_invitation, services, principal, origin_of(request),
        organization_id=organization_id,
    )  # fmt: skip
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{organization_id}/cancel",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Cancela uma organização pendente",
)
async def cancel_organization(
    organization_id: uuid.UUID, request: Request, services: ServicesDep, principal: CanManageRecent
) -> Response:
    await run_in_threadpool(
        organizations.cancel_organization, services, principal, origin_of(request),
        organization_id=organization_id,
    )  # fmt: skip
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{organization_id}/administrators",
    response_model=CreatedOut,
    status_code=status.HTTP_201_CREATED,
    summary="Convida mais um Administrador",
)
async def invite_administrator(
    organization_id: uuid.UUID,
    body: AdministratorInviteIn,
    request: Request,
    services: ServicesDep,
    principal: CanManageAdmins,
) -> CreatedOut:
    invitation_id = await run_in_threadpool(
        organizations.invite_administrator, services, principal, origin_of(request),
        organization_id=organization_id, name=body.name, email=str(body.email),
    )  # fmt: skip
    return CreatedOut(id=invitation_id)


@router.post(
    "/{organization_id}/administrators/{user_id}/disable",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Desativa um Administrador",
)
async def disable_administrator(
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    request: Request,
    services: ServicesDep,
    principal: CanManageAdmins,
) -> Response:
    await run_in_threadpool(
        organizations.disable_administrator, services, principal, origin_of(request),
        organization_id=organization_id, user_id=user_id,
    )  # fmt: skip
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{organization_id}/administrators/{user_id}/enable",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Reativa um Administrador",
)
async def enable_administrator(
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    request: Request,
    services: ServicesDep,
    principal: CanManageAdmins,
) -> Response:
    await run_in_threadpool(
        organizations.enable_administrator, services, principal, origin_of(request),
        organization_id=organization_id, user_id=user_id,
    )  # fmt: skip
    return Response(status_code=status.HTTP_204_NO_CONTENT)
