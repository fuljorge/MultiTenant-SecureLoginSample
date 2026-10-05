# Plano: Identidade, Autenticação e Controle de Acesso de Usuários

- **ID:** 001-identity-access
- **Spec:** [spec.md](spec.md) (Aprovada em 2026-10-04, emenda ASVS)
- **Status:** Aprovado <!-- Rascunho | Aprovado -->
- **Emenda 2026-10-04:** reautenticação recente (RF-031) e medidor de força da senha
  (RF-032), vindos do checklist ASVS (T076). Seções alteradas: 4.12 (nova), 8, 10 e 11.
- **Revisão 2026-10-03:** Super Administrador e modelo híbrido. Seções alteradas: 1, 3,
  4.2, 4.3, 4.4, 4.8, 4.11 (nova), 5, 7, 8, 10, 11 e 12 (nova).
- **Criado em:** 2026-10-02
- **Aprovado por / em:** Fulvio Jorge da Silva / 2026-10-04 (emenda ASVS; versões
  anteriores aprovadas em 2026-10-02 e 2026-10-03)

Artefatos: [research.md](research.md) · [data-model.md](data-model.md) ·
[contracts/identity-api.md](contracts/identity-api.md) ·
[contracts/audit-events.md](contracts/audit-events.md)

## 1. Resumo

O **Keycloak** faz a autenticação: login com e-mail e senha, código de segundo fator por
e-mail (extensão Apache 2.0, research R1), bloqueio por tentativas, recuperação de senha
e hash Argon2. O **Control Plane** (FastAPI) faz todo o resto: organizações, vínculos,
perfis, escopo de Administrador, autorização por requisição, sessões do navegador no
padrão BFF e Audit Trail com hash encadeado. O **SecureLogin** (Next.js) traz as telas de
administração de usuários, organizações, segurança, auditoria e sessões.

Por ser a primeira feature com código, o plano também cria a estrutura do monorepo, o
ambiente local (Docker Compose) e o CI com os gates da constituição.

**Revisão 2026-10-03.** O Administrador da instalação dá lugar ao **Super
Administrador** do fornecedor (spec §4.8, RF-025 a RF-030). Hoje o escopo de instalação
**ignora o RLS** em todas as tabelas de identidade; o Super Administrador passa a ter
políticas próprias, que só expõem organizações, os seus Administradores e os convites de
organização. Ele não tem organização ativa nem permissões de organização. A seção 12
lista o que muda no código já entregue (US1 a US4).

## 2. Contexto técnico

- **Linguagem/versão:** Python 3.12 (Control Plane); TypeScript 5.x (Studio). Nenhum
  código Java próprio: a extensão do Keycloak entra como artefato pronto, com versão e
  checksum fixados.
- **Dependências principais:**
  - Control Plane: FastAPI, Pydantic v2, SQLAlchemy 2 + Alembic, Authlib, httpx,
    redis-py (cliente compatível com Valkey), OpenTelemetry.
  - Studio: Next.js, shadcn/ui + Radix UI + Tailwind CSS, TanStack Query + TanStack
    Table, i18next, cliente gerado por orval.
  - Identidade: Keycloak (versão fixada conforme R1), extensão
    `keycloak-2fa-email-authenticator`, keycloak-config-cli.
- **Armazenamento:** PostgreSQL 17 com RLS (dados do Control Plane); banco próprio do
  Keycloak na mesma instância PostgreSQL, em database separado; Valkey (sessões); OpenBao
  (segredos e chave de cifra das sessões).
- **E-mail:** SMTP genérico configurado no provisionamento (Keycloak e Control Plane
  usam o mesmo relay). Mailpit em desenvolvimento e testes.
- **Testes:** pytest + Testcontainers, Vitest (proposto), Playwright, gitleaks, Trivy.
- **Componentes afetados:** Control Plane, SecureLogin, Keycloak, infraestrutura local
  e CI. Nenhum componente do data plane.
- **Metas de desempenho:** RNF-007 da spec (etapas de login ≤ 2 s p95; e-mail do código
  ≤ 60 s p95; troca de organização ≤ 2 s; revogação ≤ 60 s).
