"""Ambiente de integração: o compose local (infra/compose) com URLs e credenciais."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

import httpx

REPO_ROOT = Path(__file__).resolve().parents[4]
COMPOSE_DIR = REPO_ROOT / "infra" / "compose"


@dataclass(frozen=True)
class Stack:
    keycloak_url: str
    realm: str
    mailpit_url: str
    secrets: dict[str, str]

    @property
    def realm_url(self) -> str:
        return f"{self.keycloak_url}/realms/{self.realm}"


def load_env() -> dict[str, str]:
    """Lê infra/compose/.env (gerado por init_env.py)."""
    env_file = COMPOSE_DIR / ".env"
    if not env_file.exists():
        raise RuntimeError(f"{env_file} não existe; rode infra/compose/init_env.py")
    values: dict[str, str] = {}
    for line in env_file.read_text(encoding="utf-8").splitlines():
        key, _, value = line.partition("=")
        if key:
            values[key] = value
    return values


def is_ready(stack: Stack) -> bool:
    try:
        well_known = httpx.get(f"{stack.realm_url}/.well-known/openid-configuration", timeout=2)
        mailpit = httpx.get(f"{stack.mailpit_url}/readyz", timeout=2)
    except httpx.HTTPError:
        return False
    return well_known.status_code == 200 and mailpit.status_code == 200


def wait_until_ready(stack: Stack, timeout_s: float = 300) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if is_ready(stack):
            return
        time.sleep(2)
    raise TimeoutError("Ambiente de integração não ficou pronto")
