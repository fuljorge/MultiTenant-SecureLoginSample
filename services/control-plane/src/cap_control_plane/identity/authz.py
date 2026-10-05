"""Autorização por rota (T027; RF-014).

Cada rota declara a permissão exigida com `Depends(require(Permission.X))`. A sessão
(middleware do BFF, T037) coloca o `Principal` em `request.state.principal`.
"""

from __future__ import annotations

import ipaddress
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from fastapi import HTTPException, Request, status
from sqlalchemy import Engine

from cap_control_plane.audit.chain import AuditEvent
from cap_control_plane.audit.writer import Origin, append_event
from cap_control_plane.core.db import DbContext, transaction
from cap_control_plane.identity.permissions import Permission, Profile


@dataclass(frozen=True)
class Principal:
    """Quem faz a requisição: membro da organização ativa ou Super Administrador.

    O Super Administrador não tem organização ativa nem perfil (RF-028).
    """

    user_id: uuid.UUID
    organization_id: uuid.UUID | None
    profile: Profile | None
    is_super_admin: bool
    permissions: frozenset[Permission]

    def db_context(self) -> DbContext:
        return DbContext(
            user_id=self.user_id,
            organization_id=self.organization_id,
            is_super_admin=self.is_super_admin,
        )


class AccessDeniedRecorder(Protocol):
    def __call__(self, request: Request, principal: Principal, permission: str) -> None: ...


def route_template(request: Request) -> str:
    """Caminho da rota sem valores (ex.: /users/{user_id}), para não registrar ids no log."""
    route = request.scope.get("route")
    template = getattr(route, "path", None)
    if not isinstance(template, str):
        return request.url.path
    # Em routers incluídos, `route.path` é relativo ao router; os prefixos não têm
    # parâmetros, então os segmentos da URL antes do modelo formam o prefixo.
    segments = request.url.path.rstrip("/").split("/")
    suffix = template.rstrip("/").split("/")
    prefix = segments[: len(segments) - len(suffix) + 1]
    return "/".join(prefix + suffix[1:]) or "/"


def origin_of(request: Request) -> Origin:
    """IP e navegador da requisição. Valores que não são IP (ex.: socket) são descartados."""
    host = request.client.host if request.client else None
    try:
        source_ip = str(ipaddress.ip_address(host)) if host else None
    except ValueError:
        source_ip = None
    user_agent = request.headers.get("user-agent")
    return Origin(source_ip=source_ip, user_agent=user_agent[:512] if user_agent else None)


def audit_access_denied(engine: Engine) -> AccessDeniedRecorder:
    """Grava `access.denied` no Audit Trail (contracts/audit-events.md)."""

    def record(request: Request, principal: Principal, permission: str) -> None:
        now = datetime.now(UTC)
        with transaction(engine, principal.db_context()) as session:
            append_event(
                session,
                AuditEvent(
                    occurred_at=now,
                    recorded_at=now,
                    organization_id=principal.organization_id,
                    actor_user_id=principal.user_id,
                    actor_kind="user",
                    event_type="access.denied",
                    target_type="route",
                    target_id=route_template(request),
                    result="denied",
                    details={"permission": permission, "method": request.method},
                ),
                origin_of(request),
            )

    return record


def current_principal(request: Request) -> Principal:
    principal = getattr(request.state, "principal", None)
    if not isinstance(principal, Principal):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sessão ausente ou expirada")
    return principal


def require(permission: Permission) -> Callable[[Request], Principal]:
    """Dependência que exige `permission` no perfil da organização ativa."""
    return require_any(permission)


def require_any(*permissions: Permission) -> Callable[[Request], Principal]:
    """Exige pelo menos uma das permissões (ex.: auditoria da organização ou da instalação)."""

    def dependency(request: Request) -> Principal:
        principal = current_principal(request)
        if not principal.permissions & set(permissions):
            recorder: AccessDeniedRecorder = request.app.state.record_access_denied
            recorder(request, principal, "|".join(p.value for p in permissions))
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Sem permissão para esta ação")
        return principal

    # Lido pelo teste que garante permissão declarada em toda rota (T055, T058).
    dependency.required_permissions = frozenset(permissions)  # type: ignore[attr-defined]
    return dependency


# RF-031: ações sensíveis exigem login completo (senha e código) recente.
RECENT_AUTH_SECONDS = 15 * 60


class ReauthRequiredError(Exception):
    """O último login completo é antigo demais para a ação pedida (RF-031)."""


def require_recent(*permissions: Permission) -> Callable[[Request], Principal]:
    """Permissão (como `require_any`) e login completo há no máximo 15 min (RF-031).

    A permissão vem primeiro: quem não a tem recebe 403, não um pedido de nova autenticação.
    """
    check_permission = require_any(*permissions)

    def dependency(request: Request) -> Principal:
        principal = check_permission(request)
        session = getattr(request.state, "session", None)
        auth_time = float(getattr(session, "auth_time", 0) or 0)
        if time.time() - auth_time > RECENT_AUTH_SECONDS:
            raise ReauthRequiredError()
        return principal

    dependency.required_permissions = frozenset(permissions)  # type: ignore[attr-defined]
    dependency.recent_auth = True  # type: ignore[attr-defined]
    return dependency