- **Restrições:** licenças OSI (constituição, Seção 3); nada do Keycloak acessa o banco
  do Control Plane e vice-versa.

## 3. Verificação da Constituição

| Princípio | Status | Como o plano atende |
|---|---|---|
| I. Especificação primeiro | ✅ | Spec aprovada; plano e tarefas passam por aprovação antes do código |
| II. Control/data plane, versões imutáveis | ✅ | Não se aplica: feature só do control plane, sem versões de agente |
| III. Ações governadas por política | ✅ | Não se aplica a agentes (RNF-003). Autorização de usuários por matriz de permissões no servidor, negação por padrão |
| IV. Isolamento multi-tenant | ✅ | `organization_id` + RLS em `membership` e `invitation`; contexto de organização por transação; papel do banco sem `BYPASSRLS`; **nenhum papel ignora o RLS**: o Super Administrador tem políticas próprias, restritas a organizações, Administradores e convites de organização; testes de isolamento por perfil, na troca de organização e para o Super Administrador |
| V. LGPD desde o projeto | ✅ | Dados pessoais mínimos (nome, e-mail, IP, navegador); IP e navegador fora da cadeia de auditoria, com expurgo em 12 meses; anonimização no pedido de esquecimento; logs técnicos sem e-mail nem IP completos; o Super Administrador só vê nome e e-mail dos Administradores das organizações |
| VI. Agnóstico a modelo e nuvem | ✅ | Keycloak, PostgreSQL, Valkey e OpenBao self-hosted; e-mail por SMTP genérico; nenhum serviço proprietário |
| VII. Observável e auditável | ✅ | Audit Trail append-only com hash encadeado; eventos do Keycloak importados com cursor; traces OpenTelemetry nas rotas; métricas de login, bloqueio e entrega de e-mail |
| VIII. Qualidade verificável | ✅ | Testes de unidade, integração, contrato e E2E por história; matriz de permissões testada por tabela (CS-004); gates de CI na seção 8 |
| IX. Simplicidade e entrega por fase | ✅ | Sem OpenFGA, SSO, Keycloak Organizations, barramento de eventos nem Keycloakify; tudo dentro da Fase 1 |
| X. Segurança da aplicação e dos dados | ✅ | Senhas só no Keycloak (Argon2); segredos no OpenBao; tokens de convite e troca de e-mail guardados como hash; tokens de sessão cifrados; cookie `__Host-` HttpOnly; CSRF; limites mínimos de segurança não configuráveis; gitleaks e Trivy no CI. Pendente: armazenamento do código na extensão (R1, item 1) |
| XI. Segurança de IA | ✅ | Nenhum LLM ou agente participa da autenticação ou autorização (RNF-006) |
| §2 Identidade de marca | ✅ | Tema do Keycloak e telas do Studio com os tokens do media kit, em PT-BR |
| §3 Licenças e dependências | ✅ | Todas OSI (research R8); novas dependências registradas na stack nesta mudança |

## 4. Arquitetura e design

```text
Navegador
   │  cookie de sessão (__Host-, HttpOnly)          telas de login e código
   ▼                                                        ▲
SecureLogin (Next.js) ── /api/v1 ──▶ Control Plane (FastAPI) ── OIDC + PKCE ─┘
                                        │   │   │                   Keycloak
                                        │   │   └── Admin REST API ──▶ (realm da instalação,
                                        │   │                           extensão de código por e-mail,
                                        │   └── Valkey (sessões)        brute force, Argon2)
                                        ├── PostgreSQL (identity, audit, RLS)
                                        ├── OpenBao (segredos, chave de cifra)
                                        └── SMTP (avisos: senha trocada, e-mail trocado, convite a quem já tem conta)
```

### 4.1 Login (US1)

1. O Studio chama `GET /api/v1/auth/login`; o Control Plane redireciona ao Keycloak com
   PKCE e `state`.
2. O Keycloak executa o fluxo **senha → código por e-mail** e o bloqueio por tentativas.
3. No retorno, o Control Plane troca o código por tokens, cria a sessão no Valkey,
   escolhe a organização ativa (a última usada) e grava `auth.login`.
