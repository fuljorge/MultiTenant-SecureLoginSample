"""Ambiente do Alembic. Conecta com o papel `cap_migrator`, dono dos schemas."""

import os

from alembic import context
from sqlalchemy import create_engine, pool

config = context.config


def _url() -> str:
    url = config.get_main_option("sqlalchemy.url") or os.environ.get("CAP_MIGRATOR_DATABASE_URL")
    if not url:
        raise RuntimeError("Defina CAP_MIGRATOR_DATABASE_URL para rodar as migrações")
    return url


def run_migrations_online() -> None:
    engine = create_engine(_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, transaction_per_migration=True)
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
