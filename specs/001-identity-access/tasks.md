# Tarefas: Identidade, Autenticação e Controle de Acesso de Usuários

- **ID:** 001-identity-access
- **Spec / Plano:** [spec.md](spec.md) · [plan.md](plan.md) (ambos aprovados em
  2026-10-03, revisão do Super Administrador)
- **Status:** Aprovadas <!-- Rascunho | Aprovadas -->
- **Emenda 2026-10-04:** nova Fase 10 (T093–T099: reautenticação recente e medidor de
  força), análise (A20, A21) e rastreabilidade (RF-031, RF-032).
- **Revisão 2026-10-03:** nova Fase 7 (migração para o Super Administrador, T080–T090),
  US5 reescrita (T060–T064, T091, T092), ajustes em T065 e T066, dependências, análise
  (A16–A19) e rastreabilidade.
- **Criado em:** 2026-10-02
- **Aprovado por / em:** Fulvio Jorge da Silva / 2026-10-04 (emenda ASVS; versões
  anteriores aprovadas em 2026-10-02 e 2026-10-03)

## Formato

`- [ ] T001 [P] [US1] Descrição com caminho/do/arquivo`

- `[P]`: pode rodar em paralelo (arquivos diferentes, sem dependência pendente).
- `[US1]`: história da spec atendida (fases de setup e fundação não levam marcador).
- Testes vêm antes da implementação correspondente e devem falhar antes dela.

Caminhos abreviados: `cp/` = `services/control-plane/`, `cpkg/` =
`services/control-plane/src/cap_control_plane/`, `studio/` = `apps/studio/`.

## Fase 1 — Setup

- [x] T001 Criar o monorepo: `pyproject.toml` (workspace uv), `pnpm-workspace.yaml`,
  `.editorconfig` e as pastas `apps/`, `services/`, `packages/`, `infra/`, `tests/`
- [x] T002 [P] Criar o projeto do Control Plane em `cp/pyproject.toml` (FastAPI,
  Pydantic v2, SQLAlchemy 2, Alembic, Authlib, httpx, redis-py, OpenTelemetry) com
  Ruff (incluindo regras `S`) e mypy estrito; app mínima com `/healthz` em `cpkg/main.py`
- [x] T003 [P] Criar o Studio em `studio/` (Next.js, TypeScript estrito, Tailwind,
  shadcn/ui, TanStack Query/Table, i18next, ESLint + Prettier, Vitest) com os tokens do
  media kit em `studio/src/styles/tokens.css` e tema escuro padrão
- [x] T004 [P] Configurar Playwright em `tests/e2e/` (`playwright.config.ts` com
  projetos desktop e celular; helper que lê e-mails no Mailpit)
- [x] T005 [P] Criar `.gitleaks.toml` e `.pre-commit-config.yaml` (gitleaks, Ruff,
  Prettier)
- [x] T006 Criar `infra/compose/docker-compose.yml` com PostgreSQL 17 (databases `cap` e
  `keycloak`), Valkey, OpenBao (modo dev, Transit habilitado) e Mailpit
- [x] T007 Criar `.github/workflows/ci.yml` com jobs: Ruff + mypy + pytest unitário;
  ESLint + `tsc` + Vitest; gitleaks; Trivy em modo filesystem

## Fase 2 — Fundação (bloqueia as histórias)

### Keycloak

- [x] T008 **Verificação bloqueante R1** da extensão `keycloak-2fa-email-authenticator`:
  (1) o código é guardado em texto claro na sessão de autenticação? (2) emite eventos de
  envio, reenvio e falha? (3) o reenvio invalida o código anterior? (4) qual versão do
  Keycloak é suportada? (5) falhas de código contam para o bloqueio por tentativas do
  Keycloak (RF-003)? Registrar o resultado em `research.md` (R1). Se algum item
  falhar sem correção possível, **parar** e levar o plano B para decisão
- [x] T009 Criar `infra/keycloak/Dockerfile` (imagem oficial na versão definida em T008,
  build otimizado) e `infra/keycloak/providers.lock` com URL, versão e SHA-256 da
  extensão; o build falha se o checksum divergir
- [x] T010 [P] Criar o tema `infra/keycloak/themes/cap/` (login: CSS com os tokens,
  `messages_pt_BR.properties`; e-mail: templates PT-BR de código, convite/boas-vindas e
  recuperação de senha)
- [x] T011 Criar `infra/keycloak/realm/cap-realm.yaml` conforme o plano (§4.9): fluxo
  senha → código, registro desligado, login por e-mail, brute force, política de senha
  com lista do SecLists (baixada com checksum), tempos de sessão e de links, eventos por
  7 dias, clientes `cap-control-plane` e `cap-admin-bridge`; adicionar Keycloak e
  keycloak-config-cli ao compose
