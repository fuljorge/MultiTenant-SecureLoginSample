"""Toda rota declara a proteção (T058; RF-014, RF-024). Roda no CI, sem serviços."""

from __future__ import annotations

from cap_control_plane.identity.permissions import (
    PROFILE_PERMISSIONS,
    SUPER_ADMIN_PERMISSIONS,
    Permission,
)
from cap_control_plane.main import create_app
from tests.support.routes import PUBLIC_ROUTES, api_routes

ROUTES = api_routes(create_app())


def test_toda_rota_declara_permissao_sessao_ou_e_publica_de_proposito() -> None:
    unprotected = [
        f"{r.method} {r.path}"
        for r in ROUTES
        if not r.permissions and not r.session_only and not r.public
    ]

    assert unprotected == [], "Rota sem require(...)/require_session nem lista pública"


def test_reautenticacao_recente_so_junto_de_permissao() -> None:
    """RF-031: require_recent sempre traz a permissão; nunca em rota pública ou de sessão."""
    for route in ROUTES:
        if route.recent_auth:
            assert route.permissions and not route.public, route


def test_nenhuma_rota_publica_tem_protecao_ambigua() -> None:
    for route in ROUTES:
        if route.public:
            assert not route.permissions and not route.session_only, route


def test_lista_de_rotas_publicas_nao_tem_sobras() -> None:
    existing = {(r.method, r.path) for r in ROUTES}

    assert PUBLIC_ROUTES <= existing


def test_nenhuma_permissao_fora_dos_perfis_ou_do_escopo_de_instalacao() -> None:
    """RF-024: o fornecedor só atua pelo Super Administrador; não há permissão "escondida"."""
    granted = set().union(*PROFILE_PERMISSIONS.values(), SUPER_ADMIN_PERMISSIONS)

    assert set().union(*(r.permissions for r in ROUTES)) <= granted
    assert set(Permission) == granted
