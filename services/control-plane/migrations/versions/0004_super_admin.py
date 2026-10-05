"""Super Administrador no lugar do Administrador da instalação (revisão 2026-10-03).

specs/001-identity-access/data-model.md e plano, seções 4.11 e 12 (T084):

- `installation_admin` vira `super_admin`. O escopo amplo `has_installation_scope()`
  passa a valer só para fluxos internos do sistema; o Super Administrador ganha políticas
  próprias, que só expõem organizações, vínculos e convites de Administrador, as pessoas
  que são Administradores e os Super Administradores (RF-028). Nenhum papel ignora o RLS.
- *Triggers* impedem que um Super Administrador tenha vínculo com organização (RF-028).
- `organization.status` (pendente, ativa, suspensa, cancelada); sem organização padrão.
- `membership.status` ganha `disabled` (desativação por organização, plano §4.4).
- `audit_event.installation_scope` marca os eventos da gestão da instalação.
- Dados existentes: o Administrador da instalação vira Super Administrador e os vínculos
  dele com organizações são marcados como `removed`, com evento no Audit Trail.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-03
"""

from typing import Any, cast

from alembic import op
from sqlalchemy import text

from cap_control_plane.audit.chain import AuditEvent
from cap_control_plane.audit.writer import append_event

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

UPGRADE = r"""
-- Contexto da transação --------------------------------------------------------------
ALTER TABLE identity.installation_admin RENAME TO super_admin;
ALTER POLICY installation_admin_read ON identity.super_admin RENAME TO super_admin_own;
ALTER POLICY installation_admin_write ON identity.super_admin RENAME TO super_admin_system_insert;
ALTER POLICY installation_admin_delete ON identity.super_admin RENAME TO super_admin_system_delete;
ALTER POLICY installation_admin_lock ON identity.super_admin RENAME TO super_admin_system_lock;

-- Escopo amplo só para fluxos internos (aceite por token, eventos do Keycloak, CLI).
CREATE OR REPLACE FUNCTION identity.has_installation_scope() RETURNS boolean
    LANGUAGE sql STABLE AS $$ SELECT identity.is_system() $$;
DROP FUNCTION identity.is_installation_admin();

-- Marca vinda da sessão (o Control Plane só a liga para quem está em super_admin).
CREATE FUNCTION identity.super_admin_flag() RETURNS boolean
    LANGUAGE sql STABLE
    AS $$ SELECT coalesce(nullif(current_setting('app.is_super_admin', true), ''),
                          'false')::boolean $$;
-- Super Administrador de fato: a marca e a linha em super_admin. A consulta a super_admin
-- passa pelas políticas dela, que usam só a marca (sem recursão).
CREATE FUNCTION identity.is_super_admin() RETURNS boolean
    LANGUAGE sql STABLE
    AS $$ SELECT identity.super_admin_flag() AND EXISTS (
              SELECT 1 FROM identity.super_admin s
              WHERE s.user_id = identity.current_user_id()) $$;

-- Políticas do Super Administrador (somam-se às existentes; RF-025 a RF-030) ----------
CREATE POLICY super_admin_manage ON identity.super_admin
    USING (identity.super_admin_flag()) WITH CHECK (identity.super_admin_flag());

CREATE POLICY organization_super ON identity.organization
    USING (identity.is_super_admin()) WITH CHECK (identity.is_super_admin());

CREATE POLICY membership_super ON identity.membership
    USING (identity.is_super_admin() AND profile = 'administrator')
    WITH CHECK (identity.is_super_admin() AND profile = 'administrator');

CREATE POLICY invitation_super ON identity.invitation
    USING (identity.is_super_admin() AND profile = 'administrator')
    WITH CHECK (identity.is_super_admin() AND profile = 'administrator');

-- Pessoas: só Administradores de organização e Super Administradores. O INSERT cria a
-- pessoa convidada; o vínculo de Administrador vem na mesma transação.
CREATE POLICY user_account_super_read ON identity.user_account FOR SELECT
    USING (identity.is_super_admin() AND (
        EXISTS (SELECT 1 FROM identity.membership m
                WHERE m.user_id = user_account.id AND m.profile = 'administrator')
        OR EXISTS (SELECT 1 FROM identity.super_admin s WHERE s.user_id = user_account.id)));
CREATE POLICY user_account_super_insert ON identity.user_account FOR INSERT
    WITH CHECK (identity.is_super_admin());
CREATE POLICY user_account_super_update ON identity.user_account FOR UPDATE
    USING (identity.is_super_admin() AND (
        EXISTS (SELECT 1 FROM identity.membership m
                WHERE m.user_id = user_account.id AND m.profile = 'administrator')
        OR EXISTS (SELECT 1 FROM identity.super_admin s WHERE s.user_id = user_account.id)))
    WITH CHECK (identity.is_super_admin());

-- Situação da organização -------------------------------------------------------------
CREATE TYPE identity.organization_status AS ENUM ('pending', 'active', 'suspended', 'cancelled');
ALTER TABLE identity.organization
    ADD COLUMN status identity.organization_status NOT NULL DEFAULT 'active',
    ADD COLUMN status_changed_at timestamptz,
    ADD COLUMN status_changed_by uuid,
    ADD COLUMN version integer NOT NULL DEFAULT 1;
-- As existentes ficam ativas; as novas nascem pendentes (convite de organização).
ALTER TABLE identity.organization ALTER COLUMN status SET DEFAULT 'pending';
DROP INDEX identity.organization_single_default;
ALTER TABLE identity.organization DROP COLUMN is_default;

-- Desativação por organização (plano §4.4).
ALTER TYPE identity.membership_status ADD VALUE 'disabled' BEFORE 'removed';

-- Segregação do Super Administrador (RF-028) -------------------------------------------
-- As consultas precisam enxergar além do RLS de quem age (ex.: o Administrador de uma
-- organização não vê a tabela super_admin). A marca de sistema é ligada só durante a
-- verificação e volta ao valor anterior.
CREATE FUNCTION identity.check_super_admin_segregation() RETURNS trigger
    LANGUAGE plpgsql AS $$
DECLARE
    previous text := current_setting('app.is_system', true);
    conflict boolean;
BEGIN
    PERFORM set_config('app.is_system', 'true', true);
    IF TG_TABLE_NAME = 'membership' THEN
        conflict := NEW.status::text <> 'removed' AND EXISTS (
            SELECT 1 FROM identity.super_admin WHERE user_id = NEW.user_id);
    ELSE
        conflict := EXISTS (
            SELECT 1 FROM identity.membership
            WHERE user_id = NEW.user_id AND status::text <> 'removed');
    END IF;
    PERFORM set_config('app.is_system', coalesce(previous, 'false'), true);
    IF conflict THEN
        RAISE EXCEPTION 'Super Administrador não pode ter vínculo com organização (RF-028)'
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER membership_super_admin_segregation
    BEFORE INSERT OR UPDATE OF user_id, status ON identity.membership
    FOR EACH ROW EXECUTE FUNCTION identity.check_super_admin_segregation();
CREATE TRIGGER super_admin_segregation
    BEFORE INSERT OR UPDATE OF user_id ON identity.super_admin
    FOR EACH ROW EXECUTE FUNCTION identity.check_super_admin_segregation();
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA identity TO cap_app;

-- Auditoria: eventos da gestão da instalação ------------------------------------------
ALTER TABLE audit.audit_event ADD COLUMN installation_scope boolean NOT NULL DEFAULT false;
-- O Super Administrador vê os eventos da instalação e os acessos dos Super
-- Administradores, nunca os eventos internos das organizações (US6, cenário 2).
CREATE POLICY audit_event_super_read ON audit.audit_event FOR SELECT
    USING (identity.is_super_admin() AND (
        installation_scope
        OR EXISTS (SELECT 1 FROM identity.super_admin s WHERE s.user_id = actor_user_id)));
"""

