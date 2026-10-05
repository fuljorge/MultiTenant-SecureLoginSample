# Contrato: API de identidade do Control Plane

Visão de contrato para revisão. A fonte de verdade na implementação é o OpenAPI gerado
pelo FastAPI, e o cliente TypeScript é gerado a partir dele (stack §3.1).

## Convenções

- Base: `/api/v1`. Mesmo domínio do Studio (cookie `__Host-` não aceita subdomínio).
- Autenticação: cookie de sessão do BFF. Requisições que alteram estado exigem o
  cabeçalho `X-CSRF-Token`.
- Autorização: cada rota declara a permissão exigida (matriz da spec, seção 5.1),
  avaliada no perfil da **organização ativa**. Sem sessão: `401`. Sem permissão: `403`
  e evento `access.denied` no Audit Trail.
- Recursos de outra organização respondem `404` (não revelam existência); a tentativa
  sobre pessoa de outra organização é registrada como `access.denied` (US5, cenário 8).
- Erros no formato *Problem Details* (RFC 9457), sem dados sensíveis.
- **Reautenticação recente (RF-031):** rotas marcadas com "recente" exigem login completo
  (senha e código) há no máximo 15 min. Sem isso: `401` com `{"code": "reauth_required"}`,
  sem efeito; o Studio leva a pessoa a `GET /auth/login?reauth=1&return_to=...`.
- Edição concorrente: `If-Match` com a versão do recurso; divergência responde `412`.

## Autenticação e sessão (BFF)

| Método e rota | Quem | Descrição |
|---|---|---|
| `GET /auth/login` | público | Inicia o fluxo OIDC (Authorization Code + PKCE) e redireciona ao Keycloak; com `reauth=1`, envia `prompt=login` e `max_age=0` (RF-031) |
| `GET /auth/callback` | público | Recebe o código, cria a sessão, define o cookie, ativa vínculos `pending` do convite e redireciona ao Studio |
| `POST /auth/logout` | sessão | Encerra a sessão no BFF e no Keycloak |
| `POST /auth/backchannel-logout` | Keycloak | *Back-channel logout* (logout token assinado); encerra as sessões do BFF ligadas à sessão do Keycloak |
| `GET /me` | sessão | Usuário, tipo de principal (`member` ou `super_admin`), organizações com perfil em cada uma, organização ativa (nula para o Super Administrador), permissões efetivas, token CSRF |
| `PUT /me/active-organization` | sessão | Troca a organização ativa (RF-019); valida o vínculo |
| `GET /me/sessions` | sessão | Sessões ativas do usuário (início, último uso, navegador, IP parcial) |
| `DELETE /me/sessions/{id}` | sessão | Encerra uma sessão própria |
| `GET /auth/password` | sessão | Redireciona para a troca de senha no Keycloak (*required action* `UPDATE_PASSWORD` via `kc_action`), sempre com nova autenticação (`max_age=0`; RF-031) |

Recuperação de senha e o login com código são telas do Keycloak; não passam pela API.

## Usuários

| Método e rota | Permissão | Descrição |
|---|---|---|
| `GET /users` | `users:read` | Lista com filtros: nome, e-mail, organização, perfil, situação; paginação |
| `GET /users/{id}` | `users:read` | Detalhe com vínculos e situação de bloqueio |
| `POST /invitations` | `users:manage` | Convida: `email`, `name`, `organization_id`, `profile` |
| `GET /invitations` | `users:read` | Convites da organização |
| `DELETE /invitations/{id}` | `users:manage` | Revoga convite pendente |
| `POST /invitations/{token}/accept` | sessão | Aceite de convite por pessoa já cadastrada |
| `PATCH /users/{id}/memberships/{org_id}` | `users:manage` | Altera o perfil na organização |
| `DELETE /users/{id}/memberships/{org_id}` | `users:manage` · recente | Remove da organização |
| `POST /users/{id}/disable` | `users:manage` · recente | Desativa o vínculo com a organização ativa e encerra as sessões nela; sem outro vínculo ativo, também desativa a conta no Keycloak (RF-011; plano, seção 4.4) |
| `POST /users/{id}/enable` | `users:manage` · recente | Reativa o vínculo (e a conta, se estava desativada) |
| `POST /users/{id}/email-change` | `users:manage` · recente | Inicia troca de e-mail; envia confirmação ao novo e-mail |
| `POST /email-change/{token}/confirm` | público | Confirma; atualiza o Keycloak, encerra sessões, avisa o e-mail antigo |
| `POST /users/{id}/sessions/revoke` | `users:manage` · recente | Encerra todas as sessões do usuário |

Administrador de organização só age sobre vínculos da própria organização. Trocar o
e-mail de quem pertence a outras organizações é recusado (`409`) nesta fase.
Desativar ou remover o último Administrador ativo de uma organização ativa responde
`409` (RF-012). Rotas de usuários respondem `403` para o Super Administrador (RF-028).

