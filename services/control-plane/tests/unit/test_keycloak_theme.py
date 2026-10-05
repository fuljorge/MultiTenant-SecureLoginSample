"""Tema de login do Keycloak não revela se a conta existe (RNF-005; T034)."""

from tests.support.stack import REPO_ROOT

MESSAGES = REPO_ROOT / "infra/keycloak/themes/cap/login/messages/messages_pt_BR.properties"

# Chaves que o Keycloak usa para falhas de login; todas precisam ter o mesmo texto.
LOGIN_FAILURE_KEYS = [
    "invalidUserMessage",
    "invalidUsernameMessage",
    "invalidUsernameOrEmailMessage",
    "accountTemporarilyDisabledMessage",
    "accountPermanentlyDisabledMessage",
    "accountDisabledMessage",
]


def test_falhas_de_login_tem_uma_unica_mensagem() -> None:
    entries = dict(
        line.split("=", 1)
        for line in MESSAGES.read_text(encoding="utf-8").splitlines()
        if "=" in line and not line.startswith("#")
    )

    values = {key: entries.get(key) for key in LOGIN_FAILURE_KEYS}

    assert None not in values.values(), values
    assert len(set(values.values())) == 1, values


THEME = REPO_ROOT / "infra/keycloak/themes/cap/login"


def test_indicador_de_forca_carregado_e_sem_rede() -> None:
    """RF-032 (T098): o tema carrega o indicador, que nunca envia a senha a lugar nenhum."""
    properties = (THEME / "theme.properties").read_text(encoding="utf-8")
    script = (THEME / "resources/js/password-strength.js").read_text(encoding="utf-8")
    css = (THEME / "resources/css/cap.css").read_text(encoding="utf-8")

    assert "scripts=js/password-strength.js" in properties
    assert "password-new" in script
    assert not any(api in script for api in ("fetch(", "XMLHttpRequest", "sendBeacon", "WebSocket"))
    assert ".cap-strength" in css