4. Cada requisição carrega a sessão, revalida o vínculo com a organização ativa e aplica a
   matriz de permissões. Inatividade (30 min) e duração máxima (12 h) valem na sessão do
   BFF e no Keycloak.

### 4.2 Autorização (US4, US5)

- Catálogo de permissões e matriz perfil × permissão em código (`permissions.py`),
  espelhando a seção 5.1 da spec. Cada rota declara a permissão exigida.
- Dois tipos de principal, que não se misturam:
  - **membro de organização:** permissões do perfil na organização ativa (matriz);
  - **Super Administrador:** permissões de instalação, sem organização ativa:
    `organizations:manage`, `organization_admins:manage`, `super_admins:manage`,
    `security:manage`, `billing:read:all`, `billing:manage:all` e
    `audit:read:installation`.
- Nenhum perfil de organização recebe permissão de instalação, e o Super Administrador
  não recebe nenhuma permissão de organização (teste da matriz; RF-016, RF-028). O
  Administrador implícito em todas as organizações deixa de existir.
- A matriz cobre todas as áreas da spec. As áreas de outras features (agentes, custos,
  conversas) ganham rotas e testes de ponta a ponta nas features delas; aqui recebem
  testes de unidade da matriz.
- **RF-015** (custos só dos próprios agentes) depende do conceito de "responsável pelo
  agente", que nasce na feature de agentes. Este plano entrega a permissão
  `costs:read:own`; o filtro é implementado e testado na feature do Dashboard de Custos.

### 4.3 Convites e ativação (US2, US3)

- **Pessoa nova:** o Control Plane cria o usuário no Keycloak com a *required action*
  `UPDATE_PASSWORD` e chama `execute-actions-email` (validade de 72 h; boas-vindas usa o
  mesmo mecanismo). O vínculo fica `pending` e vira `active` no primeiro login.
- **Pessoa já cadastrada:** convite próprio do Control Plane (token aleatório, guardado
  como hash), aceito com a pessoa logada.
- O e-mail do Keycloak usa templates próprios em PT-BR com a identidade da marca.
- **Convite de organização (US5):** `POST /organizations` cria, na mesma transação, a
  organização `pending`, a pessoa (se for nova) e o vínculo `administrator` `pending`,
  reaproveitando os dois caminhos acima. Quando o primeiro vínculo de Administrador fica
  `active` (primeiro login ou aceite), a organização passa a `active` na mesma
  transação. Reenvio gera novo link ou token; cancelamento só vale para `pending` e leva
  a organização a `cancelled` (não há exclusão; o histórico fica no Audit Trail).
- Convite para o e-mail de um Super Administrador é recusado (spec, casos de borda).

### 4.4 Desativação e revogação (RF-011, CS-005)

Na mesma operação: `enabled=false` no Keycloak, logout de todas as sessões do usuário no
Keycloak e remoção das sessões do BFF (`cap:user-sess:{user_id}`). Efeito imediato na
próxima requisição.

**Revisão 2026-10-03: desativação por organização.** Sem o Administrador da instalação,
ninguém poderia desativar a conta de quem pertence a mais de uma organização, e na
instalação compartilhada o Administrador de um cliente não pode tirar o acesso de uma
pessoa a outro cliente. Por isso:

- desativar e reativar agem sobre o **vínculo** com a organização (`membership.status`
  `disabled`), e as sessões cuja organização ativa é essa são removidas;
- se a pessoa fica sem nenhum vínculo ativo, a conta também é desativada no Keycloak,
  como acima (é o caso de quem só tem uma organização, que é o cenário da US3);
- a desativação de um Administrador pelo Super Administrador (RF-027) usa a mesma
  operação.

### 4.5 Troca de senha (RF-005)

O fluxo de recuperação do Keycloak encerra as outras sessões. O worker de eventos, ao
ver `UPDATE_PASSWORD` ou `RESET_PASSWORD`, remove as sessões do BFF e envia o aviso por
e-mail. O *back-channel logout* cobre o intervalo até a leitura do evento.

### 4.6 Troca de e-mail (US3, cenário 6)

