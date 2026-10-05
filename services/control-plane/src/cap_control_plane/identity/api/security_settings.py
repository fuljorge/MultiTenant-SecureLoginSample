"""Configuração de segurança da instalação (T053; RF-007, RF-010)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from cap_control_plane.core.db import transaction
from cap_control_plane.identity.authz import Principal, origin_of, require, require_recent
from cap_control_plane.identity.permissions import Permission
from cap_control_plane.identity.service.common import record
from cap_control_plane.identity.service.security_settings import SecuritySettings
from cap_control_plane.services import Services, get_services

router = APIRouter(prefix="/security-settings", tags=["security"])

ServicesDep = Annotated[Services, Depends(get_services)]
CanManage = Annotated[Principal, Depends(require(Permission.SECURITY_MANAGE))]
# Alterar a segurança é ação sensível (RF-031).
CanChange = Annotated[Principal, Depends(require_recent(Permission.SECURITY_MANAGE))]


@router.get("", response_model=SecuritySettings, summary="Configuração de segurança vigente")
def read_security_settings(services: ServicesDep, _: CanManage) -> SecuritySettings:
    return services.security.read()


@router.put("", response_model=SecuritySettings, summary="Altera a configuração de segurança")
def update_security_settings(
    body: SecuritySettings, request: Request, services: ServicesDep, principal: CanChange
) -> SecuritySettings:
    # Os limites mínimos são validados pelo modelo (resposta 422 se afrouxados).
    changed = services.security.update(body)
    if changed:
        with transaction(services.engine, principal.db_context()) as s:
            record(
                s, principal, origin_of(request),
                event_type="security.settings_changed", target_type="installation",
                target_id="security-settings", organization_id=None,
                details={"fields": sorted(changed)},
            )  # fmt: skip
    return body
