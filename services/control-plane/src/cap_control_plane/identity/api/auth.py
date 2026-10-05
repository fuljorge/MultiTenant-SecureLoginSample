"""Rotas de autenticação do BFF (T036; contracts/identity-api.md)."""

from __future__ import annotations

import hashlib
import json
import logging
import secrets
import uuid
from datetime import UTC, datetime
from typing import Annotated
from urllib.parse import parse_qs

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import RedirectResponse

from cap_control_plane.audit.chain import AuditEvent
from cap_control_plane.audit.writer import append_event
from cap_control_plane.core.db import transaction
from cap_control_plane.identity.activation import activate_on_first_login
from cap_control_plane.identity.authz import Principal, origin_of
from cap_control_plane.identity.cookies import (
    CSRF_COOKIE,
    LOGIN_COOKIE,
    SESSION_COOKIE,
    clear_cookie,
    set_cookie,
)
from cap_control_plane.identity.directory import UserRecord, get_user, organizations_for
from cap_control_plane.identity.oidc import OidcError, PkcePair
from cap_control_plane.identity.session_auth import require_session
from cap_control_plane.services import Services, get_services

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])

LOGIN_TTL_SECONDS = 600
ServicesDep = Annotated[Services, Depends(get_services)]


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _login_key(state: str) -> str:
    return f"cap:login:{_sha256(state)}"


def last_org_key(user_id: uuid.UUID) -> str:
    return f"cap:last-org:{user_id}"


def _safe_return_path(value: str | None) -> str:
    """Só caminhos relativos do próprio Studio (evita redirecionamento aberto)."""
    if not value or not value.startswith("/") or value.startswith("//") or "\\" in value:
        return "/"
    return value


def _start_login(
    services: Services, return_to: str, kc_action: str | None = None, *, reauth: bool = False
) -> Response:
    state, nonce, binding = (secrets.token_urlsafe(32) for _ in range(3))
    pkce = PkcePair.new()
    services.valkey.set(
        _login_key(state),
        json.dumps(
            {
                "nonce": nonce,
                "verifier": pkce.verifier,
                "binding": _sha256(binding),
                "return_to": _safe_return_path(return_to),
            }
        ),
        ex=LOGIN_TTL_SECONDS,
    )
    url = services.oidc.authorization_url(
        state=state, nonce=nonce, pkce=pkce, kc_action=kc_action, reauth=reauth
    )
    response = RedirectResponse(url, status_code=status.HTTP_303_SEE_OTHER)
    set_cookie(response, LOGIN_COOKIE, binding, http_only=True, max_age=LOGIN_TTL_SECONDS)
    return response


def _login_error(services: Services, reason: str) -> Response:
    url = f"{services.settings.public_url}/entrar/erro?motivo={reason}"
    response = RedirectResponse(url, status_code=status.HTTP_303_SEE_OTHER)
    clear_cookie(response, LOGIN_COOKIE)
    return response


@router.get("/login", summary="Inicia o login (Authorization Code + PKCE)")
def start_login(services: ServicesDep, return_to: str = "/", reauth: bool = False) -> Response:
    """Com `reauth`, exige senha e código de novo (ação sensível; RF-031)."""
    return _start_login(services, return_to, reauth=reauth)


def _initial_organization(services: Services, user: UserRecord) -> uuid.UUID | None:
    """Última organização ativa usada, ou a primeira; nenhuma para o Super Administrador."""
    organizations = organizations_for(services.engine, user)
    if not organizations:
        return None
    preferred = services.valkey.get(last_org_key(user.id))
    available = {o.id for o in organizations}
    if preferred and uuid.UUID(preferred.decode()) in available:  # type: ignore[union-attr]
        return uuid.UUID(preferred.decode())  # type: ignore[union-attr]
    return organizations[0].id