- [x] T012 [P] Teste de integração do realm em `cp/tests/integration/keycloak/test_realm.py`:
  login exige código, registro desligado, política de senha recusa senha da lista,
  bloqueio após 5 falhas (de senha e de código); o realm não tem usuários
  administrativos além da conta de serviço `cap-admin-bridge`, nem clientes além dos
  previstos (RF-024)

### Base do Control Plane

- [x] T013 Criar fixtures de teste em `cp/tests/conftest.py` com Testcontainers
  (PostgreSQL, Valkey, OpenBao, Mailpit, Keycloak com a imagem e o realm do projeto)
- [x] T014 [P] Criar `cpkg/core/settings.py`, `cpkg/core/secrets.py` (leitura de segredos
  e cifra/decifra via OpenBao Transit) e `cpkg/core/telemetry.py` (OpenTelemetry)
- [x] T015 [P] Teste em `cp/tests/unit/core/test_logging.py`: senha, código, token,
  link, e-mail e IP completos são redigidos nos logs
- [x] T016 Criar `cpkg/core/logging.py` (logs estruturados com redação de campos
  sensíveis)
- [x] T017 [P] Criar `cpkg/core/email.py` (SMTP com templates PT-BR para os avisos do
  Control Plane)

### Banco e isolamento

- [x] T018 Teste de integração de RLS em `cp/tests/integration/db/test_rls.py`: sem
  contexto não lê nada; com organização A não lê `membership`/`invitation` de B;
  Administrador da instalação lê todas; papel da aplicação não tem `BYPASSRLS`
- [x] T019 Criar `cpkg/core/db.py` (engine, sessão, `SET LOCAL app.user_id`,
  `app.organization_id`, `app.is_installation_admin` por transação) e o papel de banco da
  aplicação
- [x] T020 Migração Alembic do schema `identity` em `cp/migrations/` (tabelas de
  [data-model.md](data-model.md), enums, índices, políticas RLS)

### Audit Trail

- [x] T021 [P] Testes unitários da cadeia em `cp/tests/unit/audit/test_chain.py`
  (JSON canônico, encadeamento, detecção de adulteração)
- [x] T022 Teste de integração em `cp/tests/integration/audit/test_audit_store.py`:
  `UPDATE`/`DELETE`/`TRUNCATE` recusados; gravações concorrentes mantêm a cadeia;
  `details` sem campos proibidos
- [x] T023 Migração Alembic do schema `audit` (`audit_event`, `audit_event_origin`,
  `keycloak_event_cursor`, privilégios só `INSERT`/`SELECT`, trigger anti-alteração)
- [x] T024 Criar `cpkg/audit/chain.py`, `cpkg/audit/writer.py` (gravação serializada
  com bloqueio consultivo) e `cpkg/audit/verify.py`
- [x] T025 Configurar o PostgreSQL do compose para registrar no log as recusas do
  trigger e documentar em `infra/README.md` a regra de alerta que gera
  `audit.tamper_attempt` (coleta pela observabilidade)

### Permissões e sessões

- [x] T026 [P] Testes unitários da matriz em `cp/tests/unit/identity/test_permissions.py`:
  tabela perfil × permissão igual à seção 5.1 da spec, escopos de Administrador,
  negação por padrão
- [x] T027 Criar `cpkg/identity/permissions.py` (catálogo, matriz, dependência
  `require(permission)` que responde `403` e grava `access.denied`), incluindo
  `costs:read:own` sem uso nesta feature
- [x] T028 [P] Testes de integração em `cp/tests/integration/identity/test_sessions.py`:
  criação, renovação até 30 min de inatividade, limite de 12 h, revogação de todas as
  sessões do usuário, tokens cifrados no Valkey, `sid` guardado como hash
- [x] T029 Criar `cpkg/identity/sessions.py`
- [x] T030 [P] Testes de integração do cliente da Admin API em
  `cp/tests/integration/identity/test_keycloak_admin.py` (criar usuário, ações por
  e-mail, desabilitar, logout, ler eventos e estado de bloqueio)
- [x] T031 Criar `cpkg/identity/keycloak_admin.py` (conta de serviço, httpx, timeouts e
  retentativas)

## Fase 3 — US1: Login com segundo fator por e-mail (P1) — MVP

**Objetivo:** usuário cadastrado entra com senha e código, usa a plataforma e sai.
**Teste independente:** spec, US1.

### Testes

- [x] T032 [P] [US1] Testes de integração do BFF em
  `cp/tests/integration/identity/test_bff_auth.py`: `state` e PKCE, cookie `__Host-`
  com `HttpOnly`/`Secure`/`SameSite=Lax`, CSRF recusado sem cabeçalho, logout,
  back-channel logout encerra a sessão do BFF; usuário lista as próprias sessões e
  encerra uma delas (RF-006)
- [x] T033 [P] [US1] Testes de integração do worker em
  `cp/tests/integration/audit/test_keycloak_ingestor.py`: importa eventos sem duplicar,
  mapeia para o catálogo, troca de senha encerra sessões do BFF e envia aviso; com o
  SMTP indisponível, o login não é concluído e o Keycloak registra o erro no log
