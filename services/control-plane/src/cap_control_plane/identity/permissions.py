"""Catálogo de permissões e matriz de perfis e permissões (T027; spec, seção 5.1).

A matriz espelha a tabela da seção 5.1 da spec; tests/unit/identity/test_permissions.py lê
a tabela da spec e falha se as duas divergirem. As permissões valem para o perfil da
pessoa na organização ativa. Nada é permitido por omissão (RF-014).
"""

from __future__ import annotations

from enum import StrEnum


class Profile(StrEnum):
    """Perfis fixos de §4.1 a §4.6 (RF-013)."""

    ADMINISTRATOR = "administrator"
    AGENT_DESIGNER = "agent_designer"
    BUSINESS_ANALYST = "business_analyst"
    SUPERVISOR = "supervisor"
    DEVELOPER = "developer"
    FINANCIAL_ADMIN = "financial_admin"


class Permission(StrEnum):
    # Instalação: só o Super Administrador (spec §4.8; RF-016, RF-028).
    ORGANIZATIONS_MANAGE = "organizations:manage"
    ORGANIZATION_ADMINS_MANAGE = "organization_admins:manage"
    SUPER_ADMINS_MANAGE = "super_admins:manage"
    SECURITY_MANAGE = "security:manage"
    BILLING_READ_ALL = "billing:read:all"
    BILLING_MANAGE_ALL = "billing:manage:all"
    AUDIT_READ_INSTALLATION = "audit:read:installation"
    # Organização: perfis de §4.1 a §4.6.
    USERS_READ = "users:read"
    USERS_MANAGE = "users:manage"
    ENVIRONMENTS_READ = "environments:read"
    ENVIRONMENTS_MANAGE = "environments:manage"
    MODELS_READ = "models:read"
    MODELS_MANAGE = "models:manage"
    INTEGRATIONS_READ = "integrations:read"
    INTEGRATIONS_MANAGE = "integrations:manage"
    AGENTS_READ = "agents:read"
    AGENTS_MANAGE = "agents:manage"
    AGENTS_PUBLISH = "agents:publish"
    TEST_CONSOLE_USE = "test_console:use"
    CONVERSATIONS_READ = "conversations:read"
    CONVERSATIONS_REVIEW = "conversations:review"
    OPERATIONS_READ = "operations:read"
    OPERATIONS_MANAGE = "operations:manage"
    COSTS_READ_ALL = "costs:read:all"
    # Custos dos agentes sob responsabilidade da pessoa. O filtro por responsável é
    # implementado na feature do Dashboard de Custos (spec, RF-015; achado A9).
    COSTS_READ_OWN = "costs:read:own"
    BILLING_READ = "billing:read"
    BILLING_MANAGE = "billing:manage"
    AUDIT_READ = "audit:read"


P = Permission

# Agrupadas por área da seção 5.1 (formatação manual para facilitar a revisão).
# fmt: off
PROFILE_PERMISSIONS: dict[Profile, frozenset[Permission]] = {
    Profile.ADMINISTRATOR: frozenset(
        {
            P.USERS_READ, P.USERS_MANAGE,
            P.ENVIRONMENTS_READ, P.ENVIRONMENTS_MANAGE,
            P.MODELS_READ, P.MODELS_MANAGE,
            P.INTEGRATIONS_READ, P.INTEGRATIONS_MANAGE,
            P.AGENTS_READ,
            P.TEST_CONSOLE_USE,
            P.CONVERSATIONS_READ,
            P.OPERATIONS_READ,
            P.COSTS_READ_ALL,
            P.BILLING_READ,
            P.AUDIT_READ,
        }
    ),
    Profile.AGENT_DESIGNER: frozenset(
        {
            P.ENVIRONMENTS_READ,
            P.MODELS_READ,
            P.INTEGRATIONS_READ,
            P.AGENTS_READ, P.AGENTS_MANAGE, P.AGENTS_PUBLISH,
            P.TEST_CONSOLE_USE,
            P.CONVERSATIONS_READ,
            P.OPERATIONS_READ,
            P.COSTS_READ_OWN,
        }
    ),
    Profile.BUSINESS_ANALYST: frozenset(
        {
            P.AGENTS_READ,
            P.TEST_CONSOLE_USE,
            P.CONVERSATIONS_READ, P.CONVERSATIONS_REVIEW,
            P.OPERATIONS_READ,
            P.COSTS_READ_OWN,
        }
    ),
    Profile.SUPERVISOR: frozenset(
        {
            P.AGENTS_READ,
            P.TEST_CONSOLE_USE,
            P.CONVERSATIONS_READ,
            P.OPERATIONS_READ, P.OPERATIONS_MANAGE,
        }
    ),
    Profile.DEVELOPER: frozenset(
        {
            P.ENVIRONMENTS_READ,
            P.MODELS_READ,
            P.INTEGRATIONS_READ, P.INTEGRATIONS_MANAGE,
            P.AGENTS_READ,
            P.TEST_CONSOLE_USE,
        }
    ),
    Profile.FINANCIAL_ADMIN: frozenset(
        {
            P.COSTS_READ_ALL,
            P.BILLING_READ, P.BILLING_MANAGE,
        }
    ),
}
# fmt: on

# Super Administrador (spec §4.8; RF-025 a RF-030): gere a instalação e as organizações,
# nunca o que existe dentro delas. Disjunto das permissões dos perfis (RF-028).
SUPER_ADMIN_PERMISSIONS: frozenset[Permission] = frozenset(
    {
        P.ORGANIZATIONS_MANAGE,
        P.ORGANIZATION_ADMINS_MANAGE,
        P.SUPER_ADMINS_MANAGE,
        P.SECURITY_MANAGE,
        P.BILLING_READ_ALL,
        P.BILLING_MANAGE_ALL,
        P.AUDIT_READ_INSTALLATION,
    }
)


def effective_permissions(
    profile: Profile | None, *, is_super_admin: bool
) -> frozenset[Permission]:
    """Permissões do principal: o perfil na organização ativa ou as do Super Administrador.

    Os dois nunca se somam: o Super Administrador não tem vínculo com organizações.
    """
    if is_super_admin:
        if profile is not None:
            raise ValueError("Super Administrador não tem perfil em organização (RF-028)")
        return SUPER_ADMIN_PERMISSIONS
    return PROFILE_PERMISSIONS[profile] if profile else frozenset()
