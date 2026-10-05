"""Gera infra/compose/.env com credenciais aleatórias para o ambiente local.

Nunca versione o .env (constituição, Princípio X). Rodar de novo só acrescenta as
chaves que faltam. Use --force para trocar todas (exige recriar os volumes do compose).
"""

import secrets
import sys
from pathlib import Path

ENV_FILE = Path(__file__).with_name(".env")
KEYS = [
    "POSTGRES_PASSWORD",
    "CAP_DB_PASSWORD",
    "CAP_MIGRATOR_PASSWORD",
    "KEYCLOAK_DB_PASSWORD",
    "VALKEY_PASSWORD",
    "OPENBAO_DEV_ROOT_TOKEN",
    "KEYCLOAK_BOOTSTRAP_ADMIN_PASSWORD",
    "KC_CLIENT_SECRET_CONTROL_PLANE",
    "KC_CLIENT_SECRET_ADMIN_BRIDGE",
]


def main() -> int:
    current: dict[str, str] = {}
    if ENV_FILE.exists() and "--force" not in sys.argv:
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            key, _, value = line.partition("=")
            if key:
                current[key] = value
    missing = [key for key in KEYS if key not in current]
    for key in missing:
        current[key] = secrets.token_urlsafe(32)
    ENV_FILE.write_text(
        "".join(f"{k}={v}\n" for k, v in current.items()), encoding="utf-8"
    )
    print(f"{len(missing)} credencial(is) gerada(s) em {ENV_FILE}")
    _write_control_plane_env(current)
    return 0


def _write_control_plane_env(env: dict[str, str]) -> None:
    """Configuração do Control Plane rodando na máquina, derivada do .env (sempre recriada).

    Use com `CAP_ENV_FILE=infra/compose/.env.control-plane`. Endereços em 127.0.0.1: no
    Windows o driver do PostgreSQL trava tentando IPv6 em `localhost`.
    """
    values = {
        "CAP_PUBLIC_URL": "http://localhost:3000",
        "CAP_DATABASE_URL": (
            f"postgresql+psycopg://cap_app:{env['CAP_DB_PASSWORD']}@127.0.0.1:5432/cap"
        ),
        "CAP_MIGRATOR_DATABASE_URL": (
            f"postgresql+psycopg://cap_migrator:{env['CAP_MIGRATOR_PASSWORD']}@127.0.0.1:5432/cap"
        ),
        "CAP_VALKEY_URL": f"redis://:{env['VALKEY_PASSWORD']}@127.0.0.1:6379/0",
        "CAP_KEYCLOAK_URL": "http://localhost:8080/idp",
        "CAP_OIDC_CLIENT_SECRET": env["KC_CLIENT_SECRET_CONTROL_PLANE"],
        "CAP_ADMIN_CLIENT_SECRET": env["KC_CLIENT_SECRET_ADMIN_BRIDGE"],
        "CAP_OPENBAO_URL": "http://127.0.0.1:8200",
        "CAP_OPENBAO_TOKEN": env["OPENBAO_DEV_ROOT_TOKEN"],
        "CAP_SMTP_HOST": "127.0.0.1",
        "CAP_SMTP_PORT": "1025",
        # /docs e /openapi.json no desenvolvimento (desligados por padrão; ASVS 4.3.2).
        "CAP_API_DOCS": "true",
    }
    target = ENV_FILE.with_name(".env.control-plane")
    lines = [f"{key}={value}\n" for key, value in values.items()]
    target.write_text("".join(lines), encoding="utf-8")
    print(f"Configuração do Control Plane em {target}")


if __name__ == "__main__":
    raise SystemExit(main())
