"""Documentação interativa desligada por padrão (OWASP ASVS 4.3.2; T076)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from cap_control_plane.main import create_app


def test_docs_e_openapi_nao_sao_expostos_por_padrao() -> None:
    app = create_app()
    client = TestClient(app)

    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(path).status_code == 404, path


def test_cliente_typescript_continua_gerado_sem_a_rota() -> None:
    schema = create_app().openapi()

    assert "/api/v1/me" in schema["paths"]
