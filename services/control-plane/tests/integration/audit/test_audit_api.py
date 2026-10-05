"""Consulta e exportação do Audit Trail (T065; US6; RF-021 a RF-023).

O escopo de quem consulta vem do RLS (migrações 0002, 0004 e 0005): o Administrador vê
os eventos da organização ativa (inclusive as ações do Super Administrador sobre ela) e
os eventos de identidade das pessoas dela; o Super Administrador vê só os da gestão da
instalação e os dos Super Administradores.
"""

from __future__ import annotations

import csv
import io
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from cap_control_plane.audit.chain import AuditEvent
from cap_control_plane.audit.writer import Origin, append_event
from cap_control_plane.core.db import DbContext, transaction
from tests.support.keycloak import KeycloakAdmin
from tests.support.people import (
    Person,
    create_organization,
    create_person,
    csrf_headers,
    logged_in,
)
from tests.support.stack import Stack


@dataclass(frozen=True)
class Scenario:
    org: uuid.UUID
    other_org: uuid.UUID
    admin: Person
    member: Person
    super_admin: Person
    seqs: dict[str, int]


def _append(engine: Engine, **fields: object) -> int:
    defaults: dict[str, object] = {
        "organization_id": None, "actor_kind": "user", "target_type": "user",
        "result": "success",
    }  # fmt: skip
    with transaction(engine, DbContext.system()) as s:
        return append_event(
            s,
            AuditEvent.now(**{**defaults, **fields}),
            Origin(source_ip="203.0.113.7", user_agent="pytest"),
        )


@pytest.fixture(scope="module")
def scenario(engine: Engine, kc: KeycloakAdmin) -> Iterator[Scenario]:
    org, other_org = create_organization(engine), create_organization(engine)
    admin = create_person(engine, kc, organizations={org: "administrator"})
    member = create_person(engine, kc, organizations={org: "supervisor"})
    outsider = create_person(engine, kc, organizations={other_org: "supervisor"})
    super_admin = create_person(engine, kc, super_admin=True)
    seqs = {
        # Login de quem é da organização: vem do Keycloak, sem organização.
        "member_login": _append(
            engine, actor_user_id=member.id, event_type="auth.login",
            target_id=str(member.id), source="keycloak",
            source_event_id=str(uuid.uuid4()),
        ),
        "profile_changed": _append(
            engine, organization_id=org, actor_user_id=admin.id,
            event_type="user.profile_changed", target_id=str(member.id),
            result="success", details={"from": "supervisor", "to": "developer"},
        ),
        "denied": _append(
            engine, organization_id=org, actor_user_id=member.id,
            event_type="access.denied", target_type="route", target_id="/api/v1/users",
            result="denied", details={"permission": "users:read", "method": "GET"},
        ),
        "super_on_org": _append(
            engine, organization_id=org, actor_user_id=super_admin.id,
            event_type="org.renamed", target_type="organization", target_id=str(org),
            details={"name": "Nova"}, installation_scope=True,
        ),
        "super_login": _append(
            engine, actor_user_id=super_admin.id, event_type="auth.login",
            target_id=str(super_admin.id), source="keycloak",
            source_event_id=str(uuid.uuid4()),
        ),
        "other_org": _append(
            engine, organization_id=other_org, actor_user_id=outsider.id,
            event_type="user.profile_changed", target_id=str(outsider.id),
        ),
        "outsider_login": _append(
            engine, actor_user_id=outsider.id, event_type="auth.login",
            target_id=str(outsider.id), source="keycloak",
            source_event_id=str(uuid.uuid4()),
        ),
    }  # fmt: skip
    yield Scenario(org, other_org, admin, member, super_admin, seqs)
    for p in (admin, member, outsider, super_admin):
        kc.delete_user(str(p.id))


@pytest.fixture(scope="module")
def admin_client(app: FastAPI, stack: Stack, scenario: Scenario) -> Iterator[TestClient]:
    with logged_in(app, stack, scenario.admin) as client:
        yield client


@pytest.fixture(scope="module")
def super_client(app: FastAPI, stack: Stack, scenario: Scenario) -> Iterator[TestClient]:
    with logged_in(app, stack, scenario.super_admin) as client:
        yield client


