"""Sessão do BFF e proteção contra CSRF em cada requisição (T037).

Carrega a sessão pelo cookie, monta o `Principal` a partir do banco (perfil na organização
ativa, situação da pessoa) e exige o cabeçalho anti-CSRF nas requisições que alteram estado.
"""

from __future__ import annotations

import hmac
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

from cap_control_plane.identity.cookies import CSRF_COOKIE, CSRF_HEADER, SESSION_COOKIE
from cap_control_plane.identity.directory import principal_for
from cap_control_plane.services import Services

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
# Chamado pelo Keycloak (servidor a servidor), sem cookie nem cabeçalho do Studio.
CSRF_EXEMPT_PATHS = {"/api/v1/auth/backchannel-logout"}


def _load(services: Services, sid: str) -> tuple[object | None, object | None]:
    session = services.sessions.get(sid)
    if session is None:
        return None, None
    principal = principal_for(services.engine, session.user_id, session.organization_id)
    if principal is None:
        # Pessoa desativada ou sem acesso à organização ativa: a sessão acaba.
        services.sessions.delete(sid)
        return None, None
    return session, principal


async def bff_session(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    services: Services = request.app.state.services
    request.state.session = None
    request.state.principal = None

    sid = request.cookies.get(SESSION_COOKIE)
    if sid:
        session, principal = await run_in_threadpool(_load, services, sid)
        request.state.session = session
        request.state.principal = principal
        if session is not None:
            request.state.session_id = sid

    if (
        request.method not in SAFE_METHODS
        and request.url.path not in CSRF_EXEMPT_PATHS
        and request.state.session is not None
    ):
        header = request.headers.get(CSRF_HEADER)
        cookie = request.cookies.get(CSRF_COOKIE)
        if (
            not header
            or not cookie
            or not hmac.compare_digest(header, cookie)
            or not services.sessions.csrf_matches(request.state.session, header)
        ):
            return JSONResponse({"detail": "Token anti-CSRF ausente ou inválido"}, status_code=403)

    return await call_next(request)
