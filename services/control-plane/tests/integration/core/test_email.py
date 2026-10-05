import secrets
from datetime import UTC, datetime

from cap_control_plane.core.email import Mailer, password_changed
from cap_control_plane.core.settings import Settings
from tests.support.mailpit import wait_for_email
from tests.support.stack import Stack


def test_aviso_de_senha_trocada_chega_em_portugues(stack: Stack, settings: Settings) -> None:
    to = f"aviso-{secrets.token_hex(4)}@exemplo.com.br"
    since = datetime.now(UTC)

    Mailer(settings).send(password_changed(to))

    text = wait_for_email(stack.mailpit_url, to, since)
    assert "foi alterada" in text
    assert "Administrador da sua organização" in text
