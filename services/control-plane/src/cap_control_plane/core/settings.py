"""Configuração do Control Plane, lida de variáveis de ambiente com prefixo `CAP_`.

Segredos chegam pelo ambiente: em produção, o External Secrets Operator os copia do
OpenBao (stack §3.14); no ambiente local, vêm de infra/compose/.env. O OpenBao é usado
diretamente apenas para cifra (Transit), em `core.secrets`.
"""

import os
from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CAP_", extra="ignore")

    # URL pública da instalação (Studio e API no mesmo domínio).
    public_url: str = "http://localhost:3000"

    # PostgreSQL: papel da aplicação (sem BYPASSRLS) e papel das migrações.
    database_url: SecretStr
    migrator_database_url: SecretStr | None = None

    # Valkey (sessões do BFF).
    valkey_url: SecretStr

    # Keycloak.
    keycloak_url: str = "http://localhost:8080/idp"
    keycloak_realm: str = "cap"
    oidc_client_id: str = "cap-control-plane"
    oidc_client_secret: SecretStr
    admin_client_id: str = "cap-admin-bridge"
    admin_client_secret: SecretStr

    # OpenBao Transit (cifra dos tokens de sessão).
    openbao_url: str = "http://localhost:8200"
    openbao_token: SecretStr
    openbao_transit_key: str = "cap-session"

    # E-mail (avisos do Control Plane).
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_from: str = "nao-responda@agent-studio.local"
    smtp_username: str | None = None
    smtp_password: SecretStr | None = None
    smtp_starttls: bool = False

    # Validade dos links de convite e boas-vindas (RF-010; spec, seção 8).
    invitation_valid_hours: int = 72
    # IP e navegador do Audit Trail (fora da cadeia; LGPD). Confirmar com o DPO.
    audit_origin_retention_days: int = 365

    # Sessão (RF-006; spec, seção 8).
    session_idle_seconds: int = 30 * 60
    session_max_seconds: int = 12 * 60 * 60

    # Telemetria.
    service_name: str = "cap-control-plane"
    # /docs e /openapi.json; desligado por padrão (produção).
    api_docs: bool = False

    @property
    def keycloak_realm_url(self) -> str:
        return f"{self.keycloak_url}/realms/{self.keycloak_realm}"


@lru_cache
def get_settings() -> Settings:
    """Lê o ambiente; `CAP_ENV_FILE` aponta um arquivo opcional (ambiente local)."""
    env_file = os.environ.get("CAP_ENV_FILE")
    return Settings(_env_file=env_file)  # type: ignore[call-arg]  # valores vêm do ambiente
