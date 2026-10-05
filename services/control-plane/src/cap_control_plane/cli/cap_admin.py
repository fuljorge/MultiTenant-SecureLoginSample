"""Ferramenta de operação `cap-admin` (T044; contracts/identity-api.md).

Executada pelo pipeline de provisionamento e pela equipe de operação dentro da
instalação; nunca exposta pela rede. Só cria o Super Administrador inicial e reemite o
link de ativação de um Super Administrador (spec §4.8, RF-008 e caso de borda do Super
Administrador que perdeu o e-mail). As organizações são criadas pelo Super Administrador,
na plataforma.

    cap-admin bootstrap-super-admin --email ana@exemplo.com.br --name "Ana"
    cap-admin reissue-activation --email ana@exemplo.com.br --ticket CH-123 [--new-email ...]
    cap-admin audit verify   # recalcula a cadeia de hash do Audit Trail
    cap-admin anonymize-user --email pessoa@cliente.com.br --ticket LGPD-123
"""

from __future__ import annotations

import argparse
import re
import sys
import unicodedata
import uuid
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session

from cap_control_plane.audit.chain import ActorKind, AuditEvent
from cap_control_plane.audit.verify import verify_chain
from cap_control_plane.audit.writer import append_event
from cap_control_plane.core.db import DbContext, transaction
from cap_control_plane.core.logging import configure_logging
from cap_control_plane.core.settings import get_settings
from cap_control_plane.services import Services


class AdminAlreadyExistsError(RuntimeError):
    """A instalação já tem Super Administrador: o bootstrap só roda uma vez."""


@dataclass(frozen=True)
class BootstrapResult:
    user_id: uuid.UUID
    email: str


def slugify(value: str) -> str:
    ascii_text = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")
    return slug or "organizacao"


def _audit(
    session: Session,
    *,
    event_type: str,
    actor_kind: ActorKind,
    target_type: str,
    target_id: uuid.UUID,
    organization_id: uuid.UUID | None,
    details: dict[str, object],
    installation_scope: bool = True,
) -> None:
    append_event(
        session,
        AuditEvent.now(
            organization_id=organization_id,
            actor_user_id=None,
            actor_kind=actor_kind,
            event_type=event_type,
            target_type=target_type,
            target_id=str(target_id),
            result="success",
            details=details,
            installation_scope=installation_scope,
        ),
    )


def bootstrap_super_admin(services: Services, *, email: str, name: str) -> BootstrapResult:
    """Cria o Super Administrador inicial e envia o e-mail de boas-vindas (§53.2; US2).

    Não cria organização: a primeira de cada cliente nasce do convite do Super
    Administrador (US5).
    """
    email = email.strip().lower()
    with transaction(services.engine, DbContext.system()) as s:
        if s.execute(text("SELECT count(*) FROM identity.super_admin")).scalar_one():
            raise AdminAlreadyExistsError("A instalação já tem Super Administrador")

    existing = services.keycloak_admin.find_user_by_email(email)
    user_id = uuid.UUID(existing["id"] if existing else services.keycloak_admin.create_user(email))

    with transaction(services.engine, DbContext.system()) as s:
        s.execute(
            text(
                "INSERT INTO identity.user_account (id, email, name, status)"
                " VALUES (:id, :email, :name, 'invited')"
            ),
            {"id": user_id, "email": email, "name": name.strip()},
        )
        s.execute(text("INSERT INTO identity.super_admin (user_id) VALUES (:id)"), {"id": user_id})
        _audit(
            s,
            event_type="super_admin.invited",
            actor_kind="system",
            target_type="user",
            target_id=user_id,
            organization_id=None,
            details={"via": "bootstrap"},
        )

    services.keycloak_admin.send_activation_email(
        str(user_id), lifespan_seconds=services.settings.invitation_valid_hours * 3600
    )
    return BootstrapResult(user_id=user_id, email=email)


