"""Banco temporário para testes: criado do zero, migrado e apagado ao final."""

from __future__ import annotations

import secrets
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import psycopg
from alembic import command
from alembic.config import Config
from psycopg import sql

from tests.support.stack import Stack

ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"


@dataclass(frozen=True)
class MigratedDatabase:
    name: str
    app_url: str
    migrator_url: str


@contextmanager
def temporary_database(stack: Stack) -> Iterator[MigratedDatabase]:
    s = stack.secrets
    name = f"cap_test_{secrets.token_hex(4)}"
    admin_dsn = f"postgresql://postgres:{s['POSTGRES_PASSWORD']}@127.0.0.1:5432/postgres"
    with psycopg.connect(admin_dsn, autocommit=True) as conn:
        conn.execute(sql.SQL("CREATE DATABASE {} OWNER cap_migrator").format(sql.Identifier(name)))
        conn.execute(sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(sql.Identifier(name)))
        conn.execute(
            sql.SQL("GRANT CONNECT ON DATABASE {} TO cap_app").format(sql.Identifier(name))
        )
    try:
        yield MigratedDatabase(
            name=name,
            app_url=f"postgresql+psycopg://cap_app:{s['CAP_DB_PASSWORD']}@127.0.0.1:5432/{name}",
            migrator_url=(
                f"postgresql+psycopg://cap_migrator:{s['CAP_MIGRATOR_PASSWORD']}"
                f"@127.0.0.1:5432/{name}"
            ),
        )
    finally:
        with psycopg.connect(admin_dsn, autocommit=True) as conn:
            conn.execute(
                sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name))
            )


def run_migrations(migrator_url: str, revision: str = "head") -> None:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("sqlalchemy.url", migrator_url)
    command.upgrade(config, revision)