- [x] T034 [P] [US1] E2E em `tests/e2e/login.spec.ts`: login com código lido no Mailpit;
  código incorreto, expirado e reenviado; bloqueio após 5 falhas; mensagem genérica;
  logout; inatividade (tempo curto no ambiente de teste); recuperação de senha com aviso
  e sessões encerradas; viewport de celular
- [x] T035 [P] [US1] Teste de enumeração em `cp/tests/integration/identity/test_enumeration.py`:
  mesma resposta e tempo semelhante para e-mail existente e inexistente (login e
  recuperação)

### Implementação

- [x] T036 [US1] Criar `cpkg/identity/oidc.py` (Authlib, Authorization Code + PKCE) e
  `cpkg/identity/api/auth.py` (`/auth/login`, `/auth/callback`, `/auth/logout`,
  `/auth/backchannel-logout`, `/auth/password`)
- [x] T037 [US1] Criar o middleware de sessão e CSRF em `cpkg/identity/middleware.py` e
  a rota `GET /me` em `cpkg/identity/api/me.py`
- [x] T038 [US1] Criar `cpkg/audit/keycloak_ingestor.py` (leitura a cada 5 s, cursor,
  deduplicação, mapeamento; em troca de senha remove sessões do BFF e envia aviso;
  métricas de logins, falhas e bloqueios; alerta de atraso do cursor — RNF-004)
- [x] T039 [US1] Criar `GET /me/sessions` e `DELETE /me/sessions/{id}` em
  `cpkg/identity/api/me.py`
- [x] T040 [US1] No Studio: `studio/src/lib/auth/` (consulta a `/me`, envio do token
  CSRF, redirecionamento ao login), layout protegido, botão Sair, link "Trocar senha" e
  tela `studio/src/app/(app)/conta/sessoes/`
- [x] T041 [US1] Gerar o cliente em `packages/api-client/` (orval) e adicionar ao CI a
  verificação de divergência com o OpenAPI

**Checkpoint:** US1 funciona e é testável sozinha (usuário criado por fixture).

## Fase 4 — US2: Primeiro acesso do Administrador inicial (P1)

### Testes

- [x] T042 [P] [US2] Teste de integração em `cp/tests/integration/cli/test_bootstrap.py`:
  `bootstrap-admin` cria a organização padrão, o usuário no Keycloak, o vínculo e o
  escopo de instalação e envia o e-mail; `reissue-activation` com e sem novo e-mail;
  eventos com `actor_kind = support`
- [x] T043 [P] [US2] E2E em `tests/e2e/activation.spec.ts`: link de boas-vindas → define
  senha → login com código → tela inicial; link já usado ou expirado é recusado

### Implementação

- [x] T044 [US2] Criar `cpkg/cli/cap_admin.py` (`bootstrap-admin`,
  `reissue-activation`, com número do chamado obrigatório no segundo)
- [x] T045 [US2] No callback de login, ativar usuário e vínculos `pending` e gravar
  `user.activated`

**Checkpoint:** instalação nova entrega o Administrador inicial funcionando.

## Fase 5 — US3: Gestão de usuários pelo Administrador (P1)

### Testes

- [x] T046 [P] [US3] Testes de integração em `cp/tests/integration/identity/test_users.py`:
  convite de pessoa nova e de pessoa já cadastrada; revogação de convite; mudança de
  perfil vale na próxima requisição; desativação revoga sessões em até 60 s;
  reativação; último Administrador da instalação (inclusive com duas operações
  simultâneas); edição concorrente responde `412`; listagem com filtros
- [x] T047 [P] [US3] Testes de integração em `cp/tests/integration/identity/test_email_change.py`:
  confirmação pelo novo e-mail, sessões encerradas, aviso ao antigo, token de uso
  único e expirado
- [x] T048 [P] [US3] Testes de integração em `cp/tests/integration/identity/test_security_settings.py`:
  leitura e gravação no realm, incluindo a validade de convites e links de ativação
  (RF-010); limites mínimos recusados (RF-007)
- [x] T049 [P] [US3] E2E em `tests/e2e/user-management.spec.ts`: Administrador convida →
  pessoa ativa → Administrador muda perfil → desativa → pessoa perde acesso

### Implementação

- [x] T050 [US3] Criar `cpkg/identity/service/users.py` e `cpkg/identity/service/invitations.py`
  (regras de convite, ativação, desativação, último Administrador, trava otimista)
- [x] T051 [US3] Criar `cpkg/identity/service/email_change.py`
- [x] T052 [US3] Criar as rotas de usuários, convites e troca de e-mail em
  `cpkg/identity/api/users.py`
- [x] T053 [US3] Criar `cpkg/identity/api/security_settings.py`
- [x] T054 [US3] No Studio: `studio/src/app/(app)/admin/usuarios/` (lista com filtros,
  convite, detalhe, alterar perfil, desativar/reativar, trocar e-mail, encerrar
  sessões) e `studio/src/app/(app)/admin/seguranca/`

