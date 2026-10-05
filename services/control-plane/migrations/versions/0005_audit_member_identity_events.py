"""Administrador vê os eventos de identidade das pessoas da organização (T068; US6).

Eventos de login, falha de senha, bloqueio e troca de senha vêm do Keycloak sem
organização: o login vale para todas as organizações da pessoa. Sem esta política, o
Administrador não encontraria o login de quem administra (US6, cenário 1).

Visível ao Administrador da organização ativa: evento sem organização, fora da gestão da
instalação, cujo autor tem vínculo (não removido) com essa organização. Quem foi removido
deixa de ter os novos eventos expostos.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-03
"""

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE POLICY audit_event_member_identity_read ON audit.audit_event FOR SELECT
            USING (
                organization_id IS NULL
                AND NOT installation_scope
                AND identity.current_organization_id() IS NOT NULL
                AND EXISTS (
                    SELECT 1 FROM identity.membership m
                    WHERE m.user_id = audit_event.actor_user_id
                      AND m.organization_id = identity.current_organization_id()
                      AND m.status <> 'removed'
                )
            );
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY audit_event_member_identity_read ON audit.audit_event;")
