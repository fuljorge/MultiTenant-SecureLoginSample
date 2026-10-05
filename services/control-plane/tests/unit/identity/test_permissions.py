"""Matriz de permissões (T026, T080; RF-013, RF-014, RF-016, RF-028; spec, seção 5.1).

A matriz esperada é lida da própria spec: se a tabela da seção 5.1 mudar sem o código
(ou o contrário), este teste falha. A primeira coluna é o Super Administrador.
"""

from __future__ import annotations

import re

import pytest

from cap_control_plane.identity.permissions import (
    PROFILE_PERMISSIONS,
    SUPER_ADMIN_PERMISSIONS,
    Permission,
    Profile,
    effective_permissions,
)
from tests.support.stack import REPO_ROOT

SPEC = REPO_ROOT / "specs" / "001-identity-access" / "spec.md"

SUPER = "super_admin"
COLUMNS: list[Profile | str] = [
    SUPER,
    Profile.ADMINISTRATOR,
    Profile.AGENT_DESIGNER,
    Profile.BUSINESS_ANALYST,
    Profile.SUPERVISOR,
    Profile.DEVELOPER,
    Profile.FINANCIAL_ADMIN,
]
P = Permission

# Linha da tabela -> (permissão de leitura, permissão de gestão).
ROWS: dict[str, tuple[Permission | None, Permission | None]] = {
    "Organizações (criar, suspender, reativar)": (None, P.ORGANIZATIONS_MANAGE),
    "Política de segurança da instalação": (None, P.SECURITY_MANAGE),
    "Super Administradores": (None, P.SUPER_ADMINS_MANAGE),
    "Administradores das organizações": (None, P.ORGANIZATION_ADMINS_MANAGE),
    "Demais usuários e perfis": (P.USERS_READ, P.USERS_MANAGE),
    # Ainda sem rota nem permissão própria: virá com a feature de configuração.
    "Configuração da organização": (None, None),
    "Ambientes (§30)": (P.ENVIRONMENTS_READ, P.ENVIRONMENTS_MANAGE),
    "Modelos de IA (§40)": (P.MODELS_READ, P.MODELS_MANAGE),
    "Conexões corporativas, APIs, MCP": (P.INTEGRATIONS_READ, P.INTEGRATIONS_MANAGE),
    "Agentes, Goals, Skills, prompts, RAG, workflows": (P.AGENTS_READ, P.AGENTS_MANAGE),
    "Cockpit de Teste e Demo Chat": (None, None),
    "Publicação de agentes": (None, None),
    "Conversas e análise de eficácia": (P.CONVERSATIONS_READ, None),
    "Monitoramento operacional e transferências": (P.OPERATIONS_READ, P.OPERATIONS_MANAGE),
    "Custos (§57)": (None, None),
    "Faturas, planos, orçamentos": (P.BILLING_READ, P.BILLING_MANAGE),
    "Audit Trail": (None, None),
}


def _cell_permissions(row: str, cell: str) -> set[Permission]:
    read, manage = ROWS[row]
    cell = cell.strip()
    if cell == "—":
        return set()
    if cell == "Ver":
        return {read} if read else set()
    if cell == "Gerenciar":
        return {p for p in (read, manage) if p}
    if cell == "Gerenciar (na sua)":
        # O Administrador gere os Administradores da sua organização como os demais usuários.
        return {P.USERS_READ, P.USERS_MANAGE}
    if cell == "Gerenciar (todas)":
        return {P.BILLING_READ_ALL, P.BILLING_MANAGE_ALL}
    if cell == "Da instalação":
        return {P.AUDIT_READ_INSTALLATION}
    if cell == "Da organização":
        return {P.AUDIT_READ}
    if cell == "Usar":
        return {P.TEST_CONSOLE_USE}
    if cell == "Executar":
        return {P.AGENTS_PUBLISH}
    if cell == "Gerenciar revisões":
        return {P.CONVERSATIONS_READ, P.CONVERSATIONS_REVIEW}
    if cell == "Completo":
        return {P.COSTS_READ_ALL}
    if cell == "Seus agentes":
        return {P.COSTS_READ_OWN}
    raise AssertionError(f"Célula desconhecida na seção 5.1: {row!r} = {cell!r}")


def _matrix_from_spec() -> dict[Profile | str, set[Permission]]:
    text = SPEC.read_text(encoding="utf-8")
    section = text[text.index("### 5.1 Matriz de perfis") :]
    section = section[: section.index("\n## ")]
    expected: dict[Profile | str, set[Permission]] = {p: set() for p in COLUMNS}
    rows_seen = set()
    for line in section.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) != 8 or cells[0] in ("Área", "") or re.fullmatch(r"-+", cells[0]):
            continue
        row = cells[0]
        rows_seen.add(row)
        for column, cell in zip(COLUMNS, cells[1:], strict=True):
            expected[column] |= _cell_permissions(row, cell)
    assert rows_seen == set(ROWS), "Linhas da seção 5.1 mudaram; atualize ROWS e o código"
    return expected


def test_matriz_do_codigo_e_igual_a_da_spec() -> None:
    expected = _matrix_from_spec()

    assert SUPER_ADMIN_PERMISSIONS == expected[SUPER]
    for profile in Profile:
        assert PROFILE_PERMISSIONS[profile] == expected[profile], profile


def test_permissoes_de_instalacao_e_de_organizacao_sao_disjuntas() -> None:
    """RF-016, RF-028: nenhum perfil tem permissão de instalação e vice-versa."""
    for profile in Profile:
        assert not PROFILE_PERMISSIONS[profile] & SUPER_ADMIN_PERMISSIONS, profile


def test_toda_permissao_pertence_a_algum_perfil_ou_ao_super_administrador() -> None:
    granted = set().union(*PROFILE_PERMISSIONS.values(), SUPER_ADMIN_PERMISSIONS)

    assert granted == set(Permission)


def test_super_administrador_so_tem_permissoes_de_instalacao() -> None:
    assert effective_permissions(None, is_super_admin=True) == SUPER_ADMIN_PERMISSIONS


def test_super_administrador_nao_herda_perfil_de_organizacao() -> None:
    with pytest.raises(ValueError, match="Super Administrador"):
        effective_permissions(Profile.ADMINISTRATOR, is_super_admin=True)


def test_administrador_nao_tem_escopo_de_instalacao() -> None:
    admin = effective_permissions(Profile.ADMINISTRATOR, is_super_admin=False)

    assert not admin & SUPER_ADMIN_PERMISSIONS


def test_sem_perfil_nao_tem_permissao() -> None:
    assert effective_permissions(None, is_super_admin=False) == frozenset()


@pytest.mark.parametrize("profile", [p for p in Profile if p is not Profile.AGENT_DESIGNER])
def test_so_agent_designer_publica(profile: Profile) -> None:
    assert Permission.AGENTS_PUBLISH not in PROFILE_PERMISSIONS[profile]