**Checkpoint:** Administrador gerencia a equipe sem o fornecedor.

## Fase 6 — US4: Acesso controlado por perfil (P1)

### Testes

- [x] T055 [P] [US4] Teste orientado por tabela em
  `cp/tests/integration/identity/test_route_permissions.py`: para cada rota da feature e
  cada perfil, resposta esperada (`2xx` ou `403`) e `access.denied` gravado; falha se
  houver rota sem permissão declarada; nenhum perfil ou rota dá acesso ao fornecedor
  (RF-024)
- [x] T056 [P] [US4] Teste de componente em `studio/src/components/nav/nav.test.tsx`:
  menus exibidos conforme as permissões de `/me`
- [x] T057 [P] [US4] E2E em `tests/e2e/profiles.spec.ts`: Business Analyst não vê a
  administração e recebe `403` ao chamar a API diretamente

### Implementação

- [x] T058 [US4] Garantir `require()` em todas as rotas e registrar no CI o teste de
  rota sem permissão
- [x] T059 [US4] Navegação do Studio guiada pelas permissões em
  `studio/src/components/nav/`

**Checkpoint:** todas as histórias P1 entregues (MVP).

## Fase 7 — Migração para o Super Administrador (revisão 2026-10-03; bloqueia a US5)

Adapta o que US1–US4 entregaram (plano, seção 12). Ao fim desta fase, o Administrador da
instalação não existe mais e o Super Administrador não lê nada de dentro das
organizações.

### Testes

- [x] T080 [P] Testes de unidade em `cp/tests/unit/identity/test_permissions.py` e
  `cp/tests/unit/identity/test_route_permissions.py`: permissões de instalação
  (`SUPER_ADMIN_PERMISSIONS`) e de organização são disjuntas; o Super Administrador não
  recebe nenhuma permissão de organização; nenhum perfil recebe permissão de
  instalação; toda permissão pertence a algum perfil ou ao Super Administrador
  (RF-016, RF-024, RF-028)
- [x] T081 [P] Teste de integração em `cp/tests/integration/identity/test_super_admin_rls.py`:
  consultas direto no banco com o contexto do Super Administrador veem todas as
  organizações, só vínculos e convites de perfil `administrator`, só pessoas que são
  Administradores ou Super Administradores e nenhuma troca de e-mail; inserir vínculo
  de outro perfil é recusado; o *trigger* recusa vínculo para Super Administrador e
  Super Administrador para quem tem vínculo ativo (RF-028, RNF-001)
- [x] T082 [P] Teste de integração em `cp/tests/integration/test_migration_0004.py`: a
  partir do estado da 0003 com Administrador da instalação, vínculos e organização
  padrão, a 0004 cria `super_admin`, marca os vínculos dele como `removed`, grava
  `super_admin.converted`, deixa as organizações existentes `active`, remove
  `is_default` e mantém a cadeia de auditoria válida
- [x] T083 [P] Ajustar os testes existentes ao novo modelo: `tests/support/people.py`
  (`create_person(super_admin=...)`), `tests/support/seed_person.py` (`--super-admin`),
  `test_activation.py` (US2 cria o Super Administrador inicial, sem organização),
  `test_users.py` (desativação por vínculo, último Administrador por organização),
  `test_security_settings.py` (só Super Administrador), a matriz de
  `test_route_permissions.py` com o Super Administrador como principal (`403` e
  `access.denied` em toda rota de organização) e os E2E `activation.spec.ts`,
  `user-management.spec.ts` e `profiles.spec.ts`

### Implementação

- [x] T084 Migração `cp/migrations/versions/0004_super_admin.py` conforme
  [data-model.md](data-model.md): `super_admin` (de `installation_admin`), função
  `identity.is_super_admin()` e políticas por tabela no lugar de
  `has_installation_scope()`, *triggers* do RF-028, `organization.status` e colunas de
  situação, `membership.status` com `disabled`, `audit_event.installation_scope`,
  remoção de `is_default` e conversão dos dados existentes
- [x] T085 Permissões e principal: `cpkg/identity/permissions.py`
  (`SUPER_ADMIN_PERMISSIONS`, `effective_permissions` sem mistura), `cpkg/core/db.py`
  (`DbContext.is_super_admin`), `cpkg/identity/authz.py` e `cpkg/identity/directory.py`
  (Super Administrador sem organização; organização precisa estar `active` na
  revalidação de cada requisição)
- [x] T086 Login e `/me`: Super Administrador entra sem organização ativa;
  `GET /me` informa o tipo de principal; regenerar o OpenAPI e o cliente TypeScript