Token de confirmação próprio (hash no banco, 24 h) enviado ao novo e-mail. Na
confirmação: atualiza o Keycloak, encerra sessões, avisa o e-mail antigo.

### 4.7 Audit Trail (US6)

- Eventos do Control Plane gravados na mesma transação da operação.
- Worker importa eventos do Keycloak a cada 5 s com cursor e deduplicação
  (`source`, `source_event_id`).
- Hash encadeado, gravação serializada, papel de banco só com `INSERT`/`SELECT` e trigger
  contra alteração; rotina de verificação da cadeia.

### 4.8 Configuração de segurança (RF-007)

Tela do Super Administrador que lê e grava no realm do Keycloak (política de
senha, tempos de sessão, bloqueio, parâmetros do código), com limites mínimos que a API
recusa afrouxar (ver contrato).

### 4.9 Keycloak

- Imagem própria construída a partir da oficial, com a extensão baixada por versão e
  **checksum SHA-256 verificado**, tema `cap` (CSS + mensagens PT-BR) e build otimizado.
- Realm por instalação, aplicado por keycloak-config-cli a partir de
  `infra/keycloak/realm/cap-realm.yaml`:
  - fluxo de navegador: formulário de usuário e senha → código por e-mail (obrigatório);
  - registro de novos usuários desligado; login por e-mail;
  - brute force: bloqueio temporário de 15 min após 5 falhas;
  - política de senha: 12+ caracteres, lista de senhas vazadas, histórico de 5, diferente
    do e-mail;
  - sessão: inatividade de 30 min, máximo de 12 h; links de ação: 72 h (convite),
    30 min (recuperação);
  - eventos de login e de administração habilitados, guardados por 7 dias;
  - cliente `cap-control-plane` (confidencial, PKCE, back-channel logout);
  - cliente `cap-admin-bridge` (conta de serviço com papéis mínimos: `manage-users`,
    `view-events`, `view-realm`, `manage-realm` só para a tela de segurança).
- Keycloak exposto no mesmo domínio da instalação, no caminho `/idp`.

### 4.10 Ambiente local

`infra/compose/docker-compose.yml` sobe PostgreSQL, Valkey, OpenBao (modo dev), Mailpit,
Keycloak (imagem própria) e aplica o realm. Control Plane e Studio rodam fora ou dentro
do compose. Comandos documentados no `AGENTS.md` (seção 9) ao fim da implementação.

### 4.11 Super Administrador (US2, US5; RF-025 a RF-030)

- **Armazenamento:** a tabela `installation_admin` vira `super_admin`. Um *trigger*
  recusa vínculo com organização para quem é Super Administrador e recusa tornar Super
  Administrador quem tem vínculo ativo (RF-028), além da checagem no serviço.
- **RLS:** a função `identity.has_installation_scope()` dá lugar a
  `identity.is_super_admin()`, usada só em políticas específicas:
  - `organization`: ler, criar e alterar todas;
  - `membership` e `invitation`: só as linhas com perfil `administrator`;
  - `user_account`: só pessoas com vínculo de Administrador ou que são Super
    Administradores;
  - `email_change_request` e tabelas de outras features: nenhuma política para ele.
  Um teste executa as consultas com o contexto do Super Administrador direto no banco e
  confirma que pessoas e vínculos de outros perfis não aparecem.
- **Sessão:** o Super Administrador entra sem organização ativa; `GET /me` informa o
  tipo de principal, e o Studio abre a tela de organizações. Pessoa sem organização
  acessível e que não é Super Administrador continua recebendo o erro
  `sem-organizacao`.
- **Organização suspensa ou pendente:** a revalidação de cada requisição passa a exigir
  `organization.status = 'active'`. Na suspensão, as sessões com essa organização ativa
  são removidas do BFF; quem não tem outra organização ativa também é desconectado no
  Keycloak (CS-009).
- **Último Administrador (RF-012):** travamento dos vínculos de Administrador da
  organização (`FOR UPDATE`) na desativação, na remoção e na mudança de perfil; a mesma
  técnica já usada para o escopo de instalação vale para os Super Administradores.