@router.get("/callback", summary="Retorno do Keycloak; cria a sessão")
def login_callback(
    request: Request,
    services: ServicesDep,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> Response:
    if error or not code or not state:
        return _login_error(services, "cancelado")
    raw = services.valkey.getdel(_login_key(state))
    binding = request.cookies.get(LOGIN_COOKIE)
    if raw is None or binding is None:
        return _login_error(services, "expirado")
    attempt = json.loads(raw)
    if not secrets.compare_digest(attempt["binding"], _sha256(binding)):
        return _login_error(services, "expirado")

    try:
        tokens = services.oidc.exchange_code(code, attempt["verifier"])
        claims = services.oidc.validate_id_token(tokens["id_token"], nonce=attempt["nonce"])
    except (OidcError, KeyError):
        return _login_error(services, "falha")

    origin = origin_of(request)
    user = get_user(services.engine, uuid.UUID(claims.subject))
    if user is not None and user.status == "invited":
        # Primeiro login após o convite ou as boas-vindas (US2, US3).
        activate_on_first_login(services.engine, user.id, origin)
        user = get_user(services.engine, user.id)
    if user is None or user.status != "active":
        return _login_error(services, "sem-acesso")
    organization_id = _initial_organization(services, user)
    if organization_id is None and not user.is_super_admin:
        return _login_error(services, "sem-organizacao")

    # Novo login no mesmo navegador (ex.: reautenticação): a sessão anterior deixa de valer.
    previous = request.cookies.get(SESSION_COOKIE)
    if previous:
        services.sessions.delete(previous)
    created = services.sessions.create(
        user_id=user.id,
        keycloak_sid=claims.keycloak_sid,
        organization_id=organization_id,
        tokens=tokens,
        user_agent=origin.user_agent,
        source_ip=origin.source_ip,
        auth_time=claims.auth_time,
    )
    response = RedirectResponse(
        f"{services.settings.public_url}{attempt['return_to']}",
        status_code=status.HTTP_303_SEE_OTHER,
    )
    set_cookie(response, SESSION_COOKIE, created.sid, http_only=True)
    set_cookie(response, CSRF_COOKIE, created.csrf_token, http_only=False)
    clear_cookie(response, LOGIN_COOKIE)
    return response


@router.get("/password", summary="Troca de senha no Keycloak")
def start_password_change(
    services: ServicesDep, _: Annotated[Principal, Depends(require_session)]
) -> Response:
    # Sempre com nova autenticação, qualquer que seja a idade do login (RF-031).
    return _start_login(services, "/conta/sessoes", kc_action="UPDATE_PASSWORD", reauth=True)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, summary="Encerra a sessão")
async def logout(
    request: Request,
    services: ServicesDep,
    principal: Annotated[Principal, Depends(require_session)],
) -> Response:
    session = request.state.session
    sid: str = request.state.session_id

    def end() -> None:
        # A sessão do Studio acaba primeiro: com o Keycloak lento ou fora do ar, "Sair" não
        # pode deixar a pessoa logada. A sessão SSO expira sozinha (inatividade de 30 min).
        services.sessions.delete(sid)
        try:
            services.keycloak_admin.delete_session(session.keycloak_sid)
        except Exception:
            logger.exception("Falha ao encerrar a sessão no Keycloak durante o logout")
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
                    event_type="auth.logout",
                    target_type="user",
                    target_id=str(principal.user_id),
                    result="success",
                    details={"reason": "user"},
                ),
                origin_of(request),
            )

    await run_in_threadpool(end)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    clear_cookie(response, SESSION_COOKIE)
    clear_cookie(response, CSRF_COOKIE)
    return response


@router.post("/backchannel-logout", summary="Back-channel logout do Keycloak")
async def backchannel_logout(request: Request, services: ServicesDep) -> Response:
    # Corpo application/x-www-form-urlencoded com o campo logout_token (OIDC Back-Channel
    # Logout 1.0). Lido com a biblioteca padrão para não depender de python-multipart.
    fields = parse_qs((await request.body()).decode(), max_num_fields=5)
    logout_token = (fields.get("logout_token") or [""])[0]
    try:
        keycloak_sid = services.oidc.validate_logout_token(logout_token)
    except OidcError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Logout token inválido") from exc
    await run_in_threadpool(services.sessions.delete_by_keycloak_sid, keycloak_sid)
    return Response(status_code=status.HTTP_200_OK)
