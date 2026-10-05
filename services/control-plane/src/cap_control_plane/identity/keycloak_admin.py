"""Cliente da Admin REST API do Keycloak (T031).

Usa a conta de serviço `cap-admin-bridge` (Client Credentials), com os papéis mínimos do
realm (infra/keycloak/realm/cap-realm.yaml). O Keycloak cuida só da autenticação; nome,
organizações e perfis ficam no Control Plane (research R2).
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any

import httpx

from cap_control_plane.core.settings import Settings

_RETRIES = 3


class KeycloakAdminError(RuntimeError):
    """Falha na Admin API do Keycloak (sem dados do usuário na mensagem)."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class KeycloakAdminClient:
    def __init__(self, settings: Settings, http: httpx.Client | None = None) -> None:
        self._settings = settings
        self._http = http or httpx.Client(timeout=10)
        self._base = f"{settings.keycloak_url}/admin/realms/{settings.keycloak_realm}"
        self._token: str | None = None
        self._token_expires_at = 0.0

    # Autenticação da conta de serviço --------------------------------------------------

    def _access_token(self) -> str:
        if self._token and time.monotonic() < self._token_expires_at:
            return self._token
        s = self._settings
        response = self._http.post(
            f"{s.keycloak_realm_url}/protocol/openid-connect/token",
            data={
                "grant_type": "client_credentials",
                "client_id": s.admin_client_id,
                "client_secret": s.admin_client_secret.get_secret_value(),
            },
        )
        if response.status_code != 200:
            raise KeycloakAdminError(f"Token da conta de serviço recusado: {response.status_code}")
        body = response.json()
        self._token = str(body["access_token"])
        # Renova 30 s antes de expirar.
        self._token_expires_at = time.monotonic() + int(body["expires_in"]) - 30
        return self._token

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        last_error: Exception | None = None
        for attempt in range(_RETRIES):
            try:
                response = self._http.request(
                    method,
                    f"{self._base}{path}",
                    headers={"Authorization": f"Bearer {self._access_token()}"},
                    **kwargs,
                )
            except httpx.TransportError as exc:
                last_error = exc
            else:
                if response.status_code < 500:
                    if response.status_code >= 400:
                        raise KeycloakAdminError(
                            f"{method} {path.split('?')[0]} respondeu {response.status_code}",
                            response.status_code,
                        )
                    return response
                last_error = KeycloakAdminError(f"{method} respondeu {response.status_code}")
            time.sleep(0.2 * (attempt + 1))
        raise KeycloakAdminError(f"{method} falhou após {_RETRIES} tentativas") from last_error

    # Usuários ---------------------------------------------------------------------------

    def create_user(self, email: str) -> str:
        """Cria a pessoa já exigindo a definição de senha no primeiro acesso (plano §4.3)."""
        response = self._request(
            "POST",
            "/users",
            json={
                "username": email,
                "email": email,
                "emailVerified": True,
                "enabled": True,
                "requiredActions": ["UPDATE_PASSWORD"],
            },
        )
        return response.headers["Location"].rsplit("/", 1)[-1]

    def get_user(self, user_id: str) -> dict[str, Any]:
        return dict(self._request("GET", f"/users/{user_id}").json())

    def find_user_by_email(self, email: str) -> dict[str, Any] | None:
        users = self._request("GET", "/users", params={"email": email, "exact": "true"}).json()
        return dict(users[0]) if users else None

    def delete_user(self, user_id: str) -> None:
        self._request("DELETE", f"/users/{user_id}")

    def send_activation_email(self, user_id: str, *, lifespan_seconds: int) -> None:
        """E-mail de boas-vindas ou convite: link de uso único para definir a senha."""
        s = self._settings
        self._request(
            "PUT",
            f"/users/{user_id}/execute-actions-email",
            params={
                "lifespan": lifespan_seconds,
                "client_id": s.oidc_client_id,
                # Volta à página inicial do Studio, que inicia o login (senha e código).
                "redirect_uri": f"{s.public_url}/",
            },
            json=["UPDATE_PASSWORD"],
        )

    def set_password(self, user_id: str, password: str) -> None:
        """Só para testes e para o bootstrap de ambientes locais."""
        self._request(
            "PUT",
            f"/users/{user_id}/reset-password",
            json={"type": "password", "value": password, "temporary": False},
        )

    def require_password_update(self, user_id: str) -> None:
        """Exige nova senha no próximo acesso (link de ativação reemitido)."""
        self._request("PUT", f"/users/{user_id}", json={"requiredActions": ["UPDATE_PASSWORD"]})

    def set_enabled(self, user_id: str, *, enabled: bool) -> None:
        self._request("PUT", f"/users/{user_id}", json={"enabled": enabled})

    def update_email(self, user_id: str, email: str) -> None:
        self._request(
            "PUT",
            f"/users/{user_id}",
            json={"email": email, "username": email, "emailVerified": True},
        )

    def logout(self, user_id: str) -> None:
        """Encerra todas as sessões da pessoa no Keycloak (RF-005, RF-011).

        Pessoa inexistente no Keycloak (404) não tem sessões: nada a fazer.
        """
        try:
            self._request("POST", f"/users/{user_id}/logout")
        except KeycloakAdminError as exc:
            if exc.status_code != 404:
                raise

    def delete_session(self, keycloak_sid: str) -> None:
        """Encerra uma sessão do Keycloak (logout pelo Studio)."""
        try:
            self._request("DELETE", f"/sessions/{keycloak_sid}")
        except KeycloakAdminError:
            # Sessão já encerrada ou expirada no Keycloak: nada a fazer.
            pass

    def session_count(self, user_id: str) -> int:
        return len(self._request("GET", f"/users/{user_id}/sessions").json())

    def brute_force_status(self, user_id: str) -> dict[str, Any]:
        return dict(self._request("GET", f"/attack-detection/brute-force/users/{user_id}").json())

    # Eventos (research R4) --------------------------------------------------------------

    def login_events(self, *, since_ms: int, page_size: int = 100) -> list[dict[str, Any]]:
        """Eventos de login a partir de `since_ms`, do mais antigo para o mais novo."""
        return self._events("/events", since_ms, page_size, time_key="time")

    def admin_events(self, *, since_ms: int, page_size: int = 100) -> list[dict[str, Any]]:
        return self._events("/admin-events", since_ms, page_size, time_key="time")

    def _events(
        self, path: str, since_ms: int, page_size: int, *, time_key: str
    ) -> list[dict[str, Any]]:
        # A API filtra por dia (dateFrom) e devolve do mais novo para o mais antigo.
        date_from = datetime.fromtimestamp(since_ms / 1000, UTC).strftime("%Y-%m-%d")
        collected: list[dict[str, Any]] = []
        first = 0
        while True:
            page = self._request(
                "GET", path, params={"dateFrom": date_from, "first": first, "max": page_size}
            ).json()
            collected.extend(e for e in page if int(e[time_key]) >= since_ms)
            if len(page) < page_size or int(page[-1][time_key]) < since_ms:
                break
            first += page_size
        return sorted(collected, key=lambda e: int(e[time_key]))

    # Configuração de segurança do realm (RF-007; plano §4.8) ----------------------------

    def flow_executions(self, flow_alias: str) -> list[dict[str, Any]]:
        return list(self._request("GET", f"/authentication/flows/{flow_alias}/executions").json())

    def authenticator_config(self, config_id: str) -> dict[str, str]:
        body = self._request("GET", f"/authentication/config/{config_id}").json()
        return dict(body.get("config") or {})

    def update_authenticator_config(self, config_id: str, config: dict[str, str]) -> None:
        current = self._request("GET", f"/authentication/config/{config_id}").json()
        self._request(
            "PUT",
            f"/authentication/config/{config_id}",
            json={"id": config_id, "alias": current.get("alias"), "config": config},
        )

    def get_realm(self) -> dict[str, Any]:
        return dict(self._request("GET", "").json())

    def update_realm(self, changes: dict[str, Any]) -> None:
        self._request("PUT", "", json=changes)
