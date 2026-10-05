#!/bin/sh
# Cria os bancos e papéis na primeira inicialização do PostgreSQL local.
# - cap_migrator: dono do schema, usado só pelas migrações (Alembic).
# - cap_app: usado pela aplicação; sem BYPASSRLS e sem ser dono das tabelas (data-model, RLS).
# - keycloak: banco separado, acessado apenas pelo Keycloak.
set -eu

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" \
  -v cap_db_password="$CAP_DB_PASSWORD" \
  -v cap_migrator_password="$CAP_MIGRATOR_PASSWORD" \
  -v keycloak_db_password="$KEYCLOAK_DB_PASSWORD" <<'SQL'
CREATE ROLE cap_migrator LOGIN PASSWORD :'cap_migrator_password';
CREATE ROLE cap_app LOGIN PASSWORD :'cap_db_password' NOBYPASSRLS;
CREATE DATABASE cap OWNER cap_migrator;
REVOKE ALL ON DATABASE cap FROM PUBLIC;
GRANT CONNECT ON DATABASE cap TO cap_app;

CREATE ROLE keycloak LOGIN PASSWORD :'keycloak_db_password';
CREATE DATABASE keycloak OWNER keycloak;
REVOKE ALL ON DATABASE keycloak FROM PUBLIC;
SQL
