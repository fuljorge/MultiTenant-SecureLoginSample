"""Configuração de segurança da instalação (T053; RF-007, RF-010; plano §4.8).

O Keycloak é a fonte de verdade: política de senha, tempos de sessão, bloqueio, código por
e-mail e validade dos links ficam no realm. Os limites mínimos abaixo não podem ser
afrouxados (contracts/identity-api.md). O Control Plane lê os tempos de sessão e a
validade dos convites daqui, com cache curto, para aplicar os mesmos valores.
"""

from __future__ import annotations

import re
import threading
import time

from pydantic import BaseModel, Field

from cap_control_plane.core.settings import Settings
from cap_control_plane.identity.keycloak_admin import KeycloakAdminClient

LEAKED_PASSWORDS_FILE = "pwdb-top-1000000.txt"
EMAIL_CODE_FLOW = "cap-browser"
EMAIL_CODE_PROVIDER = "email-authenticator"
CACHE_SECONDS = 60


class SecuritySettings(BaseModel):
    """Valores ajustáveis pelo Super Administrador, com os limites mínimos."""

    password_min_length: int = Field(ge=12, le=128)
    password_history: int = Field(ge=0, le=24)
    session_idle_minutes: int = Field(ge=5, le=480)
    session_max_hours: int = Field(ge=1, le=24)
    lockout_failures: int = Field(ge=3, le=10)
    lockout_minutes: int = Field(ge=1, le=1440)
    code_length: int = Field(ge=6, le=10)
    code_valid_minutes: int = Field(ge=1, le=15)
    code_resend_minutes: int = Field(ge=1, le=60)
    invitation_valid_hours: int = Field(ge=1, le=168)
    recovery_link_minutes: int = Field(ge=5, le=120)


def _policy(min_length: int, history: int) -> str:
    # Fixos: teto de 128 caracteres (OWASP ASVS 2.1.2, contra abuso do hash), lista de senhas
    # vazadas (research R5) e as regras de e-mail/usuário.
    parts = [
        f"length({min_length})",
        "maxLength(128)",
        f"passwordBlacklist({LEAKED_PASSWORDS_FILE})",
    ]
    if history:
        parts.append(f"passwordHistory({history})")
    parts += ["notEmail", "notUsername"]
    return " and ".join(parts)


def _policy_value(policy: str, name: str, default: int) -> int:
    match = re.search(rf"{name}\((\d+)\)", policy or "")
    return int(match.group(1)) if match else default


class SecuritySettingsService:
    def __init__(self, keycloak: KeycloakAdminClient, settings: Settings) -> None:
        self._kc = keycloak
        self._settings = settings
        self._lock = threading.Lock()
        self._cached: SecuritySettings | None = None
        self._cached_at = 0.0

    def _email_code_config(self) -> tuple[str, dict[str, str]]:
        executions = self._kc.flow_executions(EMAIL_CODE_FLOW)
        step = next(e for e in executions if e.get("providerId") == EMAIL_CODE_PROVIDER)
        config_id = str(step["authenticationConfig"])
        return config_id, self._kc.authenticator_config(config_id)

    def read(self) -> SecuritySettings:
        realm = self._kc.get_realm()
        _, code = self._email_code_config()
        policy = str(realm.get("passwordPolicy", ""))
        current = SecuritySettings(
            password_min_length=_policy_value(policy, "length", 12),
            password_history=_policy_value(policy, "passwordHistory", 0),
            session_idle_minutes=int(realm["ssoSessionIdleTimeout"]) // 60,
            session_max_hours=int(realm["ssoSessionMaxLifespan"]) // 3600,
            lockout_failures=int(realm["failureFactor"]),
            lockout_minutes=int(realm["waitIncrementSeconds"]) // 60,
            code_length=int(code.get("length", 6)),
            code_valid_minutes=int(code.get("ttl", 600)) // 60,
            code_resend_minutes=int(code.get("resendCooldown", 300)) // 60,
            invitation_valid_hours=int(realm["actionTokenGeneratedByAdminLifespan"]) // 3600,
            recovery_link_minutes=int(realm["actionTokenGeneratedByUserLifespan"]) // 60,
        )
        with self._lock:
            self._cached, self._cached_at = current, time.monotonic()
        return current

    def update(self, new: SecuritySettings) -> list[str]:
        """Aplica no Keycloak e devolve os campos alterados (para o Audit Trail)."""
        old = self.read()
        changed = [k for k, v in new.model_dump().items() if getattr(old, k) != v]
        if not changed:
            return []
        lockout = new.lockout_minutes * 60
        self._kc.update_realm(
            {
                "passwordPolicy": _policy(new.password_min_length, new.password_history),
                "ssoSessionIdleTimeout": new.session_idle_minutes * 60,
                "ssoSessionMaxLifespan": new.session_max_hours * 3600,
                "failureFactor": new.lockout_failures,
                "waitIncrementSeconds": lockout,
                "maxFailureWaitSeconds": lockout,
                "actionTokenGeneratedByAdminLifespan": new.invitation_valid_hours * 3600,
                "actionTokenGeneratedByUserLifespan": new.recovery_link_minutes * 60,
            }
        )
        config_id, code = self._email_code_config()
        self._kc.update_authenticator_config(
            config_id,
            {
                **code,
                "length": str(new.code_length),
                "ttl": str(new.code_valid_minutes * 60),
                "resendCooldown": str(new.code_resend_minutes * 60),
                "maxAttempts": str(new.lockout_failures),
                # Nunca ligar: escreve o código no log (research R1).
                "simulationMode": "false",
            },
        )
        with self._lock:
            self._cached, self._cached_at = new, time.monotonic()
        return changed

    def _current(self) -> SecuritySettings | None:
        with self._lock:
            if self._cached and time.monotonic() - self._cached_at < CACHE_SECONDS:
                return self._cached
        try:
            return self.read()
        except Exception:  # Keycloak indisponível: usa os padrões da configuração.
            return None

    def session_limits(self) -> tuple[int, int]:
        current = self._current()
        if current is None:
            return self._settings.session_idle_seconds, self._settings.session_max_seconds
        return current.session_idle_minutes * 60, current.session_max_hours * 3600

    def invitation_valid_hours(self) -> int:
        current = self._current()
        return current.invitation_valid_hours if current else self._settings.invitation_valid_hours
