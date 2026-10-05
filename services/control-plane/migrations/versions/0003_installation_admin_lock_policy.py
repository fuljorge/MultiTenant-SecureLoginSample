"""Política de UPDATE em identity.installation_admin, necessária para travar as linhas.

No PostgreSQL, `SELECT ... FOR UPDATE` também aplica as políticas RLS de UPDATE. Sem
uma política de UPDATE, a consulta que trava os Administradores da instalação voltava
vazia e a regra "a instalação nunca fica sem Administrador" (RF-012) não era aplicada
com desativações simultâneas. Nenhum dado muda.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-03
"""

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE POLICY installation_admin_lock ON identity.installation_admin FOR UPDATE
            USING (identity.has_installation_scope())
            WITH CHECK (identity.has_installation_scope());
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY installation_admin_lock ON identity.installation_admin;")
