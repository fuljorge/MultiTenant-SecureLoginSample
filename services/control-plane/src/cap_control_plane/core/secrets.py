"""Cifra e decifra com o OpenBao Transit (constituição, Princípio X; research R3).

O material de chave nunca sai do OpenBao: o Control Plane envia o texto e recebe o
texto cifrado. Usado para os tokens do Keycloak guardados nas sessões do BFF.
"""

import base64

import httpx

from cap_control_plane.core.settings import Settings


class TransitError(RuntimeError):
    """Falha ao cifrar ou decifrar no OpenBao."""


class TransitCipher:
    def __init__(self, settings: Settings, client: httpx.Client | None = None) -> None:
        self._key = settings.openbao_transit_key
        self._client = client or httpx.Client(
            base_url=f"{settings.openbao_url}/v1/transit",
            headers={"X-Vault-Token": settings.openbao_token.get_secret_value()},
            timeout=5,
        )

    def encrypt(self, plaintext: str) -> str:
        encoded = base64.b64encode(plaintext.encode()).decode()
        data = self._post(f"/encrypt/{self._key}", {"plaintext": encoded})
        return str(data["ciphertext"])

    def decrypt(self, ciphertext: str) -> str:
        data = self._post(f"/decrypt/{self._key}", {"ciphertext": ciphertext})
        return base64.b64decode(data["plaintext"]).decode()

    def _post(self, path: str, payload: dict[str, str]) -> dict[str, str]:
        try:
            response = self._client.post(path, json=payload)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            # Nunca inclui o texto (claro ou cifrado) na mensagem de erro.
            raise TransitError(f"OpenBao Transit falhou em {path}") from exc
        return dict(response.json()["data"])
