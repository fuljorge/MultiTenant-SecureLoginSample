# Contrato: catálogo de eventos de auditoria (identidade e acesso)

Cobre a lista do RF-021. Campos de cada registro: ver
[data-model.md](../data-model.md#audit_event-append-only-39). Nenhum evento leva senha,
código, token ou link em `details`. Eventos de ações do Super Administrador gravam
`installation_scope = true` e, quando se referem a uma organização, o `organization_id`
dela (o Administrador da organização também os vê).

| `event_type` | Origem | Quando | `details` (exemplos) |
|---|---|---|---|
| `auth.login` | Keycloak `LOGIN` | Login completo (senha + código) | `organization_id` inicial |
| `auth.login_failed` | Keycloak `LOGIN_ERROR` | Senha ou código incorretos | `reason`: `invalid_credentials`, `invalid_code`, `expired_code` |
| `auth.locked` | Keycloak (brute force) | Bloqueio temporário | `until` |
| `auth.logout` | Control Plane / Keycloak `LOGOUT` | Logout, inatividade, expiração | `reason`: `user`, `idle`, `max_age`, `revoked` |
| `auth.session_revoked` | Control Plane | Sessão encerrada por terceiro ou pelo próprio usuário | `revoked_by` |
| `auth.password_changed` | Keycloak `UPDATE_PASSWORD` | Troca voluntária | — |
| `auth.password_reset_requested` | Keycloak `SEND_RESET_PASSWORD` | Pedido de recuperação | — |
| `auth.password_reset` | Keycloak `RESET_PASSWORD` | Senha redefinida pelo link | — |
| `user.activated` | Control Plane | Primeiro login após convite ou boas-vindas | `via`: `invitation`, `organization_invitation`, `bootstrap` |
| `user.invited` | Control Plane | Convite criado | `profile`, `organization_id` |
| `user.invitation_revoked` | Control Plane | Convite revogado | — |
| `user.profile_changed` | Control Plane | Perfil alterado na organização | `from`, `to` |
| `user.membership_added` / `user.membership_removed` | Control Plane | Inclusão ou remoção de organização | `organization_id`, `profile` |
| `user.email_change_requested` / `user.email_changed` | Control Plane | Troca de e-mail | sem os e-mails em claro |
| `user.disabled` / `user.enabled` | Control Plane | Desativação e reativação da conta | — |
| `user.membership_disabled` / `user.membership_enabled` | Control Plane | Desativação e reativação do vínculo com a organização (inclusive de Administrador pelo Super Administrador) | `organization_id`, `profile` |
| `user.anonymized` | CLI `cap-admin` | Pedido de esquecimento (LGPD); `actor_kind = support` | número do chamado |
| `org.created` / `org.renamed` | Control Plane | Convite de organização (nasce `pending`) ou renomeação | `name` |
| `org.activated` | Control Plane | Primeiro Administrador ativou o acesso | — |
| `org.suspended` / `org.reactivated` | Control Plane | Suspensão e reativação pelo Super Administrador | `sessions_revoked` |
| `org.invitation_resent` / `org.cancelled` | Control Plane | Reenvio do convite e cancelamento de organização pendente | — |
| `org.switched` | Control Plane | Troca de organização ativa | `from`, `to` |
| `super_admin.invited` / `super_admin.disabled` / `super_admin.enabled` | Control Plane | Gestão de Super Administradores (RF-030) | — |
| `super_admin.converted` | Migração 0004 | Administrador da instalação convertido em Super Administrador; vínculos marcados `removed` | `memberships_removed` |
| `security.settings_changed` | Control Plane | Configuração de segurança alterada | campos alterados (sem valores sensíveis) |
| `access.denied` | Control Plane | Ação sem permissão (alvo: a rota) ou sobre pessoa de outra organização (alvo: a pessoa; a resposta é `404`, US5 cenário 8) | `permission` e `method`, ou `reason: other_organization` |
| `audit.exported` | Control Plane | Exportação do histórico | filtro usado |
| `audit.tamper_attempt` | Alerta sobre o log do PostgreSQL | Tentativa de alterar ou apagar evento (recusada pelo trigger) | `operation`, papel do banco |
| `audit.origin_purged` | Control Plane | Expurgo de IP e navegador antigos | intervalo |
| `support.activation_reissued` | CLI `cap-admin` | Reemissão de link pelo suporte | número do chamado |
