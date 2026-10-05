"""Base dos serviços de identidade: erros de negócio e auditoria das ações (T050)."""

from __future__ import annotations

import hashlib
import secrets
import uuid
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from cap_control_plane.audit.chain import AuditEvent, Result
from cap_control_plane.audit.writer import Origin, append_event
from cap_control_plane.identity.authz import Principal, ReauthRequiredError


class ServiceError(Exception):
    """Erro de negócio com status HTTP. A mensagem é exibida ao usuário (sem dados sensíveis)."""

    status_code = 400

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class NotFoundError(ServiceError):
    status_code = 404


class ConflictError(ServiceError):
    status_code = 409


class ScopeError(ServiceError):
    """Ação fora do escopo do Administrador (ex.: pessoa de outra organização)."""

    status_code = 403


class VersionMismatchError(ServiceError):
    """Edição concorrente: o recurso mudou desde a leitura (If-Match)."""

    status_code = 412


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ReauthRequiredError)
    async def reauth(_: Request, __: ReauthRequiredError) -> JSONResponse:
        # O Studio reconhece o código e leva a pessoa à nova autenticação (RF-031).
        return JSONResponse(
            {
                "title": "Confirme sua identidade para continuar.",
                "status": 401,
                "code": "reauth_required",
            },
            status_code=401,
            media_type="application/problem+json",
        )

    @app.exception_handler(ServiceError)
    async def handle(_: Request, exc: ServiceError) -> JSONResponse:
        # Problem Details (RFC 9457), sem dados sensíveis.
        return JSONResponse(
            {"title": exc.message, "status": exc.status_code},
            status_code=exc.status_code,
            media_type="application/problem+json",
        )


def new_token() -> tuple[str, bytes]:
    """Token aleatório de 256 bits para links de uso único e o hash guardado no banco."""
    token = secrets.token_urlsafe(32)
    return token, token_hash(token)


def token_hash(token: str) -> bytes:
    return hashlib.sha256(token.encode()).digest()


def record(
    session: Session,
    principal: Principal,
    origin: Origin,
    *,
    event_type: str,
    target_type: str,
    target_id: uuid.UUID | str,
    details: dict[str, Any] | None = None,
    organization_id: uuid.UUID | None = None,
    result: Result = "success",
) -> None:
    """Grava a ação no Audit Trail, na mesma transação da operação.

    Ações do Super Administrador são da gestão da instalação (`installation_scope`): ele as
    vê, e o Administrador da organização afetada também (US6, cenário 2).
    """
    append_event(
        session,
        AuditEvent.now(
            organization_id=organization_id or principal.organization_id,
            actor_user_id=principal.user_id,
            actor_kind="user",
            event_type=event_type,
            target_type=target_type,
            target_id=str(target_id),
            result=result,
            details=details or {},
            installation_scope=principal.is_super_admin,
        ),
        origin,
    )
