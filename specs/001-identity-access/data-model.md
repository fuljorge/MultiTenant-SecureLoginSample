# Modelo de dados: 001-identity-access

Banco do Control Plane (PostgreSQL 17). O Keycloak mantém o próprio banco (credenciais,
sessões de login e eventos), que não é acessado diretamente pelo Control Plane: toda
interação passa pela Admin REST API.

## Quem guarda o quê

| Dado | Fonte de verdade | Observação |
|---|---|---|
| Senha (hash Argon2) | Keycloak | Nunca trafega pelo Control Plane |
| Código do segundo fator | Keycloak (sessão de autenticação, em memória) | Ver research R1 |
| Bloqueio por tentativas | Keycloak (brute force detection) | Lido pela Admin API para exibir a situação "bloqueado" |
| Nome, e-mail, situação do usuário | Control Plane, espelhado no Keycloak | O Control Plane comanda; o Keycloak recebe |
| Organizações, vínculos, perfis, Super Administradores | Control Plane | Base da autorização (research R2) |
| Convites e trocas de e-mail pendentes | Control Plane | Tokens guardados só como hash |
| Sessões do BFF | Valkey | Ver seção "Sessões" |
| Audit Trail | Control Plane (schema `audit`) | Inclui eventos importados do Keycloak |

## Schema `identity`

### `organization`

| Campo | Tipo | Regras |
|---|---|---|
| `id` | uuid | PK |
| `name` | text | obrigatório, único na instalação |
| `slug` | text | único, kebab-case |
| `status` | enum `pending`, `active`, `suspended`, `cancelled` | `pending` até o primeiro Administrador ativar o acesso (RF-018) |
| `status_changed_at`, `status_changed_by` | timestamptz, uuid | última mudança de situação |
| `version` | integer | trava otimista |
| `created_at`, `created_by` | timestamptz, uuid | `created_by` é sempre um Super Administrador |

Não há organização padrão: a coluna `is_default` sai na migração 0004.

### `user_account`

| Campo | Tipo | Regras |
|---|---|---|
| `id` | uuid | PK; igual ao id do usuário no Keycloak |
| `email` | citext | único na instalação (identificador da pessoa) |
| `name` | text | |
| `status` | enum `invited`, `active`, `disabled` | `blocked` é derivado do Keycloak, não persistido |
| `last_login_at` | timestamptz | atualizado a partir dos eventos de login |
| `anonymized_at` | timestamptz | preenchido no pedido de esquecimento (LGPD) |
| `version` | integer | trava otimista contra edições simultâneas |
| `created_at`, `updated_at` | timestamptz | |

### `super_admin`

Pessoas com o papel de **Super Administrador** (spec §4.8). Antes da revisão de
2026-10-03, `installation_admin` (renomeada na migração 0004).

| Campo | Tipo | Regras |
|---|---|---|
| `user_id` | uuid | PK, FK `user_account` |
| `granted_at`, `granted_by` | timestamptz, uuid | |

- RF-012: uma transação que remove uma linha ou desativa um Super Administrador trava as
  linhas (`SELECT … FOR UPDATE OF super_admin, user_account`) e recusa a operação se não
  sobrar nenhum ativo. A política de UPDATE existe só para permitir o travamento
  (migração 0003).
- RF-028: *trigger* recusa inserir aqui quem tem vínculo `active` ou `pending`, e recusa
  inserir vínculo para quem está aqui.

### `membership`

Vínculo de uma pessoa com uma organização (RF-019).

| Campo | Tipo | Regras |
|---|---|---|
| `id` | uuid | PK |
| `organization_id` | uuid | FK; **RLS** |
| `user_id` | uuid | FK; único com `organization_id` |
| `profile` | enum `administrator`, `agent_designer`, `business_analyst`, `supervisor`, `developer`, `financial_admin` | RF-013 |
| `status` | enum `pending`, `active`, `disabled`, `removed` | `pending` até o primeiro login após o convite; `disabled` na desativação por organização (plano, seção 4.4) |
| `version` | integer | trava otimista |
| `created_at`, `created_by`, `updated_at` | | |

