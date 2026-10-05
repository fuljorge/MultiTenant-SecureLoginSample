"""Schema identity: organizações, usuários, vínculos, convites e RLS.

specs/001-identity-access/data-model.md (T020). Políticas RLS conforme a seção "RLS"
do modelo de dados (Princípio IV). O papel `cap_app` só recebe SELECT, INSERT e UPDATE:
nada é apagado fisicamente (desativação e remoção são mudanças de situação).

Revision ID: 0001
Revises:
Create Date: 2026-10-02
"""

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

UPGRADE = r"""
CREATE EXTENSION IF NOT EXISTS citext;
CREATE SCHEMA identity;

-- Contexto da transação, definido por cap_control_plane.core.db.transaction.
CREATE FUNCTION identity.current_user_id() RETURNS uuid
    LANGUAGE sql STABLE AS $$ SELECT nullif(current_setting('app.user_id', true), '')::uuid $$;
CREATE FUNCTION identity.current_organization_id() RETURNS uuid
    LANGUAGE sql STABLE
    AS $$ SELECT nullif(current_setting('app.organization_id', true), '')::uuid $$;
CREATE FUNCTION identity.is_installation_admin() RETURNS boolean
    LANGUAGE sql STABLE
    AS $$ SELECT coalesce(nullif(current_setting('app.is_installation_admin', true), ''),
                          'false')::boolean $$;
CREATE FUNCTION identity.is_system() RETURNS boolean
    LANGUAGE sql STABLE
    AS $$ SELECT coalesce(nullif(current_setting('app.is_system', true), ''), 'false')::boolean $$;
-- Acesso amplo: Administrador da instalação ou fluxo interno do sistema.
CREATE FUNCTION identity.has_installation_scope() RETURNS boolean
    LANGUAGE sql STABLE AS $$ SELECT identity.is_installation_admin() OR identity.is_system() $$;

CREATE TYPE identity.user_status AS ENUM ('invited', 'active', 'disabled');
CREATE TYPE identity.profile AS ENUM (
    'administrator', 'agent_designer', 'business_analyst',
    'supervisor', 'developer', 'financial_admin'
);
CREATE TYPE identity.membership_status AS ENUM ('pending', 'active', 'removed');
CREATE TYPE identity.invitation_status AS ENUM ('pending', 'accepted', 'expired', 'revoked');
CREATE TYPE identity.email_change_status AS ENUM ('pending', 'confirmed', 'expired', 'revoked');

CREATE TABLE identity.organization (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name        text NOT NULL UNIQUE CHECK (length(trim(name)) > 0),
    slug        text NOT NULL UNIQUE CHECK (slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'),
    is_default  boolean NOT NULL DEFAULT false,
    created_at  timestamptz NOT NULL DEFAULT now(),
    created_by  uuid
);
-- Exatamente uma organização padrão por instalação.
CREATE UNIQUE INDEX organization_single_default ON identity.organization (is_default)
    WHERE is_default;

CREATE TABLE identity.user_account (
    id             uuid PRIMARY KEY,  -- mesmo id do usuário no Keycloak
    email          citext NOT NULL UNIQUE,
    name           text NOT NULL,
    status         identity.user_status NOT NULL DEFAULT 'invited',
    last_login_at  timestamptz,
    anonymized_at  timestamptz,
    version        integer NOT NULL DEFAULT 1,
    created_at     timestamptz NOT NULL DEFAULT now(),
    updated_at     timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE identity.installation_admin (
    user_id     uuid PRIMARY KEY REFERENCES identity.user_account (id),
    granted_at  timestamptz NOT NULL DEFAULT now(),
    granted_by  uuid
);

CREATE TABLE identity.membership (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id  uuid NOT NULL REFERENCES identity.organization (id),
    user_id          uuid NOT NULL REFERENCES identity.user_account (id),
    profile          identity.profile NOT NULL,
    status           identity.membership_status NOT NULL DEFAULT 'pending',
    version          integer NOT NULL DEFAULT 1,
    created_at       timestamptz NOT NULL DEFAULT now(),
    created_by       uuid,
    updated_at       timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, user_id)
);
CREATE INDEX membership_user ON identity.membership (user_id);

CREATE TABLE identity.invitation (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id  uuid NOT NULL REFERENCES identity.organization (id),
    email            citext NOT NULL,
    profile          identity.profile NOT NULL,
    token_hash       bytea UNIQUE,  -- SHA-256; só para pessoas já cadastradas
    expires_at       timestamptz NOT NULL,
    status           identity.invitation_status NOT NULL DEFAULT 'pending',
    invited_by       uuid NOT NULL,
    created_at       timestamptz NOT NULL DEFAULT now(),
    accepted_at      timestamptz
);
CREATE INDEX invitation_organization ON identity.invitation (organization_id, status);

CREATE TABLE identity.email_change_request (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       uuid NOT NULL REFERENCES identity.user_account (id),
    new_email     citext NOT NULL,
    token_hash    bytea NOT NULL UNIQUE,  -- SHA-256
    expires_at    timestamptz NOT NULL,
    status        identity.email_change_status NOT NULL DEFAULT 'pending',
    requested_by  uuid NOT NULL,
    created_at    timestamptz NOT NULL DEFAULT now(),
    confirmed_at  timestamptz
);

-- RLS (Princípio IV). FORCE aplica as políticas também ao dono das tabelas.
ALTER TABLE identity.organization ENABLE ROW LEVEL SECURITY;
ALTER TABLE identity.organization FORCE ROW LEVEL SECURITY;
ALTER TABLE identity.user_account ENABLE ROW LEVEL SECURITY;
ALTER TABLE identity.user_account FORCE ROW LEVEL SECURITY;
ALTER TABLE identity.installation_admin ENABLE ROW LEVEL SECURITY;
ALTER TABLE identity.installation_admin FORCE ROW LEVEL SECURITY;
ALTER TABLE identity.membership ENABLE ROW LEVEL SECURITY;
ALTER TABLE identity.membership FORCE ROW LEVEL SECURITY;
ALTER TABLE identity.invitation ENABLE ROW LEVEL SECURITY;
ALTER TABLE identity.invitation FORCE ROW LEVEL SECURITY;
ALTER TABLE identity.email_change_request ENABLE ROW LEVEL SECURITY;
ALTER TABLE identity.email_change_request FORCE ROW LEVEL SECURITY;

-- Vínculos: os da organização ativa e os da própria pessoa (para listar suas organizações).
CREATE POLICY membership_access ON identity.membership
    USING (
        identity.has_installation_scope()
        OR organization_id = identity.current_organization_id()
        OR user_id = identity.current_user_id()
    )
    WITH CHECK (
        identity.has_installation_scope()
        OR organization_id = identity.current_organization_id()
    );

CREATE POLICY organization_read ON identity.organization FOR SELECT
    USING (
        identity.has_installation_scope()
        OR EXISTS (
            SELECT 1 FROM identity.membership m
            WHERE m.organization_id = organization.id
              AND m.user_id = identity.current_user_id()
              AND m.status <> 'removed'
        )
    );
CREATE POLICY organization_write ON identity.organization FOR INSERT
    WITH CHECK (identity.has_installation_scope());
CREATE POLICY organization_update ON identity.organization FOR UPDATE
    USING (identity.has_installation_scope())
    WITH CHECK (identity.has_installation_scope());

-- Pessoas: a própria e as que têm vínculo com a organização ativa.
CREATE POLICY user_account_access ON identity.user_account
    USING (
        identity.has_installation_scope()
        OR id = identity.current_user_id()
        OR EXISTS (
            SELECT 1 FROM identity.membership m
            WHERE m.user_id = user_account.id
              AND m.organization_id = identity.current_organization_id()
        )
    )
    -- Criar pessoa (convite) exige uma organização ativa; o vínculo vem na mesma transação.
    WITH CHECK (
        identity.has_installation_scope()
        OR id = identity.current_user_id()
        OR identity.current_organization_id() IS NOT NULL
    );

CREATE POLICY installation_admin_read ON identity.installation_admin FOR SELECT
    USING (identity.has_installation_scope() OR user_id = identity.current_user_id());
CREATE POLICY installation_admin_write ON identity.installation_admin FOR INSERT
    WITH CHECK (identity.has_installation_scope());
CREATE POLICY installation_admin_delete ON identity.installation_admin FOR DELETE
    USING (identity.has_installation_scope());

CREATE POLICY invitation_access ON identity.invitation
    USING (
        identity.has_installation_scope()
        OR organization_id = identity.current_organization_id()
    )
    WITH CHECK (
        identity.has_installation_scope()
        OR organization_id = identity.current_organization_id()
    );

CREATE POLICY email_change_access ON identity.email_change_request
    USING (
        identity.has_installation_scope()
        OR user_id = identity.current_user_id()
        OR EXISTS (
            SELECT 1 FROM identity.membership m
            WHERE m.user_id = email_change_request.user_id
              AND m.organization_id = identity.current_organization_id()
        )
    );

-- Privilégios do papel da aplicação. Sem DELETE, exceto para retirar o escopo de
-- Administrador da instalação (a tabela só guarda o escopo vigente; o histórico fica no
-- Audit Trail).
GRANT USAGE ON SCHEMA identity TO cap_app;
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA identity TO cap_app;
GRANT DELETE ON identity.installation_admin TO cap_app;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA identity TO cap_app;
"""

DOWNGRADE = r"""
DROP SCHEMA identity CASCADE;
"""


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