- **Auditoria:** `audit_event` ganha `installation_scope` (booleano, dentro da cadeia de
  hash). Ações do Super Administrador sobre uma organização gravam o `organization_id`
  dela **e** `installation_scope = true`: o Administrador da organização vê pelo
  `organization_id`, e o Super Administrador vê por `installation_scope` ou pelos
  eventos feitos por Super Administradores, como os logins deles (US6, cenário 2).
- **Billing:** só as permissões (RF-029); rotas e telas na feature de Faturamento.
- **Studio:** menu "Organizações" (lista com filtros, convite, detalhe com
  Administradores, suspender e reativar), "Super Administradores" e "Segurança"; o
  cabeçalho mostra "Super Administrador" no lugar da organização.

### 4.12 Reautenticação recente e medidor de força (RF-031, RF-032)

- **Momento do login:** o callback guarda na sessão do BFF o `auth_time` do ID token
  (quando a pessoa digitou senha e código). Uma renovação de tokens não muda esse valor.
- **Dependência `require_recent_auth`:** nas rotas do RF-031, junto da permissão. Se o
  `auth_time` tiver mais de 15 min, responde `401` com Problem Details
  `{"code": "reauth_required"}` e não executa nada. O prazo é constante nesta fase.
- **Nova autenticação:** `GET /auth/login?reauth=1&return_to=...` manda ao Keycloak
  `prompt=login` e `max_age=0`, que exigem senha e código mesmo com sessão SSO. No
  callback, a sessão anterior do mesmo navegador é substituída pela nova.
- **Troca de senha:** `GET /auth/password` passa a enviar `max_age=0` junto do
  `kc_action=UPDATE_PASSWORD`.
- **Studio:** o cliente da API reconhece `reauth_required`, guarda a tela atual e leva a
  pessoa à nova autenticação; ao voltar, mostra "Identidade confirmada, repita a ação".
  A ação não é repetida sozinha, para a pessoa ver o que vai acontecer.
- **Teste estrutural:** a lista de rotas do RF-031 fica no contrato; um teste confere que
  cada uma declara `require_recent_auth` e que nenhuma outra declara.
- **Medidor de força:** script no tema `cap` do Keycloak, nas telas de definir senha
  (ativação, convite, recuperação e troca), com heurística local (tamanho, variedade de
  caracteres, repetições e sequências) e rótulos em PT-BR. Sem dependência nova; não
  bloqueia o envio: quem decide é a política do realm.

## 5. Modelo de dados

Ver [data-model.md](data-model.md). Tabelas `organization`, `user_account`,
`super_admin`, `membership`, `invitation`, `email_change_request` (schema `identity`),
`audit_event`, `audit_event_origin`, `keycloak_event_cursor` (schema `audit`); sessões no
Valkey. A revisão de 2026-10-03 entra por uma migração nova (0004), sem editar as
anteriores.

## 6. Contratos

- API: [contracts/identity-api.md](contracts/identity-api.md); OpenAPI gerado pelo
  FastAPI e cliente TypeScript gerado por orval (verificação de divergência no CI).
- Eventos de auditoria: [contracts/audit-events.md](contracts/audit-events.md).
- Configuração do Keycloak: `infra/keycloak/realm/cap-realm.yaml` (versionado).

## 7. Estrutura de código

```text
apps/
  studio/                          # Next.js — SecureLogin
    src/app/(app)/admin/usuarios/
    src/app/(app)/admin/organizacoes/       # Super Administrador
    src/app/(app)/admin/super-administradores/
    src/app/(app)/admin/seguranca/
    src/app/(app)/admin/auditoria/
    src/app/(app)/conta/sessoes/
    src/components/org-switcher/
    src/lib/auth/                  # sessão, CSRF, permissões no cliente (só para exibir)
    src/styles/tokens.css          # tokens do media kit
services/
  control-plane/
    src/cap_control_plane/
      core/                        # settings, db, RLS, segredos (OpenBao), e-mail, telemetria
      identity/                    # api, service, permissions, sessions, keycloak_admin, oidc
      audit/                       # chain, writer, keycloak_ingestor, api, export
      cli/                         # cap-admin
    migrations/                    # Alembic
    tests/{unit,integration,contract}/
packages/
  api-client/                      # gerado por orval
infra/
  keycloak/{Dockerfile,realm/,themes/cap/,providers.lock}
  compose/docker-compose.yml
tests/
  e2e/                             # Playwright (lê códigos no Mailpit)
.github/workflows/ci.yml
pyproject.toml                     # workspace uv
pnpm-workspace.yaml
.gitleaks.toml
```

