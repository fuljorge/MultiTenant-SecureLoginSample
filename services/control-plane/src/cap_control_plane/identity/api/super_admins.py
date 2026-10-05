"""Rotas de Super Administradores (T092; US5; RF-030; contracts/identity-api.md)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, EmailStr, Field

from cap_control_plane.identity.authz import Principal, origin_of, require, require_recent
from cap_control_plane.identity.permissions import Permission
from cap_control_plane.identity.service import super_admins
from cap_control_plane.services import Services, get_services

router = APIRouter(prefix="/super-admins", tags=["super-admins"])

ServicesDep = Annotated[Services, Depends(get_services)]
CanManage = Annotated[Principal, Depends(require(Permission.SUPER_ADMINS_MANAGE))]
# Ações sensíveis (RF-031): permissão e login completo recente.
CanManageRecent = Annotated[Principal, Depends(require_recent(Permission.SUPER_ADMINS_MANAGE))]


class SuperAdminOut(BaseModel):
    id: uuid.UUID
    name: str
    email: str
    status: str
    last_login_at: datetime | None


class SuperAdminInviteIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    email: EmailStr


class SuperAdminCreatedOut(BaseModel):
    id: uuid.UUID


@router.get("", response_model=list[SuperAdminOut], summary="Lista os Super Administradores")
def list_super_admins(services: ServicesDep, principal: CanManage) -> list[SuperAdminOut]:
    return [
        SuperAdminOut.model_validate(vars(v))
        for v in super_admins.list_super_admins(services, principal)
    ]


@router.post(
    "",
    response_model=SuperAdminCreatedOut,
    status_code=status.HTTP_201_CREATED,
    summary="Convida um Super Administrador",
)
async def invite_super_admin(
    body: SuperAdminInviteIn, request: Request, services: ServicesDep, principal: CanManageRecent
) -> SuperAdminCreatedOut:
    user_id = await run_in_threadpool(
        super_admins.invite_super_admin, services, principal, origin_of(request),
        email=str(body.email), name=body.name,
    )  # fmt: skip
    return SuperAdminCreatedOut(id=user_id)


@router.post("/{user_id}/disable", status_code=status.HTTP_204_NO_CONTENT, summary="Desativa")
async def disable_super_admin(
    user_id: uuid.UUID, request: Request, services: ServicesDep, principal: CanManageRecent
) -> Response:
    await run_in_threadpool(
        super_admins.disable_super_admin, services, principal, origin_of(request),
        user_id=user_id,
    )  # fmt: skip
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{user_id}/enable", status_code=status.HTTP_204_NO_CONTENT, summary="Reativa")
async def enable_super_admin(
    user_id: uuid.UUID, request: Request, services: ServicesDep, principal: CanManageRecent
) -> Response:
    await run_in_threadpool(
        super_admins.enable_super_admin, services, principal, origin_of(request),
        user_id=user_id,
    )  # fmt: skip
    return Response(status_code=status.HTTP_204_NO_CONTENT)
