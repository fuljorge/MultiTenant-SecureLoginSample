"""Dependência require() (T027; RF-014)."""

from __future__ import annotations

import uuid
from typing import Annotated

import pytest
from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.testclient import TestClient

from cap_control_plane.identity.authz import Principal, require, route_template
from cap_control_plane.identity.permissions import Permission, Profile, effective_permissions


def _app(principal: Principal | None) -> tuple[FastAPI, list[tuple[str, Permission]]]:
    denied: list[tuple[str, Permission]] = []
    app = FastAPI()

    def record(request: Request, p: Principal, permission: Permission) -> None:
        denied.append((request.scope["route"].path, permission))

    app.state.record_access_denied = record

    @app.middleware("http")
    async def set_principal(request: Request, call_next):  # type: ignore[no-untyped-def]
        request.state.principal = principal
        return await call_next(request)

    @app.get("/users/{user_id}")
    def read_user(
        user_id: str, p: Annotated[Principal, Depends(require(Permission.USERS_READ))]
    ) -> dict[str, str]:
        return {"by": str(p.user_id)}

    return app, denied


def _principal(profile: Profile) -> Principal:
    return Principal(
        user_id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        profile=profile,
        is_super_admin=False,
        permissions=effective_permissions(profile, is_super_admin=False),
    )


def test_sem_sessao_responde_401() -> None:
    app, denied = _app(None)

    response = TestClient(app).get("/users/abc")

    assert response.status_code == 401
    assert denied == []


def test_com_permissao_passa() -> None:
    principal = _principal(Profile.ADMINISTRATOR)
    app, denied = _app(principal)

    response = TestClient(app).get("/users/abc")

    assert response.status_code == 200
    assert response.json() == {"by": str(principal.user_id)}
    assert denied == []


@pytest.mark.parametrize("profile", [Profile.BUSINESS_ANALYST, Profile.FINANCIAL_ADMIN])
def test_sem_permissao_responde_403_e_registra_sem_o_id(profile: Profile) -> None:
    app, denied = _app(_principal(profile))

    response = TestClient(app).get("/users/abc")

    assert response.status_code == 403
    assert denied == [("/users/{user_id}", Permission.USERS_READ)]


def test_dependencia_declara_a_permissao_exigida() -> None:
    dependency = require(Permission.AUDIT_READ)

    assert dependency.required_permissions == {Permission.AUDIT_READ}  # type: ignore[attr-defined]


@pytest.mark.parametrize("url", ["/api/v1/users/abc/disable", "/api/v1/users/abc/disable/"])
def test_rota_registrada_e_o_modelo_completo_sem_valores(url: str) -> None:
    """Em router incluído, `scope["route"].path` é relativo; o log usa o caminho completo."""
    router = APIRouter(prefix="/users")

    @router.post("/{user_id}/disable")
    def disable(user_id: str, request: Request) -> str:
        return route_template(request)

    app = FastAPI()
    app.include_router(router, prefix="/api/v1")

    response = TestClient(app).post(url, follow_redirects=True)

    assert response.json() == "/api/v1/users/{user_id}/disable"
