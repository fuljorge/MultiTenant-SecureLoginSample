from cap_control_plane.core.secrets import TransitCipher
from cap_control_plane.core.settings import Settings


def test_cifra_e_decifra_no_openbao(settings: Settings) -> None:
    cipher = TransitCipher(settings)

    ciphertext = cipher.encrypt("refresh-token-de-teste")

    assert ciphertext.startswith("vault:v1:")
    assert "refresh-token-de-teste" not in ciphertext
    assert cipher.decrypt(ciphertext) == "refresh-token-de-teste"
