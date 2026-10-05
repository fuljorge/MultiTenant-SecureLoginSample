"""Script de varredura de logs do CI (T071; CS-007)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from tests.support.stack import REPO_ROOT

_spec = importlib.util.spec_from_file_location(
    "scan_logs", REPO_ROOT / "infra" / "ci" / "scan_logs_for_secrets.py"
)
assert _spec and _spec.loader
scan_logs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(scan_logs)


@pytest.mark.parametrize(
    "line",
    [
        "token eyJhbGciOiJSUzI1NiIs.eyJzdWIiOiIxMjM0NTY3ODkw.assinatura",
        "Authorization: Bearer abcdefghijklmnopqrstuvwxyz",
        "login com Senha-Forte-abc123XYZ",
        '{"password": "minha-senha-secreta"}',
        "abra http://localhost:3000/convites/AbCdEfGhIjKlMnOpQrStUvWxYz012345",
        "link /confirmar-email/AbCdEfGhIjKlMnOpQrStUvWxYz012345",
        "Seu código de acesso: 482913",
    ],
)
def test_detecta_segredo(tmp_path: Path, line: str) -> None:
    log = tmp_path / "app.log"
    log.write_text(f"ok\n{line}\n", encoding="utf-8")

    assert scan_logs.scan([log]) != []
    assert scan_logs.main([str(log)]) == 1


def test_logs_limpos_passam(tmp_path: Path) -> None:
    log = tmp_path / "app.log"
    log.write_text(
        '{"timestamp": "2026-10-04T15:02:58.759444+00:00", "level": "INFO",'
        ' "message": "HTTP Request: GET [LINK] \\"HTTP/1.1 200 OK\\""}\n'
        '{"message": "Falha de login", "password": "[REDACTED]"}\n',
        encoding="utf-8",
    )

    assert scan_logs.scan([log]) == []
    assert scan_logs.main([str(log)]) == 0