### `invitation`

| Campo | Tipo | Regras |
|---|---|---|
| `id` | uuid | PK |
| `organization_id` | uuid | FK; **RLS** |
| `email` | citext | |
| `profile` | enum (igual a `membership.profile`) | |
| `token_hash` | bytea | SHA-256 de token aleatório de 256 bits; usado só para pessoas já cadastradas |
| `expires_at` | timestamptz | padrão: 72 h |
| `status` | enum `pending`, `accepted`, `expired`, `revoked` | |
| `invited_by`, `created_at`, `accepted_at` | | |

### `email_change_request`

| Campo | Tipo | Regras |
|---|---|---|
| `id` | uuid | PK |
| `user_id` | uuid | FK |
| `new_email` | citext | |
| `token_hash` | bytea | SHA-256 de token aleatório de 256 bits |
| `expires_at` | timestamptz | padrão: 24 h |
| `status` | enum `pending`, `confirmed`, `expired`, `revoked` | |
| `requested_by`, `created_at`, `confirmed_at` | | |

### RLS (Princípio IV)

- Cada transação define `app.user_id`, `app.organization_id` (organização ativa) e
  `app.is_super_admin`; a função `identity.is_super_admin()` só é verdadeira se a pessoa
  também está em `super_admin`.
- Nenhum papel ignora o RLS. As políticas do Super Administrador são específicas:

| Tabela | Membro da organização ativa | Super Administrador |
|---|---|---|
| `organization` | as suas organizações | todas (ler, criar, alterar) |
| `membership` | os da organização ativa e os próprios | só `profile = 'administrator'` |
| `invitation` | os da organização ativa | só `profile = 'administrator'` |
| `user_account` | a própria pessoa e quem tem vínculo com a organização ativa | a própria pessoa, quem tem vínculo de Administrador e os Super Administradores |
| `super_admin` | só a própria linha | todas |
| `email_change_request` | como antes | nenhuma |

- O papel de banco da aplicação não é dono das tabelas e não tem `BYPASSRLS`.

## Schema `audit`

### `audit_event` (append-only, §39)

| Campo | Tipo | Regras |
|---|---|---|
| `seq` | bigint | PK, sequencial; reservado pelo gravador com `nextval` antes do INSERT (um `INSERT … RETURNING` exigiria que o autor pudesse ler o evento pelas políticas de leitura) |
| `occurred_at` | timestamptz | horário do evento na origem |
| `recorded_at` | timestamptz | horário da gravação |
| `organization_id` | uuid nulo | nulo para eventos da instalação (ex.: login antes de escolher organização) |
| `installation_scope` | boolean | verdadeiro para eventos da gestão da instalação (ações do Super Administrador), inclusive os que têm `organization_id`; entra no hash |
| `actor_user_id` | uuid nulo | quem fez |
| `actor_kind` | enum `user`, `system`, `support` | `support` = ação do fornecedor via ferramenta de operação (ex.: reemissão de link) |
| `event_type` | text | catálogo em [contracts/audit-events.md](contracts/audit-events.md) |
| `target_type`, `target_id` | text, text | alvo da ação |
| `result` | enum `success`, `failure`, `denied` | |
| `details` | jsonb | **nunca** contém senha, código, token, link, IP ou e-mail |
| `source` | enum `control_plane`, `keycloak` | |
| `source_event_id` | text | id do evento no Keycloak; único com `source`, evita duplicar na importação |
| `prev_hash`, `hash` | bytea | `hash = SHA-256(prev_hash ‖ JSON canônico do registro)` |

