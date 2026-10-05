"""Cliente OIDC do BFF: Authorization Code + PKCE com o Keycloak (T036; research R3).

Valida ID tokens e logout tokens (back-channel logout) com as chaves públicas do realm.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx
from joserfc import jwt
from joserfc.errors import JoseError
from joserfc.jwk import KeySet

from cap_control_plane.core.settings import Settings

_BACKCHANNEL_EVENT = "http://schemas.openid.net/event/backchannel-logout"
_CLOCK_SKEW_SECONDS = 30


class OidcError(RuntimeError):
    """Falha no fluxo OIDC (sem tokens nem dados pessoais na mensagem)."""


@dataclass(frozen=True)
class PkcePair:
    verifier: str
    challenge: str

    @classmethod
    def new(cls) -> PkcePair:
        verifier = secrets.token_urlsafe(64)
        digest = hashlib.sha256(verifier.encode()).digest()
        return cls(verifier, base64.urlsafe_b64encode(digest).rstrip(b"=").decode())


@dataclass(frozen=True)
class IdentityClaims:
    subject: str
    keycloak_sid: str
    email: str | None
    # Momento da autenticação (senha e código), não da emissão do token.
    auth_time: float


class OidcClient:
    def __init__(self, settings: Settings, http: httpx.Client | None = None) -> None:
        self._settings = settings
        self._http = http or httpx.Client(timeout=10)
        self._metadata: dict[str, Any] | None = None
        self._keys: KeySet | None = None
        self._keys_fetched_at = 0.0

    @property
    def redirect_uri(self) -> str:
        return f"{self._settings.public_url}/api/v1/auth/callback"

    def _discovery(self) -> dict[str, Any]:
        if self._metadata is None:
            url = f"{self._settings.keycloak_realm_url}/.well-known/openid-configuration"
            response = self._http.get(url)
            response.raise_for_status()
            self._metadata = dict(response.json())
        return self._metadata

    def _key_set(self, *, refresh: bool = False) -> KeySet:
        # Recarrega quando pedido (chave desconhecida), no máximo a cada 60 s.
        if self._keys is None or (refresh and time.monotonic() - self._keys_fetched_at > 60):
            response = self._http.get(self._discovery()["jwks_uri"])
            response.raise_for_status()
            self._keys = KeySet.import_key_set(response.json())
            self._keys_fetched_at = time.monotonic()
        return self._keys

    def authorization_url(
        self,
        *,
        state: str,
        nonce: str,
        pkce: PkcePair,
        kc_action: str | None = None,
        reauth: bool = False,
    ) -> str:
        params = {
            "client_id": self._settings.oidc_client_id,
            "response_type": "code",
            "scope": "openid",
            "redirect_uri": self.redirect_uri,
            "state": state,
            "nonce": nonce,
            "code_challenge": pkce.challenge,
            "code_challenge_method": "S256",
        }
        if kc_action:
            params["kc_action"] = kc_action
        if reauth:
            # Senha e código de novo, mesmo com a sessão SSO aberta (RF-031).
            params["prompt"] = "login"
            params["max_age"] = "0"
        return f"{self._discovery()['authorization_endpoint']}?{urlencode(params)}"

    def exchange_code(self, code: str, pkce_verifier: str) -> dict[str, str]:
        s = self._settings
        response = self._http.post(
            self._discovery()["token_endpoint"],
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": self.redirect_uri,
                "code_verifier": pkce_verifier,
                "client_id": s.oidc_client_id,
                "client_secret": s.oidc_client_secret.get_secret_value(),
            },
        )
        if response.status_code != 200:
            raise OidcError(f"Troca do código recusada: {response.status_code}")
        body = response.json()
        return {k: str(body[k]) for k in ("access_token", "refresh_token", "id_token") if k in body}

    def _decode(self, token: str) -> dict[str, Any]:
        try:
            try:
                decoded = jwt.decode(token, self._key_set(), algorithms=["RS256"])
            except JoseError:
                decoded = jwt.decode(token, self._key_set(refresh=True), algorithms=["RS256"])
        except (JoseError, ValueError) as exc:
            raise OidcError("Assinatura do token inválida") from exc
        return dict(decoded.claims)

    def _registry(self, **extra: dict[str, Any]) -> jwt.JWTClaimsRegistry:
        options: dict[str, Any] = {
            "iss": {"essential": True, "value": self._discovery()["issuer"]},
            "aud": {"essential": True, "value": self._settings.oidc_client_id},
            **extra,
        }
        return jwt.JWTClaimsRegistry(leeway=_CLOCK_SKEW_SECONDS, **options)

    def validate_id_token(self, id_token: str, *, nonce: str) -> IdentityClaims:
        claims = self._decode(id_token)
        try:
            self._registry(
                exp={"essential": True},
                sub={"essential": True},
                sid={"essential": True},
                nonce={"essential": True, "value": nonce},
            ).validate(claims)
        except JoseError as exc:
            raise OidcError("ID token inválido") from exc
        return IdentityClaims(
            subject=str(claims["sub"]),
            keycloak_sid=str(claims["sid"]),
            email=claims.get("email"),
            auth_time=float(claims.get("auth_time") or claims.get("iat") or 0),
        )

    def validate_logout_token(self, logout_token: str) -> str:
        """Valida o logout token do back-channel logout e devolve o `sid` do Keycloak."""
        claims = self._decode(logout_token)
        try:
            self._registry(iat={"essential": True}, sid={"essential": True}).validate(claims)
        except JoseError as exc:
            raise OidcError("Logout token inválido") from exc
        events = claims.get("events")
        if not isinstance(events, dict) or _BACKCHANNEL_EVENT not in events or "nonce" in claims:
            raise OidcError("Logout token sem o evento de back-channel logout")
        return str(claims["sid"])
