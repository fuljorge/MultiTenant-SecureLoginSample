import { ApiError, type Profile } from "@cap/api-client";

/** Nomes dos perfis (spec §4; termos de produto em inglês como na referência). */
export const PROFILE_LABELS: Record<Profile, string> = {
  administrator: "Administrador",
  agent_designer: "Agent Designer",
  business_analyst: "Business Analyst",
  supervisor: "Supervisor",
  developer: "Desenvolvedor / Integration Engineer",
  financial_admin: "Administrador Financeiro",
};

export const PROFILES = Object.keys(PROFILE_LABELS) as Profile[];

export const STATUS_LABELS: Record<string, string> = {
  invited: "Convidado",
  active: "Ativo",
  disabled: "Desativado",
  pending: "Pendente",
};

/** Situação da organização (US5; RF-025). */
export const ORGANIZATION_STATUS_LABELS: Record<string, string> = {
  pending: "Pendente",
  active: "Ativa",
  suspended: "Suspensa",
  cancelled: "Cancelada",
};

/** Tipos de evento do Audit Trail (contracts/audit-events.md), em PT-BR. */
export const AUDIT_EVENT_LABELS: Record<string, string> = {
  "auth.login": "Login",
  "auth.login_failed": "Falha de login",
  "auth.locked": "Bloqueio por tentativas",
  "auth.logout": "Logout",
  "auth.session_revoked": "Sessão encerrada",
  "auth.password_changed": "Senha alterada",
  "auth.password_reset_requested": "Recuperação de senha pedida",
  "auth.password_reset": "Senha redefinida",
  "user.activated": "Conta ativada",
  "user.invited": "Convite enviado",
  "user.invitation_revoked": "Convite revogado",
  "user.profile_changed": "Perfil alterado",
  "user.membership_added": "Incluído na organização",
  "user.membership_removed": "Removido da organização",
  "user.membership_disabled": "Acesso à organização desativado",
  "user.membership_enabled": "Acesso à organização reativado",
  "user.email_change_requested": "Troca de e-mail pedida",
  "user.email_changed": "E-mail alterado",
  "user.disabled": "Conta desativada",
  "user.enabled": "Conta reativada",
  "org.created": "Organização convidada",
  "org.activated": "Organização ativada",
  "org.renamed": "Organização renomeada",
  "org.suspended": "Organização suspensa",
  "org.reactivated": "Organização reativada",
  "org.invitation_resent": "Convite da organização reenviado",
  "org.cancelled": "Organização cancelada",
  "org.switched": "Troca de organização",
  "super_admin.invited": "Super Administrador convidado",
  "super_admin.disabled": "Super Administrador desativado",
  "super_admin.enabled": "Super Administrador reativado",
  "security.settings_changed": "Segurança alterada",
  "access.denied": "Acesso negado",
  "audit.exported": "Auditoria exportada",
  "audit.origin_purged": "Expurgo de origem",
  "support.activation_reissued": "Link reemitido pelo suporte",
};

export const AUDIT_RESULT_LABELS: Record<string, string> = {
  success: "Sucesso",
  failure: "Falha",
  denied: "Negado",
};

/** Mensagem para o usuário a partir do erro da API (Problem Details). */
export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    const body = error.body as { title?: string; detail?: unknown } | undefined;
    if (body?.title) return body.title;
    if (error.status === 422) return "Verifique os valores informados.";
    if (error.status === 403) return "Você não tem permissão para esta ação.";
  }
  return "Não foi possível concluir a ação. Tente de novo.";
}
