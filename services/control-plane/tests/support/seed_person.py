"""Cria uma pessoa de teste no ambiente local e imprime os dados em JSON.

Usado pelos testes E2E (tests/e2e). Só para o ambiente local: exige o compose no ar e
`CAP_ENV_FILE` apontando para infra/compose/.env.control-plane.

    uv run python -m tests.support.seed_person --profile agent_designer
    uv run python -m tests.support.seed_person --invite   # sem senha; recebe o link de ativação
    uv run python -m tests.support.seed_person --organization <id>   # em organização existente
    uv run python -m tests.support.seed_person --super-admin   # Super Administrador
"""

from __future__ import annotations

import argparse
import json
import secrets
import sys
import uuid

from sqlalchemy import text

from cap_control_plane.core.db import DbContext, create_db_engine, transaction
from cap_control_plane.core.settings import get_settings
from cap_control_plane.services import Services
from tests.support.keycloak import KeycloakAdmin
from tests.support.people import create_organization, create_person
from tests.support.stack import Stack, load_env


def _invite(services: Services, organization: uuid.UUID, profile: str) -> dict[str, str]:
    """Pessoa convidada: sem senha, vínculo pendente e e-mail de ativação (como no bootstrap)."""
    email = f"convite-{secrets.token_hex(5)}@exemplo.com.br"
    name = f"Convidada {email[8:13]}"
    user_id = uuid.UUID(services.keycloak_admin.create_user(email))
    with transaction(services.engine, DbContext.system()) as s:
        s.execute(
            text(
                "INSERT INTO identity.user_account (id, email, name, status)"
                " VALUES (:id, :email, :name, 'invited')"
            ),
            {"id": user_id, "email": email, "name": name},
        )
        s.execute(
            text(
                "INSERT INTO identity.membership (organization_id, user_id, profile, status)"
                " VALUES (:org, :user, :profile, 'pending')"
            ),
            {"org": organization, "user": user_id, "profile": profile},
        )
    services.keycloak_admin.send_activation_email(str(user_id), lifespan_seconds=3600)
    return {"id": str(user_id), "email": email, "name": name}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", default="agent_designer")
    parser.add_argument("--invite", action="store_true")
    parser.add_argument("--organization", type=uuid.UUID, help="padrão: cria uma organização")
    parser.add_argument("--super-admin", action="store_true", help="sem organização (RF-028)")
    parser.add_argument(
        "--second-profile", help="também em uma segunda organização, com este perfil"
    )
    args = parser.parse_args()

    settings = get_settings()
    engine = create_db_engine(settings)
    if args.super_admin:
        stack = Stack("http://localhost:8080/idp", "cap", "http://localhost:8025", load_env())
        person = create_person(engine, KeycloakAdmin(stack), super_admin=True)
        json.dump(
            {"id": str(person.id), "email": person.email, "password": person.password,
             "name": person.name, "organizationId": None},
            sys.stdout,
        )  # fmt: skip
        return
    organization = args.organization or create_organization(engine)
    if args.invite:
        data = _invite(Services.from_settings(settings), organization, args.profile)
    else:
        stack = Stack("http://localhost:8080/idp", "cap", "http://localhost:8025", load_env())
        memberships = {organization: args.profile}
        if args.second_profile:
            memberships[create_organization(engine)] = args.second_profile
        person = create_person(engine, KeycloakAdmin(stack), organizations=memberships)
        data = {
            "id": str(person.id),
            "email": person.email,
            "password": person.password,
            "name": person.name,
        }
    json.dump({**data, "organizationId": str(organization)}, sys.stdout)


if __name__ == "__main__":
    main()
