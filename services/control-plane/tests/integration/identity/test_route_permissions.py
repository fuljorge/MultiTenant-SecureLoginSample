"""Matriz de perfis aplicada no servidor, rota a rota (T055, T083; RF-014, RF-024, RF-028).

Cada perfil e o Super Administrador chamam cada rota protegida por permissão.
Sem permissão: `403` e `access.denied` no Audit Trail. Com permissão: a proteção deixa
passar (`404`/`422` são esperados, porque os ids não existem e não há corpo; assim os
pedidos não têm efeito colateral).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from cap_control_plane.core.db import DbContext, transaction
from cap_control_plane.identity.permissions import Profile, effective_permissions
from tests.support.keycloak import KeycloakAdmin
from tests.support.people import (
    Person,
    create_organization,
    create_person,
    csrf_headers,
    logged_in,
)
from tests.support.routes import RouteInfo, api_routes
from tests.support.stack import Stack

SUPER_ADMIN = "super_admin"
PRINCIPALS = [*(p.value for p in Profile), SUPER_ADMIN]


@pytest.fixture(scope="module")
def clients(
    app: FastAPI, stack: Stack, engine: Engine, kc: KeycloakAdmin
) -> Iterator[dict[str, tuple[Person, TestClient]]]:
    """Uma pessoa logada por perfil, todas na mesma organização."""
    org = create_organization(engine)
    people = {
        name: create_person(
            engine,
            kc,
            organizations={} if name == SUPER_ADMIN else {org: name},
            super_admin=name == SUPER_ADMIN,
        )
        for name in PRINCIPALS
    }
    opened: dict[str, tuple[Person, TestClient]] = {}
    contexts = []
    try:
        for name, person in people.items():
            context = logged_in(app, stack, person)
            contexts.append(context)
            opened[name] = (person, context.__enter__())
        yield opened
    finally:
        for context in contexts:
            context.__exit__(None, None, None)
        for person in people.values():
            kc.delete_user(str(person.id))


def _call(client: TestClient, route: RouteInfo):  # type: ignore[no-untyped-def]
    return client.request(
        route.method, route.sample_path(), headers=csrf_headers(client), follow_redirects=False
    )


def _denials(engine: Engine, user_id: uuid.UUID) -> list[tuple[str, str]]:
    with transaction(engine, DbContext.system()) as s:
        rows = s.execute(
            text(
                "SELECT target_id, details->>'method' FROM audit.audit_event"
                " WHERE actor_user_id = :id AND event_type = 'access.denied'"
            ),
            {"id": user_id},
        ).all()
    return [(target, method) for target, method in rows]


def _permission_routes(app: FastAPI) -> list[RouteInfo]:
    return [r for r in api_routes(app) if r.permissions]


@pytest.mark.parametrize("principal", PRINCIPALS)
def test_cada_perfil_recebe_403_e_auditoria_exatamente_onde_nao_tem_permissao(
    principal: str,
    clients: dict[str, tuple[Person, TestClient]],
    app: FastAPI,
    engine: Engine,
) -> None:
    person, client = clients[principal]
    granted = effective_permissions(
        None if principal == SUPER_ADMIN else Profile(principal),
        is_super_admin=principal == SUPER_ADMIN,
    )
    routes = _permission_routes(app)
    assert routes, "nenhuma rota protegida por permissão encontrada"

    wrong, expected_denials = [], []
    for route in routes:
        response = _call(client, route)
        allowed = bool(route.permissions & granted)
        if allowed and response.status_code in (401, 403):
            wrong.append(f"{route.method} {route.path}: {response.status_code}, esperado acesso")
        if not allowed:
            if response.status_code != 403:
                wrong.append(f"{route.method} {route.path}: {response.status_code}, esperado 403")
            expected_denials.append((route.path, route.method))

    assert wrong == []
    assert sorted(_denials(engine, person.id)) == sorted(expected_denials)


def test_sem_sessao_toda_rota_nao_publica_responde_401(app: FastAPI) -> None:
    """RF-024: nada além das rotas públicas responde a quem não está logado."""
    with TestClient(app, base_url="https://testserver") as anonymous:
        wrong = [
            f"{route.method} {route.path}: {status}"
            for route in api_routes(app)
            if not route.public and (status := _call(anonymous, route).status_code) != 401
        ]

    assert wrong == []


def test_rotas_so_de_sessao_atendem_qualquer_perfil(
    clients: dict[str, tuple[Person, TestClient]], app: FastAPI
) -> None:
    """Ex.: /me e as próprias sessões. O logout fica de fora para não encerrar a sessão."""
    routes = [r for r in api_routes(app) if r.session_only and r.path != "/api/v1/auth/logout"]
    wrong = [
        f"{principal} {route.method} {route.path}: {status}"
        for principal, (_, client) in clients.items()
        for route in routes
        if (status := _call(client, route).status_code) in (401, 403)
    ]

    assert wrong == []