# Vínculos do antigo Administrador da instalação deixam de existir (RF-028).
CONVERT = r"""
SELECT set_config('app.is_system', 'true', true);
"""


def _convert_existing(connection: Any) -> None:
    connection.execute(text(CONVERT))
    admins = connection.execute(text("SELECT user_id FROM identity.super_admin")).scalars().all()
    for user_id in admins:
        removed = connection.execute(
            text(
                "UPDATE identity.membership SET status = 'removed', version = version + 1,"
                " updated_at = now() WHERE user_id = :u AND status <> 'removed' RETURNING id"
            ),
            {"u": user_id},
        ).all()
        # append_event só usa `execute`; a conexão da migração serve como sessão.
        append_event(
            cast(Any, connection),
            AuditEvent.now(
                organization_id=None,
                actor_user_id=None,
                actor_kind="system",
                event_type="super_admin.converted",
                target_type="user",
                target_id=str(user_id),
                result="success",
                details={"memberships_removed": len(removed)},
                installation_scope=True,
            ),
        )
    connection.execute(text("SELECT set_config('app.is_system', 'false', true)"))


def upgrade() -> None:
    op.execute(UPGRADE)
    _convert_existing(op.get_bind())


def downgrade() -> None:
    raise NotImplementedError(
        "A 0004 não tem volta: o Super Administrador substitui o Administrador da instalação."
    )
