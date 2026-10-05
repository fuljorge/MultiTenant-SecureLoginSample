"""Inventário das rotas da API e da proteção declarada em cada uma (T055, T058)."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI
from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute, iter_route_contexts

from cap_control_plane.identity.permissions import Permission

# Rotas sem sessão, de propósito. Abrir uma rota nova sem autenticação exige editar esta
# lista (e passar pela revisão). RF-024: nada aqui dá acesso a dados da instalação.
PUBLIC_ROUTES = {
    ("GET", "/api/v1/auth/login"),  # inicia o login
    ("GET", "/api/v1/auth/callback"),  # retorno do Keycloak
    ("POST", "/api/v1/auth/backchannel-logout"),  # Keycloak → Control Plane (token assinado)
    ("POST", "/api/v1/email-change/{token}/confirm"),  # link de uso único enviado por e-mail
}


@dataclass(frozen=True)
class RouteInfo:
    method: str
    path: str
    # Qualquer uma basta (require_any); vazio = sem permissão declarada.
    permissions: frozenset[Permission]
    session_only: bool
    # Exige login completo recente (RF-031; require_recent).
    recent_auth: bool = False

    @property
    def public(self) -> bool:
        return (self.method, self.path) in PUBLIC_ROUTES

    def sample_path(self) -> str:
        """Caminho com valores de exemplo nos parâmetros (ids inexistentes)."""
        return re.sub(
            r"\{(\w+)\}",
            lambda m: (
                "token-de-teste"
                if m.group(1) == "token"
                else "00000000-0000-4000-8000-000000000000"
            ),
            self.path,
        )


def _calls(dependant: Dependant) -> Iterator[Callable[..., Any]]:
    for dependency in dependant.dependencies:
        if dependency.call is not None:
            yield dependency.call
        yield from _calls(dependency)


def api_routes(app: FastAPI) -> list[RouteInfo]:
    """Rotas da API com o caminho completo.

    No FastAPI 0.142 as rotas de routers incluídos não aparecem achatadas em `app.routes`;
    `iter_route_contexts` percorre os routers incluídos com o caminho efetivo.
    """
    routes = []
    for context in iter_route_contexts(app.routes):
        route = getattr(context, "original_route", context)
        path = getattr(context, "path", "")
        if not isinstance(route, APIRoute) or not path.startswith("/api/"):
            continue
        calls = list(_calls(route.dependant))
        permissions: frozenset[Permission] = frozenset().union(
            *(c.required_permissions for c in calls if hasattr(c, "required_permissions"))
        )
        session_only = any(getattr(c, "session_only", False) for c in calls)
        recent_auth = any(getattr(c, "recent_auth", False) for c in calls)
        for method in sorted(route.methods or ()):
            routes.append(
                RouteInfo(
                    method=method,
                    path=path,
                    permissions=permissions,
                    session_only=session_only,
                    recent_auth=recent_auth,
                )
            )
    return routes
