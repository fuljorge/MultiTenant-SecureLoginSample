"""Dependência para rotas que só exigem sessão, sem permissão específica (ex.: /me).

Marcada com `session_only` para o teste que verifica permissão declarada em toda rota
(T055, T058): toda rota da API usa `require(...)` ou `require_session`.
"""

from fastapi import Request

from cap_control_plane.identity.authz import Principal, current_principal


def require_session(request: Request) -> Principal:
    return current_principal(request)


require_session.session_only = True  # type: ignore[attr-defined]