def _seqs(client: TestClient, **params: object) -> set[int]:
    response = client.get("/api/v1/audit-events", params={"limit": 200, **params})
    assert response.status_code == 200, response.text
    return {e["seq"] for e in response.json()}


def test_administrador_ve_a_organizacao_e_as_pessoas_dela(
    admin_client: TestClient, scenario: Scenario
) -> None:
    seen = _seqs(admin_client)
    s = scenario.seqs

    assert {s["member_login"], s["profile_changed"], s["denied"], s["super_on_org"]} <= seen
    assert not {s["super_login"], s["other_org"], s["outsider_login"]} & seen


def test_super_administrador_ve_so_a_gestao_da_instalacao(
    super_client: TestClient, scenario: Scenario
) -> None:
    seen = _seqs(super_client)
    s = scenario.seqs

    assert {s["super_on_org"], s["super_login"]} <= seen
    assert not {
        s["member_login"], s["profile_changed"], s["denied"], s["other_org"],
        s["outsider_login"],
    } & seen  # fmt: skip


def test_registro_traz_quem_o_que_quando_de_onde_e_resultado(
    admin_client: TestClient, scenario: Scenario
) -> None:
    """RF-022."""
    events = admin_client.get(
        "/api/v1/audit-events", params={"event_type": "user.profile_changed"}
    ).json()
    event = next(e for e in events if e["seq"] == scenario.seqs["profile_changed"])

    assert event["actor_user_id"] == str(scenario.admin.id)
    assert event["actor_name"] == scenario.admin.name
    assert event["target_name"] == scenario.member.name
    assert event["organization_id"] == str(scenario.org)
    assert event["result"] == "success"
    assert event["source_ip"] == "203.0.113.7"
    assert event["occurred_at"]


def test_filtros_por_pessoa_tipo_resultado_e_periodo(
    admin_client: TestClient, scenario: Scenario
) -> None:
    s = scenario.seqs
    by_person = _seqs(admin_client, user_id=str(scenario.member.id))
    by_name = _seqs(admin_client, q=scenario.member.email)
    by_type = _seqs(admin_client, event_type="access.denied")
    by_result = _seqs(admin_client, result="denied")
    future = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    past = (datetime.now(UTC) - timedelta(days=1)).isoformat()

    assert {s["member_login"], s["profile_changed"], s["denied"]} <= by_person
    assert s["super_on_org"] not in by_person
    assert {s["member_login"], s["denied"]} <= by_name
    assert s["denied"] in by_type and s["profile_changed"] not in by_type
    assert s["denied"] in by_result and s["member_login"] not in by_result
    assert _seqs(admin_client, date_from=future) == set()
    assert s["denied"] in _seqs(admin_client, date_from=past, date_to=future)


def test_exportacao_gera_csv_e_fica_registrada(
    admin_client: TestClient, engine: Engine, scenario: Scenario
) -> None:
    response = admin_client.post(
        "/api/v1/audit-events/export",
        json={"event_type": "access.denied"},
        headers=csrf_headers(admin_client),
    )

    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers["content-disposition"]
    rows = list(csv.DictReader(io.StringIO(response.text)))
    assert str(scenario.seqs["denied"]) in {r["seq"] for r in rows}
    assert {r["event_type"] for r in rows} == {"access.denied"}
    with transaction(engine, DbContext.system()) as s:
        exported = s.execute(
            text(
                "SELECT organization_id, details FROM audit.audit_event"
                " WHERE event_type = 'audit.exported' AND actor_user_id = :u"
            ),
            {"u": scenario.admin.id},
        ).one()
    assert exported.organization_id == scenario.org
    assert exported.details["filters"] == {"event_type": "access.denied"}
    assert exported.details["rows"] == len(rows)


def test_quem_nao_tem_permissao_nao_consulta(
    app: FastAPI, stack: Stack, scenario: Scenario
) -> None:
    with logged_in(app, stack, scenario.member) as client:
        assert client.get("/api/v1/audit-events").status_code == 403
