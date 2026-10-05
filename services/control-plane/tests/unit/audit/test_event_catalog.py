"""Catálogo de eventos de auditoria e código (T066; RF-021, CS-006).

Todo tipo do contrato (contracts/audit-events.md) é gravado em algum ponto do código, e
o código não grava tipo fora do contrato. Os campos do RF-022 são verificados pela
consulta (tests/integration/audit/test_audit_api.py).
"""

from __future__ import annotations

import re

from tests.support.stack import REPO_ROOT

CATALOG = REPO_ROOT / "specs" / "001-identity-access" / "contracts" / "audit-events.md"
SOURCES = [
    REPO_ROOT / "services" / "control-plane" / "src",
    REPO_ROOT / "services" / "control-plane" / "migrations",
]
PREFIXES = "auth|user|org|super_admin|security|access|audit|support"
# Objetos do banco no schema `audit` com o mesmo formato de nome.
DB_OBJECTS = re.compile(r"audit\.(audit_event|chain_head|keycloak_event)")

# Previstos no contrato e entregues por outra tarefa ou feature.
PENDING = {
    "audit.tamper_attempt": "A11 (alerta da observabilidade sobre o log do PostgreSQL)",
}


def _catalog() -> set[str]:
    types: set[str] = set()
    for line in CATALOG.read_text(encoding="utf-8").splitlines():
        if not line.startswith("| `"):
            continue
        first_column = line.split("|")[1]
        types.update(re.findall(r"`([a-z_]+\.[a-z_]+)`", first_column))
    return types


def _emitted() -> set[str]:
    pattern = re.compile(rf"""["']((?:{PREFIXES})\.[a-z_]+)["']""")
    found: set[str] = set()
    for root in SOURCES:
        for path in root.rglob("*.py"):
            found.update(
                name
                for name in pattern.findall(path.read_text(encoding="utf-8"))
                if not DB_OBJECTS.match(name)
            )
    return found


def test_todo_evento_do_contrato_e_gravado_pelo_codigo() -> None:
    missing = _catalog() - _emitted() - set(PENDING)

    assert missing == set()


def test_codigo_nao_grava_evento_fora_do_contrato() -> None:
    assert _emitted() - _catalog() == set()


def test_pendencias_continuam_no_contrato() -> None:
    assert set(PENDING) <= _catalog()