- [x] T087 Usuários (US3) por vínculo: `cpkg/identity/service/users.py` e
  `cpkg/identity/api/users.py` com desativação e reativação do vínculo (conta só sem
  outro vínculo ativo), último Administrador por organização com travamento (RF-012),
  troca de e-mail recusada (`409`) para quem pertence a outras organizações
- [x] T088 Auditoria: `installation_scope` em `cpkg/audit/chain.py` e
  `cpkg/audit/writer.py` (entra no hash); eventos do Super Administrador gravam a
  organização afetada e `installation_scope = true`
- [x] T089 CLI: `cap-admin bootstrap-super-admin` (sem organização) e
  `reissue-activation` para Super Administrador, em `cpkg/cli/cap_admin.py`; atualizar
  `infra/README.md`
- [x] T090 Studio: menus por tipo de principal (Organizações, Super Administradores e
  Segurança para o Super Administrador), cabeçalho com "Super Administrador" no lugar da
  organização, página inicial do Super Administrador; atualizar
  `studio/src/components/nav/nav.test.tsx`

**Checkpoint:** todos os testes existentes passam no novo modelo, e o Super
Administrador recebe `403` em toda rota de organização.

## Fase 8 — US5: Gestão de organizações pelo Super Administrador (P1)

### Testes

- [x] T060 [P] [US5] Testes de integração em `cp/tests/integration/identity/test_organizations.py`:
  convite de organização para pessoa nova e para pessoa já cadastrada (organização
  `pending`, ativa quando o Administrador ativa o acesso); só o Super Administrador
  cria (Administrador de organização recebe `403` e `access.denied`); lista com
  filtros; renomear com `If-Match`; reenviar e cancelar convite pendente; convite para
  e-mail de Super Administrador recusado; convidar, desativar e reativar Administrador,
  com `409` para o último ativo; suspender (sessões da organização removidas, acesso
  negado na próxima requisição, CS-009) e reativar (novo login); pessoa com outra
  organização ativa perde só a suspensa; troca de organização só para vínculo válido e
  organização ativa
- [x] T061 [P] [US5] Teste de isolamento em `cp/tests/integration/identity/test_cross_org.py`:
  para cada rota, usuário de A acessando recurso de B → `404`/`403` e `access.denied`
- [x] T091 [P] [US5] Testes de integração em `cp/tests/integration/identity/test_super_admins.py`:
  convidar, desativar e reativar Super Administrador; `409` para o último ativo
  (RF-012, RF-030); convite recusado para e-mail com vínculo em organização (RF-028)
- [x] T062 [P] [US5] E2E em `tests/e2e/specs/organizations.spec.ts`: o Super
  Administrador convida uma organização; o convidado ativa pelo e-mail (Mailpit) e
  entra como Administrador; o Super Administrador vê a organização ativa e o seu
  Administrador, recebe "Sem permissão" em Usuários e suspende a organização, e o
  Administrador perde o acesso; pessoa com duas organizações troca pelo seletor e vê só
  os dados da ativa; viewport de celular

### Implementação

- [x] T063 [US5] Criar `cpkg/identity/service/organizations.py` e
  `cpkg/identity/api/organizations.py` (rotas de organizações e dos seus
  Administradores do contrato) e `PUT /me/active-organization`
- [x] T092 [US5] Criar `cpkg/identity/service/super_admins.py` e
  `cpkg/identity/api/super_admins.py`
- [x] T064 [US5] No Studio: `studio/src/components/org-switcher/` (só aparece com mais
  de uma organização), `studio/src/app/(app)/admin/organizacoes/` (lista, convite,
  detalhe com Administradores, suspender e reativar) e
  `studio/src/app/(app)/admin/super-administradores/`

**Checkpoint:** todas as histórias P1 da spec revisada entregues.

## Fase 9 — US6: Auditoria de acessos (P2)

### Testes

- [x] T065 [P] [US6] Testes de integração em `cp/tests/integration/audit/test_audit_api.py`:
  filtros; o Administrador vê os eventos da organização, inclusive as ações do Super
  Administrador sobre ela; o Super Administrador vê só os de `installation_scope` ou
  feitos por Super Administradores; exportação CSV grava `audit.exported`
- [x] T066 [P] [US6] Teste de cobertura em `cp/tests/unit/audit/test_event_catalog.py`
  (estático: não precisa de serviços):
  cada tipo de [contracts/audit-events.md](contracts/audit-events.md) é produzido por
  algum cenário, com os campos do RF-022 (CS-006)
- [x] T067 [P] [US6] Teste de integração do expurgo em
  `cp/tests/integration/audit/test_origin_purge.py`: remove origem antiga, grava
  `audit.origin_purged`, cadeia continua válida

### Implementação

- [x] T068 [US6] Criar `cpkg/audit/api.py` (consulta e exportação)
- [x] T069 [US6] Criar `cpkg/audit/purge.py` (rotina diária no processo do worker) e o
  comando `cap-admin audit verify`
- [x] T070 [US6] No Studio: `studio/src/app/(app)/admin/auditoria/` (filtros, tabela,
  exportação)

