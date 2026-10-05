"""Redação de dados sensíveis nos logs (T015; constituição, Princípios V e X; CS-007)."""

import json
import logging

import pytest

from cap_control_plane.core.logging import JsonFormatter, redact_text


def _format(message: str, *args: object, **extra: object) -> dict[str, object]:
    record = logging.LogRecord("cap.test", logging.INFO, __file__, 1, message, args, None)
    for key, value in extra.items():
        setattr(record, key, value)
    return dict(json.loads(JsonFormatter().format(record)))


@pytest.mark.parametrize(
    ("text", "secret"),
    [
        ("usuário maria.silva@empresa.com.br entrou", "maria.silva@empresa.com.br"),
        ("requisição de 203.0.113.42 recusada", "203.0.113.42"),
        ("requisição de 2001:db8::1 recusada", "2001:db8::1"),
        ("requisição de fe80:0:0:0:200:f8ff:fe21:67cf recusada", "fe80:0:0:0:200:f8ff:fe21:67cf"),
        ("requisição de ::1 recusada", "::1"),
        ("Authorization: Bearer abc.def.ghi", "abc.def.ghi"),
        ("token eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.c2lnbmF0dXJh", "eyJhbGciOiJIUzI1NiJ9"),
        ("password=Senha-Forte-123 recebido", "Senha-Forte-123"),
        ("code=482913 recebido", "482913"),
        (
            "link https://cap.exemplo/convite/abcDEF123?token=xyz enviado",
            "abcDEF123",
        ),
    ],
)
def test_texto_sensivel_e_redigido(text: str, secret: str) -> None:
    assert secret not in redact_text(text)


@pytest.mark.parametrize(
    "text",
    [
        "organização criada com 3 usuários em 120 ms",
        "bloqueado até 2026-10-02T12:15:00+00:00",
        "rodou às 12:00:00 por 00:01:30",
        "id 0f8e2c7a-1b2c-4d5e-8f9a-0b1c2d3e4f5a",
    ],
)
def test_texto_comum_e_preservado(text: str) -> None:
    assert redact_text(text) == text


def test_mensagem_formatada_com_argumentos_e_redigida() -> None:
    output = _format("login de %s a partir de %s", "ana@empresa.com.br", "198.51.100.7")

    assert "ana@empresa.com.br" not in output["message"]
    assert "198.51.100.7" not in output["message"]


def test_campos_extras_sensiveis_sao_redigidos_pelo_nome() -> None:
    output = _format(
        "evento",
        password="Senha-Forte-123",
        refresh_token="abc",
        email="ana@empresa.com.br",
        source_ip="198.51.100.7",
        organization_id="org-1",
    )

    serialized = json.dumps(output)
    for secret in ("Senha-Forte-123", "abc", "ana@empresa.com.br", "198.51.100.7"):
        assert secret not in serialized
    assert output["organization_id"] == "org-1"


def test_saida_e_json_com_campos_padrao() -> None:
    output = _format("serviço iniciado")

    assert output["level"] == "INFO"
    assert output["logger"] == "cap.test"
    assert output["message"] == "serviço iniciado"
    assert "timestamp" in output


def test_campos_com_palavra_sensivel_so_por_coincidencia_sao_preservados() -> None:
    output = _format("evento", membership_id="m-1", status_code=403, description="ok")

    assert output["membership_id"] == "m-1"
    assert output["status_code"] == 403
    assert output["description"] == "ok"