def reissue_activation(
    services: Services, *, email: str, ticket: str, new_email: str | None = None
) -> uuid.UUID:
    """Reemite o link de ativação, opcionalmente para outro e-mail (atendimento de suporte).

    Usado quando um Super Administrador perdeu o acesso ao e-mail ou o link expirou. Exige o
    número do chamado, registrado no Audit Trail com `actor_kind = support`. Administradores
    de organização são geridos pelo Super Administrador, na plataforma (RF-027).
    """
    if not ticket.strip():
        raise ValueError("Informe o número do chamado")
    email = email.strip().lower()
    with transaction(services.engine, DbContext.system()) as s:
        user_id = s.execute(
            text(
                "SELECT u.id FROM identity.user_account u"
                " JOIN identity.super_admin a ON a.user_id = u.id WHERE u.email = :email"
            ),
            {"email": email},
        ).scalar_one_or_none()
    if user_id is None:
        raise LookupError("Super Administrador não encontrado")

    kc = services.keycloak_admin
    if new_email:
        new_email = new_email.strip().lower()
        kc.update_email(str(user_id), new_email)
    # Nova senha obrigatória e sessões encerradas: quem tinha o e-mail antigo perde o acesso.
    kc.require_password_update(str(user_id))
    kc.logout(str(user_id))
    services.sessions.delete_all_for_user(user_id)

    with transaction(services.engine, DbContext.system()) as s:
        if new_email:
            s.execute(
                text(
                    "UPDATE identity.user_account SET email = :email, updated_at = now(),"
                    " version = version + 1 WHERE id = :id"
                ),
                {"email": new_email, "id": user_id},
            )
        _audit(
            s,
            event_type="support.activation_reissued",
            actor_kind="support",
            target_type="user",
            target_id=user_id,
            organization_id=None,
            details={"ticket": ticket.strip(), "address_changed": bool(new_email)},
            installation_scope=True,
        )

    kc.send_activation_email(
        str(user_id), lifespan_seconds=services.settings.invitation_valid_hours * 3600
    )
    return uuid.UUID(str(user_id))


def _blocking_last_admin(session: Session, user_id: uuid.UUID) -> str | None:
    """RF-012: a anonimização não pode deixar a instalação ou uma organização sem gestão."""
    last_super = session.execute(
        text(
            "SELECT count(*) = 1 AND bool_or(a.user_id = :u) FROM identity.super_admin a"
            " JOIN identity.user_account u ON u.id = a.user_id WHERE u.status = 'active'"
        ),
        {"u": user_id},
    ).scalar_one()
    if last_super:
        return "É o último Super Administrador ativo da instalação."
    orphaned = session.execute(
        text(
            "SELECT count(*) FROM identity.membership m"
            " JOIN identity.organization o ON o.id = m.organization_id"
            " WHERE m.user_id = :u AND m.profile = 'administrator' AND m.status = 'active'"
            " AND o.status = 'active' AND NOT EXISTS ("
            "  SELECT 1 FROM identity.membership x JOIN identity.user_account xu"
            "  ON xu.id = x.user_id WHERE x.organization_id = m.organization_id"
            "  AND x.user_id <> :u AND x.profile = 'administrator' AND x.status = 'active'"
            "  AND xu.status = 'active')"
        ),
        {"u": user_id},
    ).scalar_one()
    if orphaned:
        return "É o último Administrador ativo de uma organização; nomeie outro antes."
    return None


