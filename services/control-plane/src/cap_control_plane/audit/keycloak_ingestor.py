"""Importação dos eventos de login do Keycloak para o Audit Trail (T038; research R4).

Lê a Admin API a cada `interval` segundos a partir de um cursor persistido, grava cada
evento uma única vez (`source = keycloak`, `source_event_id` = id do evento) e executa os
efeitos ligados a ele:

- LOGIN: atualiza `last_login_at`;
- troca ou redefinição de senha: encerra as sessões da pessoa no Keycloak e no BFF e
  envia o aviso por e-mail (RF-005).

Do evento do Keycloak só entram tipo, pessoa, resultado e motivo. E-mail digitado,
`redirect_uri` e demais detalhes não são copiados (contracts/audit-events.md).
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from opentelemetry import metrics
from sqlalchemy import text

from cap_control_plane.audit.chain import AuditEvent, Result
from cap_control_plane.audit.writer import Origin, append_event
from cap_control_plane.core.db import DbContext, transaction
from cap_control_plane.core.email import password_changed
from cap_control_plane.services import Services

logger = logging.getLogger(__name__)
_meter = metrics.get_meter("cap.audit.keycloak_ingestor")
_imported = _meter.create_counter("cap_keycloak_events_imported", description="Eventos importados")
_logins = _meter.create_counter("cap_logins", description="Logins por resultado")

# Atraso a partir do qual o cursor é considerado parado (alerta, research R4).
CURSOR_LAG_ALERT_SECONDS = 5 * 60


@dataclass(frozen=True)
class _Mapping:
    event_type: str
    result: Result


_MAP: dict[str, _Mapping] = {
    "LOGIN": _Mapping("auth.login", "success"),
    "LOGIN_ERROR": _Mapping("auth.login_failed", "failure"),
    "USER_DISABLED_BY_TEMPORARY_LOCKOUT": _Mapping("auth.locked", "denied"),
    "LOGOUT": _Mapping("auth.logout", "success"),
    "UPDATE_CREDENTIAL": _Mapping("auth.password_changed", "success"),
    "SEND_RESET_PASSWORD": _Mapping("auth.password_reset_requested", "success"),
    "SEND_RESET_PASSWORD_ERROR": _Mapping("auth.password_reset_requested", "failure"),
    "RESET_PASSWORD": _Mapping("auth.password_reset", "success"),
    "RESET_PASSWORD_ERROR": _Mapping("auth.password_reset", "failure"),
}

# Erros do Keycloak -> motivo registrado. "invalid_user_credentials" cobre senha e código
# (a extensão usa o mesmo erro); "user_not_found" vira o mesmo motivo, sem revelar se a
# conta existe.
_FAILURE_REASONS = {
    "invalid_user_credentials": "invalid_credentials",
    "user_not_found": "invalid_credentials",
    "expired_code": "expired_code",
    "user_temporarily_disabled": "locked",
    "user_disabled": "disabled",
}

# O Keycloak 26 emite UPDATE_PASSWORD (legado) e UPDATE_CREDENTIAL para a mesma troca, e a
# recuperação de senha também termina em UPDATE_CREDENTIAL. Só UPDATE_CREDENTIAL de senha
# gera efeitos; UPDATE_PASSWORD é ignorado e RESET_PASSWORD é só auditado.


def _is_password_change(event: dict[str, Any]) -> bool:
    if event.get("type") != "UPDATE_CREDENTIAL" or event.get("error"):
        return False
    return (event.get("details") or {}).get("credential_type") == "password"


def _uuid(value: Any) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError):
        return None


class KeycloakEventIngestor:
    def __init__(self, services: Services) -> None:
        self._services = services
        self.last_success_at = time.time()

    def poll_once(self) -> int:
        """Importa os eventos novos e devolve quantos foram gravados."""
        engine = self._services.engine
        with transaction(engine, DbContext.system()) as s:
            cursor = s.execute(
                text("SELECT last_time, last_ids FROM audit.keycloak_event_cursor")
            ).one()
        last_time, last_ids = int(cursor.last_time), set(cursor.last_ids)

        imported = 0
        for event in self._services.keycloak_admin.login_events(since_ms=last_time):
            event_time, event_id = int(event["time"]), str(event["id"])
            if event_time == last_time and event_id in last_ids:
                continue
            if self._import(event):
                imported += 1
            last_ids = (last_ids | {event_id}) if event_time == last_time else {event_id}
            last_time = event_time
        self.last_success_at = time.time()
        return imported

    def _import(self, event: dict[str, Any]) -> bool:
        mapping = _MAP.get(str(event.get("type")))
        user_id = _uuid(event.get("userId"))
        event_time = int(event["time"])
        cursor_ids_sql = text(
            "UPDATE audit.keycloak_event_cursor SET"
            " last_ids = CASE WHEN last_time = :t THEN array_append(last_ids, :id)"
            "                 ELSE ARRAY[:id] END,"
            " last_time = :t"
        )
        password_change = _is_password_change(event)
        notify_email: str | None = None

        with transaction(self._services.engine, DbContext.system()) as s:
            # Senha de quem ainda não fez nenhum login é a inicial (ativação pelo link de
            # boas-vindas ou convite): só é auditada. Os eventos chegam em ordem, então o
            # login que vem depois da ativação ainda não foi importado.
            initial_password = (
                password_change
                and bool(user_id)
                and s.execute(
                    text("SELECT last_login_at IS NULL FROM identity.user_account WHERE id = :id"),
                    {"id": user_id},
                ).scalar_one_or_none()
                is True
            )
            if mapping is not None and not (
                event["type"] == "UPDATE_CREDENTIAL" and not password_change
            ):
                occurred = datetime.fromtimestamp(event_time / 1000, UTC)
                details: dict[str, Any] = {}
                if mapping.result == "failure" and event.get("error"):
                    details["reason"] = _FAILURE_REASONS.get(str(event["error"]), "other")
                if initial_password:
                    details["initial"] = True
                append_event(
                    s,
                    AuditEvent(
                        occurred_at=occurred,
                        recorded_at=datetime.now(UTC),
                        organization_id=None,
                        actor_user_id=user_id,
                        actor_kind="user",
                        event_type=mapping.event_type,
                        target_type="user" if user_id else None,
                        target_id=str(user_id) if user_id else None,
                        result=mapping.result,
                        details=details,
                        source="keycloak",
                        source_event_id=str(event["id"]),
                    ),
                    Origin(source_ip=event.get("ipAddress")),
                )
                _imported.add(1, {"type": str(event["type"])})
                if event["type"] in ("LOGIN", "LOGIN_ERROR"):
                    _logins.add(1, {"result": mapping.result})

            if event.get("type") == "LOGIN" and user_id:
                s.execute(
                    text("UPDATE identity.user_account SET last_login_at = :t WHERE id = :id"),
                    {"t": datetime.fromtimestamp(event_time / 1000, UTC), "id": user_id},
                )
            if password_change and user_id and not initial_password:
                # RF-005: encerra todas as sessões antes de confirmar o cursor. Primeiro as do
                # Keycloak: sem isso, o cookie SSO de outro navegador faria login automático
                # (sem senha nem código) assim que a sessão do Studio caísse. Se falhar, a
                # transação é desfeita e o evento é reprocessado na próxima leitura.
                self._services.keycloak_admin.logout(str(user_id))
                self._services.sessions.delete_all_for_user(user_id)
                notify_email = s.execute(
                    text("SELECT email FROM identity.user_account WHERE id = :id"),
                    {"id": user_id},
                ).scalar_one_or_none()
            s.execute(cursor_ids_sql, {"t": event_time, "id": str(event["id"])})

        if notify_email:
            try:
                self._services.mailer.send(password_changed(str(notify_email)))
            except OSError:
                logger.exception("Falha ao enviar o aviso de senha alterada")
        return mapping is not None

    def tick(self) -> None:
        """Uma leitura, com registro de falha e alerta de atraso do cursor."""
        try:
            self.poll_once()
        except Exception:
            logger.exception("Falha ao importar eventos do Keycloak")
        lag = time.time() - self.last_success_at
        if lag > CURSOR_LAG_ALERT_SECONDS:
            logger.error(
                "Importação de eventos do Keycloak parada", extra={"lag_seconds": int(lag)}
            )

    def run_forever(self, interval_seconds: float = 5.0) -> None:
        while True:
            self.tick()
            time.sleep(interval_seconds)
