"""Clientes de teste para o Keycloak: Admin REST API e fluxo de login pelo navegador."""

from __future__ import annotations

import base64
import hashlib
import re
import secrets
from dataclasses import dataclass
from html import unescape
from typing import Any
from urllib.parse import parse_qs, urljoin, urlparse

import httpx

from tests.support.stack import Stack

REDIRECT_URI = "http://localhost:3000/api/v1/auth/callback"
CLIENT_ID = "cap-control-plane"


class KeycloakAdmin:
    """Admin REST API com o administrador temporário do realm master (só em testes)."""

    def __init__(self, stack: Stack) -> None:
        self._stack = stack
        self._client = httpx.Client(
            base_url=f"{stack.keycloak_url}/admin/realms/{stack.realm}",
            timeout=30,
            event_hooks={"request": [self._authorize]},
        )

    def _authorize(self, request: httpx.Request) -> None:
        # O token do admin do realm master dura 60 s: um novo a cada chamada (só em testes).
        token = httpx.post(
            f"{self._stack.keycloak_url}/realms/master/protocol/openid-connect/token",
            data={
                "grant_type": "password",
                "client_id": "admin-cli",
                "username": "bootstrap-admin",
                "password": self._stack.secrets["KEYCLOAK_BOOTSTRAP_ADMIN_PASSWORD"],
            },
        )
        token.raise_for_status()
        request.headers["Authorization"] = f"Bearer {token.json()['access_token']}"

    def get(self, path: str, **params: Any) -> Any:
        response = self._client.get(path, params=params)
        response.raise_for_status()
        return response.json()

    def create_user(self, email: str, password: str) -> str:
        response = self._client.post(
            "/users",
            json={
                "username": email,
                "email": email,
                "emailVerified": True,
                "enabled": True,
                "credentials": [{"type": "password", "value": password, "temporary": False}],
            },
        )
        response.raise_for_status()
        return response.headers["Location"].rsplit("/", 1)[-1]

    def reset_password(self, user_id: str, password: str) -> httpx.Response:
        return self._client.put(
            f"/users/{user_id}/reset-password",
            json={"type": "password", "value": password, "temporary": False},
        )

    def delete_user(self, user_id: str) -> None:
        self._client.delete(f"/users/{user_id}")

    def require_action(self, user_id: str, action: str) -> None:
        self._client.put(f"/users/{user_id}", json={"requiredActions": [action]}).raise_for_status()

    def clear_brute_force(self, user_id: str) -> None:
        self._client.delete(f"/attack-detection/brute-force/users/{user_id}").raise_for_status()

    def logout_user(self, user_id: str) -> None:
        """Encerra as sessões da pessoa no Keycloak (dispara o back-channel logout)."""
        self._client.post(f"/users/{user_id}/logout").raise_for_status()

    def brute_force_status(self, user_id: str) -> dict[str, Any]:
        return dict(self.get(f"/attack-detection/brute-force/users/{user_id}"))


_FORM_ACTION = re.compile(r'<form[^>]*\baction="([^"]+)"', re.IGNORECASE)


@dataclass
class LoginStep:
    response: httpx.Response

    @property
    def form_action(self) -> str:
        match = _FORM_ACTION.search(self.response.text)
        if match is None:
            raise AssertionError(f"Página sem formulário (HTTP {self.response.status_code})")
        return unescape(match.group(1))

    @property
    def asks_for_email_code(self) -> bool:
        return 'name="emailCode"' in self.response.text

    @property
    def callback_params(self) -> dict[str, str] | None:
        """Parâmetros (code, state) do redirecionamento final para o callback."""
        if self.response.status_code not in (302, 303):
            return None
        location = self.response.headers["Location"]
        if not location.startswith(REDIRECT_URI):
            return None
        return {k: v[0] for k, v in parse_qs(urlparse(location).query).items()}

    @property
    def authorization_code(self) -> str | None:
        if self.response.status_code not in (302, 303):
            return None
        location = self.response.headers["Location"]
        if not location.startswith(REDIRECT_URI):
            return None
        return parse_qs(urlparse(location).query).get("code", [None])[0]


class BrowserLogin:
    """Percorre o fluxo de login do realm como um navegador (cookies, formulários, PKCE).

    O Keycloak marca seus cookies como `Secure`. Navegadores aceitam esses cookies em
    `http://localhost`; o httpx não. Por isso os cookies são reenviados manualmente.
    """

    def __init__(self, stack: Stack) -> None:
        self._stack = stack
        self._cookies: dict[str, str] = {}
        self._client = httpx.Client(
            follow_redirects=False,
            timeout=30,
            event_hooks={"request": [self._send_cookies], "response": [self._keep_cookies]},
        )

    def _send_cookies(self, request: httpx.Request) -> None:
        if self._cookies:
            request.headers["Cookie"] = "; ".join(f"{k}={v}" for k, v in self._cookies.items())

    def _keep_cookies(self, response: httpx.Response) -> None:
        for name, value in response.cookies.items():
            self._cookies[name] = value

    def open(self) -> LoginStep:
        verifier = secrets.token_urlsafe(48)
        challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
            .rstrip(b"=")
            .decode()
        )
        response = self._client.get(
            f"{self._stack.realm_url}/protocol/openid-connect/auth",
            params={
                "client_id": CLIENT_ID,
                "response_type": "code",
                "scope": "openid",
                "redirect_uri": REDIRECT_URI,
                "state": secrets.token_urlsafe(16),
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            },
        )
        return LoginStep(response)

    def open_url(self, url: str) -> LoginStep:
        """Abre uma URL absoluta ou relativa ao Keycloak (ex.: link da página de login)."""
        return LoginStep(self._client.get(urljoin(self._stack.keycloak_url, url)))

    def follow(self, step: LoginStep) -> LoginStep:
        """Segue um redirecionamento interno do Keycloak (ex.: para uma ação obrigatória)."""
        location = step.response.headers.get("Location")
        if step.response.status_code in (302, 303) and location and step.callback_params is None:
            return LoginStep(self._client.get(location))
        return step

    def submit(self, step: LoginStep, data: dict[str, str]) -> LoginStep:
        return LoginStep(self._client.post(step.form_action, data=data))

    def password(self, step: LoginStep, email: str, password: str) -> LoginStep:
        return self.submit(step, {"username": email, "password": password})

    def code(self, step: LoginStep, code: str) -> LoginStep:
        return self.submit(step, {"emailCode": code, "login": "Entrar"})