## Organizações (Super Administrador)

| Método e rota | Permissão | Descrição |
|---|---|---|
| `GET /organizations` | `organizations:manage` | Todas as organizações: `q` (nome da organização ou nome/e-mail do Administrador), `org_status`, `limit`, `offset` (RF-025) |
| `GET /organizations/{id}` | `organizations:manage` | Detalhe com Administradores e convite pendente |
| `POST /organizations` | `organizations:manage` · recente | Convite de organização: `name`, `admin_name`, `admin_email`; cria a organização `pending` (RF-018) |
| `PATCH /organizations/{id}` | `organizations:manage` | Renomeia (`If-Match`) |
| `POST /organizations/{id}/suspend` | `organizations:manage` · recente | Suspende: encerra sessões e bloqueia o acesso (RF-026) |
| `POST /organizations/{id}/reactivate` | `organizations:manage` · recente | Reativa |
| `POST /organizations/{id}/invitation/resend` | `organizations:manage` | Reenvia o convite da organização pendente |
| `POST /organizations/{id}/cancel` | `organizations:manage` · recente | Cancela organização `pending` |
| `POST /organizations/{id}/administrators` | `organization_admins:manage` · recente | Convida mais um Administrador: `name`, `email` (RF-027) |
| `POST /organizations/{id}/administrators/{user_id}/disable` | `organization_admins:manage` · recente | Desativa o vínculo de Administrador; `409` se for o último ativo (RF-012) |
| `POST /organizations/{id}/administrators/{user_id}/enable` | `organization_admins:manage` · recente | Reativa |

Organizações da própria pessoa, para quem é membro: `GET /me`.

## Super Administradores

| Método e rota | Permissão | Descrição |
|---|---|---|
| `GET /super-admins` | `super_admins:manage` | Lista |
| `POST /super-admins` | `super_admins:manage` · recente | Convida: `name`, `email`; recusa e-mail com vínculo em organização (RF-028) |
| `POST /super-admins/{user_id}/disable` | `super_admins:manage` · recente | Desativa; `409` se for o último ativo (RF-012) |
| `POST /super-admins/{user_id}/enable` | `super_admins:manage` · recente | Reativa (RF-030) |

## Configuração de segurança

| Método e rota | Permissão | Descrição |
|---|---|---|
| `GET /security-settings` | `security:manage` (Super Administrador) | Política de senha, tempos de sessão, bloqueio, parâmetros do código, validade de convites e de links de ativação e recuperação |
| `PUT /security-settings` | `security:manage` (Super Administrador) · recente | Aplica no realm do Keycloak pela Admin API, dentro de limites mínimos de segurança |

Limites mínimos que a API não deixa afrouxar: senha ≥ 12 caracteres; código ≥ 6 dígitos
e validade ≤ 15 min; máximo de 10 tentativas antes de bloqueio; sessão máxima ≤ 24 h.

## Auditoria

| Método e rota | Permissão | Descrição |
|---|---|---|
| `GET /audit-events` | `audit:read` ou `audit:read:installation` | Filtros: `q` (nome ou e-mail da pessoa, autora ou alvo), `user_id`, `event_type`, `result`, `date_from`, `date_to`; `limit` (até 200) e `offset`. Escopo em [data-model.md](../data-model.md#quem-lê-o-audit-trail-us6-cenário-2) |
| `POST /audit-events/export` | `audit:read` ou `audit:read:installation` · recente | Mesmos filtros no corpo; CSV com até 10.000 linhas, células protegidas contra fórmulas; registra `audit.exported` (o texto de `q` não é guardado) |

## Ferramenta de operação (fora da API pública)

CLI `cap-admin`, executada pelo pipeline de operação dentro do cluster do cliente, nunca
exposta pela rede:

| Comando | Uso |
|---|---|
| `cap-admin bootstrap-super-admin --email --name` | Provisionamento: cria o Super Administrador inicial e envia o e-mail de boas-vindas (§53.2); não cria organização |
| `cap-admin anonymize-user --email --ticket` | Pedido de esquecimento (LGPD): apaga a conta no Keycloak e as sessões, anonimiza nome, e-mail, convites e trocas de e-mail, remove IP e navegador dos eventos da pessoa; recusa o último Super Administrador ou Administrador ativo (RF-012) |
| `cap-admin audit verify` | Recalcula a cadeia de hash do Audit Trail; sai com código 2 e o `seq` do primeiro registro adulterado |
| `cap-admin reissue-activation --email [--new-email]` | Suporte: reemite o link de ativação de um Super Administrador, inclusive para novo e-mail (caso de borda da spec) |

Toda execução grava evento com `actor_kind = support` e o número do chamado.