def anonymize_user(services: Services, *, email: str, ticket: str) -> uuid.UUID:
    """Pedido de esquecimento (LGPD; spec, seção 8; T072).

    Apaga ou substitui os dados pessoais em todos os armazenamentos da feature: conta no
    Keycloak, sessões, nome e e-mail, convites, trocas de e-mail e a origem (IP e
    navegador) dos eventos da pessoa. Os eventos de auditoria não mudam: passam a apontar
    para um registro sem nome nem e-mail, e a cadeia continua verificável.
    """
    if not ticket.strip():
        raise ValueError("Informe o número do chamado")
    email = email.strip().lower()
    with transaction(services.engine, DbContext.system()) as s:
        user_id = s.execute(
            text("SELECT id FROM identity.user_account WHERE email = :e AND anonymized_at IS NULL"),
            {"e": email},
        ).scalar_one_or_none()
        if user_id is None:
            raise LookupError("Pessoa não encontrada")
        user_id = uuid.UUID(str(user_id))
        blocked = _blocking_last_admin(s, user_id)
        if blocked:
            raise ValueError(blocked)
        anonymous = f"anonimo-{user_id.hex}@anonimizado.invalid"
        s.execute(
            text(
                "DELETE FROM audit.audit_event_origin o USING audit.audit_event e"
                " WHERE e.seq = o.seq AND e.actor_user_id = :u"
            ),
            {"u": user_id},
        )
        s.execute(
            text(
                "UPDATE identity.invitation SET email = :a,"
                " status = CASE WHEN status = 'pending' THEN 'revoked' ELSE status END"
                " WHERE email = :e"
            ),
            {"a": anonymous, "e": email},
        )
        s.execute(
            text(
                "UPDATE identity.email_change_request SET new_email = :a,"
                " status = CASE WHEN status = 'pending' THEN 'revoked' ELSE status END"
                " WHERE user_id = :u"
            ),
            {"a": anonymous, "u": user_id},
        )
        s.execute(
            text(
                "UPDATE identity.membership SET status = 'removed', version = version + 1,"
                " updated_at = now() WHERE user_id = :u AND status <> 'removed'"
            ),
            {"u": user_id},
        )
        s.execute(text("DELETE FROM identity.super_admin WHERE user_id = :u"), {"u": user_id})
        s.execute(
            text(
                "UPDATE identity.user_account SET name = 'Pessoa anonimizada', email = :a,"
                " status = 'disabled', last_login_at = NULL, anonymized_at = now(),"
                " version = version + 1, updated_at = now() WHERE id = :u"
            ),
            {"a": anonymous, "u": user_id},
        )
        _audit(
            s,
            event_type="user.anonymized",
            actor_kind="support",
            target_type="user",
            target_id=user_id,
            organization_id=None,
            details={"ticket": ticket.strip()},
        )
        # Keycloak antes do commit: se falhar, nada muda e o pedido pode ser repetido.
        kc = services.keycloak_admin
        if kc.find_user_by_email(email) is not None:
            kc.logout(str(user_id))
            kc.delete_user(str(user_id))
    services.sessions.delete_all_for_user(user_id)
    return user_id


def audit_verify(services: Services) -> int | None:
    """`seq` do primeiro registro adulterado, ou None se a cadeia estiver íntegra (§39)."""
    with transaction(services.engine, DbContext.system()) as s:
        return verify_chain(s)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="cap-admin", description="Operação da instalação")
    commands = parser.add_subparsers(dest="command", required=True)

    bootstrap = commands.add_parser(
        "bootstrap-super-admin", help="Cria o Super Administrador inicial"
    )
    bootstrap.add_argument("--email", required=True)
    bootstrap.add_argument("--name", required=True)

    reissue = commands.add_parser("reissue-activation", help="Reemite o link de ativação")
    reissue.add_argument("--email", required=True)
    reissue.add_argument("--ticket", required=True, help="Número do chamado de suporte")
    reissue.add_argument("--new-email")

    anonymize = commands.add_parser("anonymize-user", help="Pedido de esquecimento (LGPD)")
    anonymize.add_argument("--email", required=True)
    anonymize.add_argument("--ticket", required=True, help="Número do chamado")

    audit = commands.add_parser("audit", help="Audit Trail")
    audit_commands = audit.add_subparsers(dest="audit_command", required=True)
    audit_commands.add_parser("verify", help="Verifica a cadeia de hash")

    args = parser.parse_args(argv)
    configure_logging()
    services = Services.from_settings(get_settings())
    try:
        if args.command == "anonymize-user":
            user_id = anonymize_user(services, email=args.email, ticket=args.ticket)
            print(f"Dados pessoais de {user_id} anonimizados.")
        elif args.command == "audit":
            broken = audit_verify(services)
            if broken is not None:
                print(f"Cadeia adulterada a partir do registro {broken}.", file=sys.stderr)
                return 2
            print("Cadeia do Audit Trail íntegra.")
        elif args.command == "bootstrap-super-admin":
            result = bootstrap_super_admin(services, email=args.email, name=args.name)
            print(f"Super Administrador criado: {result.user_id}. E-mail de boas-vindas enviado.")
        else:
            user_id = reissue_activation(
                services, email=args.email, ticket=args.ticket, new_email=args.new_email
            )
            print(f"Link de ativação reemitido para {user_id}.")
    except (AdminAlreadyExistsError, LookupError, ValueError) as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
