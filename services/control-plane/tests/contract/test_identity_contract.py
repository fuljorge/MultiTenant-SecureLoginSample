"""Contrato da API e rotas reais (T078; Princípio VIII; contracts/identity-api.md).

Toda rota do contrato existe com o método e a proteção indicados, e não há rota fora do
contrato. Roda no CI sem serviços.
"""

from __future__ import annotations

import re

from cap_control_plane.identity.permissions import Permission
from cap_control_plane.main import create_app
from tests.support.routes import api_routes
from tests.support.stack import REPO_ROOT

CONTRACT = REPO_ROOT / "specs" / "001-identity-access" / "contracts" / "identity-api.md"
ROW = re.compile(r"^\| `(GET|POST|PUT|PATCH|DELETE) (/[^`]*)` \| ([^|]+) \|")


def _normalize(path: str) -> str:
    """Nomes de parâmetros não importam: /users/{id} == /users/{user_id}."""
    return re.sub(r"\{[^}]+\}", "{}", path)


def _protection(cell: str) -> str | frozenset[Permission]:
    cell = cell.strip()
    if cell in ("público", "Keycloak"):
        return "public"
    if cell == "sessão":
        return "session"
    return frozenset(Permission(p) for p in re.findall(r"`([a-z_:]+)`", cell))


def _contract() -> dict[tuple[str, str], str | frozenset[Permission]]:
    rows = {}
    for line in CONTRACT.read_text(encoding="utf-8").splitlines():
        match = ROW.match(line)
        if match:
            method, path, cell = match.groups()
            rows[(method, _normalize(f"/api/v1{path}"))] = _protection(cell)
    return rows


def _implemented() -> dict[tuple[str, str], str | frozenset[Permission]]:
    routes = {}
    for r in api_routes(create_app()):
        protection: str | frozenset[Permission] = r.permissions or (
            "session" if r.session_only else "public"
        )
        routes[(r.method, _normalize(r.path))] = protection
    return routes


def test_contrato_foi_lido() -> None:
    assert len(_contract()) > 30


def test_toda_rota_do_contrato_existe() -> None:
    assert set(_contract()) - set(_implemented()) == set()


def test_nenhuma_rota_fora_do_contrato() -> None:
    assert set(_implemented()) - set(_contract()) == set()


def _recent(source: str) -> set[tuple[str, str]]:
    if source == "contract":
        found = set()
        for line in CONTRACT.read_text(encoding="utf-8").splitlines():
            match = ROW.match(line)
            if match and "recente" in match.group(3):
                found.add((match.group(1), _normalize(f"/api/v1{match.group(2)}")))
        return found
    return {(r.method, _normalize(r.path)) for r in api_routes(create_app()) if r.recent_auth}


def test_reautenticacao_recente_exatamente_nas_rotas_do_contrato() -> None:
    """RF-031 (T093): as rotas marcadas no contrato são as que usam require_recent."""
    assert _recent("contract")
    assert _recent("code") == _recent("contract")


def test_protecao_de_cada_rota_e_a_do_contrato() -> None:
    contract, implemented = _contract(), _implemented()
    differences = {
        key: (contract[key], implemented[key])
        for key in contract.keys() & implemented.keys()
        if contract[key] != implemented[key]
    }

    assert differences == {}
