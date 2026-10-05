import base64
import json

import httpx
import pytest

from cap_control_plane.core.secrets import TransitCipher, TransitError
from cap_control_plane.core.settings import Settings


def _settings() -> Settings:
    return Settings(
        database_url="postgresql://x",
        valkey_url="redis://x",
        oidc_client_secret="s",
        admin_client_secret="s",
        openbao_token="t",
    )


def _client(handler: httpx.MockTransport) -> httpx.Client:
    return httpx.Client(base_url="http://openbao/v1/transit", transport=handler)


def test_encrypt_envia_texto_em_base64_e_devolve_cifrado() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"data": {"ciphertext": "vault:v1:abc"}})

    cipher = TransitCipher(_settings(), _client(httpx.MockTransport(handler)))

    assert cipher.encrypt("token-secreto") == "vault:v1:abc"
    assert seen["path"] == "/v1/transit/encrypt/cap-session"
    assert seen["body"] == {"plaintext": base64.b64encode(b"token-secreto").decode()}


def test_decrypt_devolve_texto_original() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        plaintext = base64.b64encode(b"token-secreto").decode()
        return httpx.Response(200, json={"data": {"plaintext": plaintext}})

    cipher = TransitCipher(_settings(), _client(httpx.MockTransport(handler)))

    assert cipher.decrypt("vault:v1:abc") == "token-secreto"


def test_erro_nao_expoe_o_texto() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"errors": ["falha"]})

    cipher = TransitCipher(_settings(), _client(httpx.MockTransport(handler)))

    with pytest.raises(TransitError) as error:
        cipher.encrypt("token-secreto")
    assert "token-secreto" not in str(error.value)