## Fase final — Acabamento

- [x] T071 [P] Teste em `cp/tests/integration/test_no_secret_leak.py` e etapa do CI que
  varre os logs da execução E2E em busca de senhas, códigos, tokens e links (CS-007)
- [x] T072 [P] Criar o comando `cap-admin anonymize-user` (pedido de esquecimento,
  LGPD) com teste em `cp/tests/integration/cli/test_anonymize.py`
- [x] T073 [P] Criar `services/control-plane/Dockerfile` e `apps/studio/Dockerfile`;
  adicionar ao CI o build e a varredura Trivy das três imagens (Control Plane, Studio,
  Keycloak), falhando com vulnerabilidade alta ou crítica sem mitigação registrada
- [x] T074 Adicionar ao CI o job E2E (sobe o compose, roda Playwright desktop e celular)
- [x] T075 Medir as metas do RNF-007 com `tests/e2e/perf/login-timing.spec.ts` (p95 de
  50 logins: tempo de cada etapa, chegada do e-mail com o código, troca de organização)
  e registrar o resultado no PR
- [x] T076 Preencher `specs/001-identity-access/checklists/asvs-l2.md` (capítulos V2, V3
  e V4 do OWASP ASVS)
- [x] T077 Atualizar `AGENTS.md` (seção 9: comandos de instalação, ambiente local,
  testes e lint) e o estado do projeto
- [x] T078 [P] Teste de contrato em `cp/tests/contract/test_identity_contract.py`: toda
  rota de [contracts/identity-api.md](contracts/identity-api.md) existe no OpenAPI com o
  método e a permissão indicados, e o OpenAPI não tem rota fora do contrato
- [ ] T079 Roteiro de validação com usuários em
  `specs/001-identity-access/checklists/validacao-usuario.md` para CS-001, CS-002 e
  CS-003 (tempos de ativação, convite e login medidos com pessoas reais), executado na
  etapa de conclusão

## Fase 10 — Reautenticação recente e medidor de força (emenda 2026-10-04)

### Testes

- [x] T093 [P] Teste unitário em `cp/tests/unit/identity/test_route_permissions.py`: as
  rotas do RF-031 (lista no contrato) declaram `require_recent_auth`, e nenhuma outra
- [x] T094 [P] Testes de integração em `cp/tests/integration/identity/test_recent_auth.py`:
  ação sensível com login há mais de 15 min responde `401 reauth_required` e não muda
  nada; com login recente, segue; `GET /auth/login?reauth=1` envia `prompt=login` e
  `max_age=0` e substitui a sessão anterior; `GET /auth/password` envia `max_age=0`;
  renovar tokens não muda o `auth_time`
- [x] T095 [P] Teste de componente em `studio/src/lib/auth/reauth.test.ts`: o erro
  `reauth_required` leva à nova autenticação com a tela atual como retorno

### Implementação

- [x] T096 `auth_time` na sessão (`cpkg/identity/sessions.py`, callback), dependência
  `require_recent_auth` em `cpkg/identity/authz.py`, `reauth=1` e `max_age=0` em
  `cpkg/identity/oidc.py` e `cpkg/identity/api/auth.py`; aplicar nas rotas do RF-031 e
  marcar no contrato `contracts/identity-api.md`
- [x] T097 Studio: tratamento de `reauth_required` no cliente e na interface (mensagem ao
  voltar); regenerar o cliente
- [x] T098 Medidor de força no tema `cap` do Keycloak (`infra/keycloak/themes/cap/`), nas
  telas de definir e trocar senha; E2E em `tests/e2e/specs/activation.spec.ts` confere o
  indicador; teste em `cp/tests/unit/test_keycloak_theme.py`
- [x] T099 Atualizar `checklists/asvs-l2.md` (2.1.6, 2.1.8, 3.7.1 e pendências) e o E2E
  `tests/e2e/specs/user-management.spec.ts` com uma ação sensível depois da nova
  autenticação

**Checkpoint:** pendências P1 e P2 do checklist ASVS resolvidas.

## Dependências e ordem

- Setup (T001–T007) → Fundação (T008–T031) → US1 → US2 → US3 → US4 → Migração para o
  Super Administrador (T080–T090) → US5 → US6 → Acabamento.
- Na migração: T084 → T085 → T086 → T087; T088 e T089 depois de T084; T090 depois de
  T086 (cliente gerado).
- **T008 bloqueia T009–T012** e, por consequência, todas as histórias.
- Na Fundação: T013 antes dos testes de integração; T018 → T019 → T020; T022 → T023 →
  T024; T026 → T027; T028 → T029; T030 → T031.
- US2 depende de US1 (callback de login). US3 depende de US2 (Administrador existente).
  US4 só fecha depois que as rotas de US1–US3 existem. US5 e US6 dependem da migração
  (T080–T090) e podem andar em paralelo depois dela.
