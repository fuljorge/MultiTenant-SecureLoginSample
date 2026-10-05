"""Acesso ao PostgreSQL com contexto de isolamento por transação (T019; Princípio IV).

Toda transação define, só para si, quem está agindo e em qual organização. As políticas
RLS do schema `identity` (e das próximas features) usam esses valores. A aplicação
conecta com o papel `cap_app`, que não é dono das tabelas e não ignora RLS.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session

from cap_control_plane.core.settings import Settings


@dataclass(frozen=True)
class DbContext:
    """Quem age na transação. Vazio = nada visível (negação por padrão)."""

    user_id: uuid.UUID | None = None
    organization_id: uuid.UUID | None = None
    # Só para quem está em identity.super_admin; o banco confere a linha (migração 0004).
    is_super_admin: bool = False
    # Fluxos internos acionados pelo código, nunca pelo usuário: aceite de convite por
    # token, eventos do Keycloak, CLI de operação.
    is_system: bool = False

    @classmethod
    def system(cls) -> DbContext:
        return cls(is_system=True)


def create_db_engine(settings: Settings) -> Engine:
    return create_engine(
        settings.database_url.get_secret_value(),
        pool_pre_ping=True,
        # Valores de parâmetros (e-mails, hashes) não vão para os logs do SQLAlchemy.
        hide_parameters=True,
    )


_SET_CONTEXT = text(
    "SELECT set_config('app.user_id', :user_id, true),"
    " set_config('app.organization_id', :organization_id, true),"
    " set_config('app.is_super_admin', :is_super_admin, true),"
    " set_config('app.is_system', :is_system, true)"
)


@contextmanager
def transaction(engine: Engine, ctx: DbContext) -> Iterator[Session]:
    """Abre uma transação com o contexto aplicado; confirma ao sair sem erro."""
    with Session(engine) as session, session.begin():
        session.execute(
            _SET_CONTEXT,
            {
                "user_id": str(ctx.user_id) if ctx.user_id else "",
                "organization_id": str(ctx.organization_id) if ctx.organization_id else "",
                "is_super_admin": "true" if ctx.is_super_admin else "false",
                "is_system": "true" if ctx.is_system else "false",
            },
        )
        yield session
