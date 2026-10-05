"""E-mails enviados pelo Control Plane (T017).

E-mails de login (código, convite de pessoa nova, recuperação de senha) são enviados pelo
Keycloak. Aqui ficam os avisos que dependem de regras do Control Plane (plano §4.3 a §4.6).
Textos em português do Brasil (constituição, Seção 2).
"""

import smtplib
from dataclasses import dataclass
from email.message import EmailMessage

from cap_control_plane.core.settings import Settings

PRODUCT = "SecureLogin"


@dataclass(frozen=True)
class Email:
    to: str
    subject: str
    body: str


def password_changed(to: str) -> Email:
    return Email(
        to=to,
        subject=f"Sua senha do {PRODUCT} foi alterada",
        body=(
            f"A senha da sua conta no {PRODUCT} foi alterada e todas as sessões abertas "
            "foram encerradas.\n\n"
            "Se não foi você, procure o Administrador da sua organização imediatamente."
        ),
    )


def email_change_confirmation(to: str, link: str, valid_hours: int) -> Email:
    return Email(
        to=to,
        subject=f"Confirme seu novo e-mail no {PRODUCT}",
        body=(
            f"O Administrador da sua organização alterou o e-mail da sua conta no {PRODUCT} "
            "para este endereço. Para confirmar, abra o link abaixo:\n\n"
            f"{link}\n\n"
            f"O link vale por {valid_hours} horas e só pode ser usado uma vez. "
            "Se você não esperava esta mudança, ignore este e-mail."
        ),
    )


def email_changed_notice(to: str) -> Email:
    return Email(
        to=to,
        subject=f"O e-mail da sua conta no {PRODUCT} foi alterado",
        body=(
            f"O e-mail da sua conta no {PRODUCT} foi trocado por outro endereço e as sessões "
            "abertas foram encerradas. Este endereço não recebe mais os acessos da conta.\n\n"
            "Se você não reconhece esta mudança, procure o Administrador da sua organização."
        ),
    )


def invitation_existing_user(to: str, organization: str, link: str, valid_hours: int) -> Email:
    return Email(
        to=to,
        subject=f"Você foi convidado para {organization} no {PRODUCT}",
        body=(
            f"Você recebeu acesso à organização {organization} no {PRODUCT}. "
            "Para aceitar, entre com sua conta e abra o link abaixo:\n\n"
            f"{link}\n\n"
            f"O convite vale por {valid_hours} horas e só pode ser usado uma vez."
        ),
    )


class Mailer:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def send(self, email: Email) -> None:
        message = EmailMessage()
        message["From"] = f"{PRODUCT} <{self._settings.smtp_from}>"
        message["To"] = email.to
        message["Subject"] = email.subject
        message.set_content(email.body)

        s = self._settings
        with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=10) as smtp:
            if s.smtp_starttls:
                smtp.starttls()
            if s.smtp_username and s.smtp_password:
                smtp.login(s.smtp_username, s.smtp_password.get_secret_value())
            smtp.send_message(message)