- T041 (cliente gerado) antes das telas do Studio que consomem a API (T040 em diante).

## Análise (preenchida antes de implementar)

Executada em 2026-10-02 sobre spec, plano, pesquisa, modelo de dados, contratos, tarefas
e constituição v1.1.0. Revisada em 2026-10-03 para o Super Administrador (A16–A19).

| Verificação | Resultado |
|---|---|
| Todo RF/RNF tem tarefa | ✅ após os ajustes A1–A8 (matriz abaixo) |
| Toda tarefa remete a requisito/história | ✅ Setup e Fundação servem a todas as histórias; demais tarefas marcadas com `[USn]` ou com o requisito |
| Spec, plano e tarefas consistentes (termos, escopo) | ✅ após a decisão do achado A9 |
| Nenhum `[PRECISA ESCLARECIMENTO]` restante | ✅ |
| Conformidade com a constituição | ✅ nenhuma violação |

### Achados

| # | Severidade | Achado | Resolução |
|---|---|---|---|
| A1 | Alta | RF-024 (fornecedor sem acesso) não tinha tarefa nem teste | Incluído em T012 (realm sem administradores ou clientes extras) e T055 |
| A2 | Alta | Sem verificação de que falhas de **código** contam para o bloqueio (RF-003); depende da extensão | Item (5) em T008; T012 testa bloqueio por senha e por código |
| A3 | Média | RNF-004: faltavam métricas de logins, falhas e bloqueios e o alerta de falha de envio de e-mail (caso de borda da spec) | Incluído em T033 e T038; o alerta de falha de envio foi reclassificado no A14 |
| A4 | Média | RF-006: listar e encerrar as próprias sessões sem teste | Incluído em T032 |
| A5 | Média | RF-009 e caso de borda: remoção de organização com a pessoa logada sem teste | Incluído em T060 |
| A6 | Média | RF-010: validade de convites e links não era configurável pela tela de segurança | Incluído em T048; o contrato `PUT /security-settings` passa a cobrir esses prazos |
| A7 | Média | Princípio VIII: o plano previa comparar o OpenAPI com o contrato, mas não havia tarefa | Nova T078 |
| A8 | Baixa | CS-001 a CS-003 medem tempo de pessoas reais e não têm verificação; RNF-007 não media a chegada do e-mail | Nova T079 (validação com usuários); T075 ampliada. Trivy agora falha com vulnerabilidade alta ou crítica (T073, Princípio X) |
| A9 | Média | **RF-015** (custos só dos próprios agentes) é requisito da spec, mas o plano entrega só a permissão e adia o filtro para a feature do Dashboard de Custos, porque "responsável pelo agente" ainda não existe | **Decidido em 2026-10-02 (Fulvio Jorge da Silva):** RF-015 concluído na feature do Dashboard de Custos; registrado na spec |
| A10 | Baixa | US2, cenário 3 (ver a ativação no Audit Trail) depende da tela de auditoria, que é da US6 (P2) | Aceito: até a US6, a verificação é feita pela API em T042 |
| A11 | Baixa | O evento `audit.tamper_attempt` depende da coleta de logs da observabilidade, que ainda não existe | Aceito: a tentativa já fica no log do PostgreSQL (US6, cenário 3); o alerta automático vem com a observabilidade |
| A12 | Baixa | Dados de usuários desativados não têm prazo de retenção (RNF-002) | Aceito: ficam até pedido de esquecimento, para preservar a auditoria; revisar com o DPO junto da retenção de 12 meses do plano |
| A13 | Processo | Esta branch parte de `docs/constitution-security`; a stack §3.16 cita o Playwright da §3.1, que está na branch `docs/stack-playwright` | Ordem de merge: `docs/constitution-security` → `docs/stack-playwright` → `001-identity-access` |
| A14 | Média | T008: a extensão de código por e-mail não gera evento de envio e reenvio, nem de falha de envio | **Decidido em 2026-10-02 (Fulvio Jorge da Silva):** envio e reenvio saem do RF-021 (spec atualizada; `auth.code_sent` retirado do catálogo). O alerta de falha de envio vem do log de erro do Keycloak, coletado pela observabilidade (mesma situação do A11) |
| A16 | **Crítica** | Revisão 2026-10-03: o código entregue em US1–US4 dá ao Administrador da instalação Administrador implícito em todas as organizações e ignora o RLS (`has_installation_scope()`), o que viola RF-016 e RF-028 da spec revisada | Fase 7 (T080–T090) antes da US5; checkpoint exige `403` do Super Administrador em toda rota de organização |
| A17 | Média | CS-008 (convite de organização em menos de 1 min; ativação em menos de 5 min) mede tempo de pessoas reais | Incluído no roteiro de validação com usuários (T079) |
| A18 | Média | RF-029 (billing de todas as organizações) só cria a permissão, porque as telas são da feature de Faturamento | Mesma solução do A9, já registrada na spec (Fora de escopo e RF-029) |
| A20 | Alta | Checklist ASVS (T076): sem reautenticação antes de ações sensíveis (2.1.6, 3.7.1) | **Decidido em 2026-10-04 (Fulvio Jorge da Silva):** implementar na Fase 1 (RF-031; T093–T097, T099) |
| A21 | Média | Checklist ASVS: sem medidor de força da senha (2.1.8); P3 a P5 dependem do provisionamento | **Decidido em 2026-10-04:** medidor nesta feature (RF-032; T098); P3 a P5 viraram requisitos do provisionamento (§53.2) |
| A19 | Processo | A revisão é uma mudança de escopo relevante, que pelo `docs/sdd/README.md` seria uma feature nova | **Decidido em 2026-10-03 (Fulvio Jorge da Silva):** revisão dentro da 001, com nova aprovação de spec, plano e tarefas |
| A15 | **Crítica** | T012: com brute force ligado, falhas de código não contam para o bloqueio e a extensão não limita tentativas; o código pode ser testado sem limite (viola RF-002, RF-003 e Princípio X) | **Corrigido em 2026-10-02** (decisão: patch na extensão). Causa: o Keycloak só conta falhas das categorias `password`, `otp` e códigos de recuperação. Patch `infra/keycloak/patches/0001-limit-email-code-attempts.patch` aplicado no build sobre o commit fixado da v26.5.0: tentativas contadas sempre, código invalidado após 5 erros, falha registrada como `otp`. Validado pelos 71 testes da extensão e pelos testes do realm. Correção proposta ao projeto original no [PR #155](https://github.com/mesutpiskin/keycloak-2fa-email-authenticator/pull/155) (issue #146); remover o patch quando for publicada |

### Matriz de rastreabilidade

| Requisito | Tarefas |
|---|---|
| RF-001 login + código | T008, T011, T012, T034, T036 |
| RF-002 regras do código | T008, T011, T034 |
| RF-003 bloqueio | T008, T011, T012, T034 |
| RF-004 recuperação de senha | T011, T034 |
| RF-005 troca de senha encerra sessões e avisa | T033, T034, T038 |
| RF-006 sessões | T028, T029, T032, T034, T039, T040 |
| RF-007 política de senha configurável | T011, T012, T048, T053, T054, T083 |
| RF-008 Super Administrador inicial | T042–T045, T083, T089 |
| RF-009 gestão de usuários | T046, T047, T049–T052, T054, T060, T083, T087 |
| RF-010 convites de uso único e validade | T011, T042, T046, T048 |
| RF-011 desativação encerra sessões | T046, T049, T050, T087 |
| RF-012 último Administrador e último Super Administrador | T046, T050, T060, T083, T087, T091 |
| RF-013 perfis fixos | T026, T027 |
| RF-014 matriz aplicada no servidor | T026, T027, T055–T059 |
| RF-015 custos dos próprios agentes | T027 (permissão) — ver A9 |
| RF-016 Administrador só na organização | T026, T080, T085 |
| RF-017 perfil vale na próxima ação | T046, T050 |
| RF-018 só o Super Administrador cria organizações | T060, T062, T063, T064 |
| RF-019 várias organizações e troca | T060, T062–T064 |
| RF-020 isolamento entre organizações | T018–T020, T061 |
| RF-021 eventos auditados | T022–T024, T033, T038, T066 |
| RF-022 campos do evento | T022, T066 |
| RF-023 consulta e exportação | T065, T068, T070, T088 |
| RF-024 fornecedor só como Super Administrador | T012, T055, T080, T083 |
| RF-025 listar e editar organizações | T060, T063, T064 |
| RF-026 suspender e reativar | T060, T062, T063, T064, T085 |
| RF-027 Administradores das organizações | T060, T063, T064 |
| RF-028 Super Administrador fora das organizações | T080, T081, T083, T084, T085 |
| RF-029 billing de todas as organizações | T080 (permissão) — ver A18 |
| RF-030 gestão de Super Administradores | T091, T092, T064 |
| RF-031 reautenticação recente | T093–T097, T099 |
| RF-032 medidor de força da senha | T098 |
| RNF-001 multi-tenant | T018–T020, T061, T081 |
| RNF-002 LGPD | T015, T016, T067, T069, T072 |
| RNF-003 política | não se aplica (sem agentes) |
| RNF-004 observabilidade e auditoria | T014, T033, T038, T066 |
| RNF-005 segurança da aplicação | T005, T007, T009, T028, T032, T035, T071, T073, T076 |
| RNF-006 segurança de IA | não se aplica (sem LLM); garantido por desenho |
| RNF-007 desempenho | T075 |
| CS-001 a CS-003 | T079 |
| CS-004 | T055, T061 |
| CS-005 | T046 |
| CS-006 | T066 |
| CS-007 | T015, T071 |
| CS-008 | T062, T079 |
| CS-009 | T060 |

**Bloqueios:** nenhum.