## 8. Estratégia de testes

- **Unitários:** matriz de permissões (tabela perfil × permissão, incluindo escopos de
  Administrador); cadeia de hash; validação de limites da configuração de segurança;
  mapeamento de eventos do Keycloak.
- **Contrato:** OpenAPI gerado comparado ao contrato; cliente TypeScript sem divergência.
- **Integração (Testcontainers):** PostgreSQL com RLS real; Valkey; Keycloak com a imagem
  e o realm do projeto. Fluxos: convite, ativação, desativação com revogação, troca de
  e-mail, último Administrador, edições concorrentes (`412`), importação de eventos sem
  duplicar.
- **Isolamento de organização (Princípio IV):** para cada rota, usuário da organização A
  tenta ler e alterar recursos da organização B → `404`/`403` e `access.denied`; troca de
  organização só para vínculos válidos.
- **Super Administrador:** a matriz rota × principal (T055) ganha o Super Administrador:
  `403` e `access.denied` em toda rota de organização; RLS testado direto no banco com o
  contexto dele; vínculo recusado pelo *trigger*; suspensão encerra o acesso em até
  60 s; último Administrador de organização e último Super Administrador protegidos;
  convite de organização de ponta a ponta no E2E.
- **E2E (Playwright):** cada história de P1 de ponta a ponta, com o código lido no
  Mailpit; login com código expirado, reenviado e incorreto; bloqueio; recuperação de
  senha com aviso; telas em viewport de celular.
- **Segurança:**
  - varredura de segredos (gitleaks) e de vulnerabilidades (Trivy) no CI;
  - verificação de que senha, código, token e link não aparecem em logs, respostas e
    Audit Trail (CS-007), com captura de logs nos testes de integração e E2E;
  - cookies com atributos corretos; CSRF recusado sem cabeçalho;
  - enumeração de usuários: mesma resposta e tempo semelhante para e-mail existente ou
    não;
  - checklist OWASP ASVS nível 2 (capítulos V2 autenticação, V3 sessão, V4 controle de
    acesso) preenchido na revisão.
- **Gates de IA/política:** não se aplicam (sem agentes nem políticas OPA).

## 9. Rastreamento de complexidade

Nenhuma exceção à constituição.

## 10. Decisões e riscos