- O papel da aplicação tem apenas `INSERT` e `SELECT`; um *trigger* também recusa
  `UPDATE`, `DELETE` e `TRUNCATE` para qualquer papel. A recusa desfaz a própria
  transação, então a tentativa é registrada no **log do PostgreSQL**, coletado pela
  observabilidade, que gera alerta e o evento `audit.tamper_attempt` em transação
  separada (US6, cenário 3).
- A gravação é serializada travando a linha única de `audit.chain_head` (`FOR UPDATE`),
  que guarda a posição e o hash do último registro. A ponta fica fora do RLS (não tem
  dado de cliente), então o gravador obtém o hash anterior mesmo quando o último
  registro é de outra organização.
- Verificação de integridade: rotina que recalcula a cadeia e alerta em divergência.
- Pedido de esquecimento: o evento não é alterado; os dados pessoais ficam em
  `user_account`, que é anonimizado. O `actor_user_id` continua apontando para um
  registro sem nome nem e-mail.

### Quem lê o Audit Trail (US6, cenário 2)

| Quem | Vê |
|---|---|
| Administrador | eventos da organização ativa (inclusive as ações do Super Administrador sobre ela) e eventos sem organização, fora da gestão da instalação, feitos por pessoas com vínculo não removido com a organização (logins e falhas vindos do Keycloak; migração 0005) |
| Super Administrador | eventos com `installation_scope` e eventos feitos por Super Administradores (migração 0004) |

A origem (`audit_event_origin`) segue a visibilidade do evento.

### `audit_event_origin`

Origem da conexão de cada evento ("de onde", RF-022). Fica **fora da cadeia de hash**
porque é dado pessoal com retenção limitada (LGPD).

| Campo | Tipo | Regras |
|---|---|---|
| `seq` | bigint | PK, FK `audit_event` |
| `source_ip` | inet | |
| `user_agent` | text | |

- Expurgo diário no `cap-worker` remove linhas com mais de 12 meses
  (`audit_origin_retention_days`, padrão 365) e grava um evento `audit.origin_purged`
  com o intervalo expurgado. A cadeia de `audit_event`
  continua verificável.

### `chain_head`

Linha única com a ponta da cadeia (`last_seq`, `last_hash`). Inicia com o hash gênese (32
bytes zero). O papel da aplicação só lê e atualiza.

### `keycloak_event_cursor`

Linha única com o instante do último evento importado (`last_time`, em milissegundos) e os
ids já importados naquele instante (`last_ids`), porque vários eventos podem ter o mesmo
horário. Usado pelo worker da research R4.

## Sessões (Valkey)

| Chave | Conteúdo | TTL |
|---|---|---|
| `cap:sess:{sid}` | `user_id`, `keycloak_sid`, `active_organization_id`, `csrf_token_hash`, tokens do Keycloak **cifrados**, `created_at`, `last_seen_at` | renovado a cada requisição até 30 min de inatividade; nunca passa de 12 h desde `created_at` |
| `cap:user-sess:{user_id}` | conjunto de `sid` do usuário | usado para encerrar todas as sessões de um usuário |

- `sid`: 256 bits aleatórios; o cookie leva o `sid`, a chave no Valkey usa o SHA-256 dele.
- Sessões pertencem à pessoa, não a uma organização; a organização ativa é um atributo
  da sessão e é revalidada contra `membership` a cada requisição.

## Transições de estado

```text
organization.status:   pending ──(1º Administrador ativo)──▶ active ◀──(reativar)── suspended
                          │                                  └───(suspender)───▶ suspended
                          └──(cancelar)──▶ cancelled
user_account.status:   invited ──(1º login)──▶ active ◀──(reativar)── disabled
                                                  └────(desativar)─────▶ disabled
membership.status:     pending ──(1º login / aceite)──▶ active ◀──(reativar)── disabled
                                                          ├──(desativar)──▶ disabled
                                                          └──(remover)────▶ removed
invitation.status:     pending ──▶ accepted | expired | revoked
email_change_request:  pending ──▶ confirmed | expired | revoked
```
