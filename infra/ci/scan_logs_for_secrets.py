"""Varre logs da execução E2E em busca de segredos (T071; CS-007).

Uso: python infra/ci/scan_logs_for_secrets.py <arquivo> [<arquivo> ...]
Sai com código 1 se encontrar algo; mostra só o arquivo, a linha e o tipo (nunca o valor).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

PATTERNS = {
    "token JWT": re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),
    "cabeçalho Authorization": re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._-]{16,}"),
    "senha dos testes E2E": re.compile(
        r"Senha-(Forte|Inicial|Convidada|Org|Teste)-[A-Za-z0-9_-]+"
    ),
    "campo de senha": re.compile(
        r"(?i)[\"']?password[\"']?\s*[:=]\s*[\"']?[^\s\"',}*\[]{4,}"
    ),
    "link de convite": re.compile(r"/convites/[A-Za-z0-9_-]{20,}"),
    "link de troca de e-mail": re.compile(r"/confirmar-email/[A-Za-z0-9_-]{20,}"),
    "código no e-mail": re.compile(r"(?i)c[óo]digo[^0-9\n]{0,40}\b\d{6}\b"),
}


def scan(paths: list[Path]) -> list[str]:
    findings = []
    for path in paths:
        for number, line in enumerate(
            path.read_text(encoding="utf-8", errors="replace").splitlines(), 1
        ):
            for kind, pattern in PATTERNS.items():
                if pattern.search(line):
                    findings.append(f"{path}:{number}: {kind}")
    return findings


def main(argv: list[str]) -> int:
    if not argv:
        print("Informe os arquivos de log.", file=sys.stderr)
        return 2
    findings = scan([Path(p) for p in argv])
    for finding in findings:
        print(finding)
    print(
        f"{len(findings)} ocorrência(s) de segredo nos logs."
        if findings
        else "Nenhum segredo nos logs."
    )
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