| Decisão / risco | Alternativas consideradas | Justificativa / mitigação |
|---|---|---|
| Código por e-mail via extensão de terceiros (R1) | Extensão própria em Java; outra extensão | Licença Apache 2.0, ativa, configurável. Risco de mantenedor único e de atraso em relação às versões do Keycloak: versão fixada, checksum, plano B documentado |
| Extensão pode guardar o código em texto claro na sessão de login (R1, item 1) | — | Verificação bloqueante antes de configurar o fluxo; correção por contribuição ou fork |
| Organizações e perfis no Control Plane, não no Keycloak (R2) | Keycloak Organizations | Autorização imediata (RF-017), RLS junto dos dados, uma fonte de verdade |
| BFF com sessão no Valkey (R3) | Tokens no navegador; Auth.js | Tokens fora do alcance de XSS; lógica de sessão num só lugar |
| Eventos do Keycloak por leitura periódica (R4) | Event listener SPI + fila | Sem Java próprio nem barramento de eventos na Fase 1; alerta se o cursor atrasar |
| Perda do Valkey derruba as sessões | Sessões no PostgreSQL | Efeito é só um novo login; Valkey com persistência habilitada |
| Retenção de IP e navegador de 12 meses | Outro prazo | Valor inicial configurável; confirmar com o jurídico/DPO |
| Entrega de e-mail (código, convites) depende de SPF/DKIM do domínio da instalação | — | Requisito para o provisionamento (§53.2); falha de envio alertada pelo log de erro do Keycloak, via observabilidade (RNF-004, achado A14) |
| Exportação periódica do Audit Trail para armazenamento WORM (stack §3.11) | — | Fica para a feature de observabilidade/auditoria; esta feature entrega a tabela e a verificação da cadeia |
| Super Administrador com políticas RLS próprias, sem ignorar o RLS | Manter `has_installation_scope()` e filtrar no serviço | Um erro no serviço exporia dados de clientes na instalação compartilhada; no banco, a barreira vale para qualquer consulta |
| Desativação por vínculo com a organização | Desativar sempre a conta | Na instalação compartilhada, um cliente não pode tirar o acesso de uma pessoa a outro cliente |
| `installation_scope` no evento de auditoria | Tabela separada para eventos de instalação | Uma só cadeia de hash e uma só consulta; o Administrador da organização continua vendo as ações do Super Administrador sobre ela |
| Dados locais existentes (Administrador da instalação com vínculos) | Apagar e recriar o ambiente | A migração 0004 converte em Super Administrador e marca os vínculos dele como `removed`, com evento no Audit Trail; não há instalação em produção |
| Segundo fator do Super Administrador igual ao dos demais | Exigir fator mais forte | Suposição da spec; reavaliar com o segundo fator por aplicativo (fase futura) |
| Reautenticação por `auth_time` + `prompt=login`/`max_age=0` (RF-031) | Senha digitada num modal do Studio; confirmação por código no e-mail | A senha nunca passa pelo Control Plane (Princípio X); o Keycloak já aplica senha, código e bloqueio por tentativas |
| Medidor de força com heurística própria (RF-032) | zxcvbn | Sem dependência nova de ~800 KB no tema; o medidor só orienta, a política do realm decide |
| P3 a P5 do checklist ASVS (administrador do realm `master`, TLS no SMTP, segredos de produção) | Resolver na 001 | Dependem de como a instalação é criada; viraram requisitos do provisionamento (§53.2) |

## 11. Impacto em documentos de referência

- [x] referência de stack interna (não incluída neste exemplo): nova §3.16 com ferramentas de
      engenharia e as dependências de identidade (R1, R6, R8) — **nesta mudança**.
- [x] da referência de produto interna (não incluída neste exemplo): §4.7 e §48 (versão
      anterior); §4.1, §4.7, §4.8, §44, §51 e §53.2 na revisão de 2026-10-03; §53.2
      (requisitos de segurança do provisionamento) na emenda de 2026-10-04.
- [x] `AGENTS.md`: comandos de build, testes e ambiente local na seção 9 (T077).

## 12. Migração do que já foi implementado (revisão 2026-10-03)

| Área | Hoje (US1 a US4) | Depois |
|---|---|---|
| Banco | `installation_admin`; `has_installation_scope()` ignora o RLS; `organization.is_default` | Migração 0004: `super_admin`; políticas da seção 4.11; `organization.status`; `membership.status` com `disabled`; `audit_event.installation_scope`; sem organização padrão |
| `permissions.py` | `INSTALLATION_ADMIN_EXTRA` somado ao perfil Administrador | `SUPER_ADMIN_PERMISSIONS` separado; `effective_permissions` não mistura os dois |
| `Principal` / `DbContext` | `is_installation_admin` | `is_super_admin`; Super Administrador sem organização ativa |
| Login e `/me` | erro `sem-organizacao` para quem não tem vínculo | Super Administrador entra sem organização; `/me` informa o tipo de principal |
| Usuários (US3) | desativar e reativar agem na conta; outras organizações exigem escopo de instalação | por vínculo (seção 4.4); último Administrador por organização (RF-012) |
| Segurança | `security:manage` do Administrador da instalação | do Super Administrador |
| CLI `cap-admin` | `bootstrap-admin` cria a organização padrão e o Administrador da instalação | `bootstrap-super-admin` cria só o Super Administrador; `reissue-activation` vale para ele |
| Studio | menu Usuários e Segurança | menus por tipo de principal (seção 4.11) |
| Testes | matriz com o Administrador da instalação | matriz com o Super Administrador; testes de US2 e US3 ajustados |
