# Pesquisa: 001-identity-access

Decisões técnicas que embasam o [plano](plan.md). Cada item registra a pergunta, a
decisão, as alternativas e o que ainda precisa ser verificado na implementação.

- **Data:** 2026-10-02
- **Constituição:** v1.1.0 (Princípio X determina que a autenticação de usuários é
  delegada ao Keycloak)

---

## R1. Segundo fator por código no e-mail

**Pergunta:** o Keycloak oferece código de uso único por e-mail como segundo fator?

**Fatos verificados:**
- A versão mais recente é a **26.8.0**. As notas de versão não mencionam autenticador de
  código por e-mail; os segundos fatores nativos são TOTP, WebAuthn e códigos de
  recuperação.
- O recurso existe como extensão da comunidade (Authenticator SPI, em Java).

**Opções avaliadas:**

| Opção | Licença | Situação | Avaliação |
|---|---|---|---|
| `mesutpiskin/keycloak-2fa-email-authenticator` | Apache 2.0 | ~280 estrelas, releases acompanham as versões do Keycloak (última em 2026-09) | Configura tamanho do código, validade, intervalo de reenvio e máximo de tentativas; templates e i18n; envio por SMTP do próprio Keycloak |
| `for-keycloak/email-otp-authenticator` | Unlicense | ~30 estrelas, ativa | Domínio público, aprovado pela OSI, mas base de usuários pequena |
| Extensão própria (Authenticator SPI) | — | — | ~200 linhas de Java; controle total, mas introduz Java como linguagem mantida pelo time (decisão em aberto nº 6 da stack) |

**Decisão:** usar `mesutpiskin/keycloak-2fa-email-authenticator`, com **versão fixada e
checksum verificado** na construção da imagem do Keycloak. O Keycloak é fixado na versão
que a extensão suporta oficialmente.

**A verificar na implementação (bloqueia a tarefa de configuração do fluxo de login):**
1. Se o código é guardado em texto claro na nota da sessão de autenticação. Se for,
   avaliar o risco (a nota fica só em memória e expira com a sessão de login) e, se
   necessário, contribuir com o armazenamento por hash ou manter um fork.
2. Se a extensão emite eventos de envio, reenvio e falha de código (RF-021). Se não
   emitir, a falta de evento precisa ser coberta antes de concluir a feature.
3. Se cada reenvio invalida o código anterior (RF-002).
4. Compatibilidade com a versão do Keycloak fixada e com o tema da plataforma.

**Plano B:** se algum item acima não puder ser resolvido por configuração ou
contribuição, escrever a extensão própria. Isso exige aprovação da inclusão de Java
(decisão em aberto nº 6 da stack).

### Resultado da verificação (T008, 2026-10-02)

Leitura do código-fonte da release **v26.5.0** (commit `904a123` da `main` para
comparação). Artefato: `keycloak-2fa-email-authenticator-v26.5.0-KC26.7.3.jar`, com
assinatura GPG (`.asc`) publicada.

| # | Pergunta | Resultado |
|---|---|---|
| 1 | Código em texto claro? | ✅ Não. Guardado como SHA-256 na nota da sessão de autenticação (`OtpHashUtils`), comparação em tempo constante. Código gerado por `SecretGenerator` do Keycloak |
| 2 | Eventos de envio, reenvio e falha? | ⚠️ **Parcial.** Falhas de código geram `LOGIN_ERROR` (`invalid_user_credentials`, `expired_code`). **Envio e reenvio não geram evento.** Falha no envio do e-mail só gera log de erro, sem evento |
| 3 | Reenvio invalida o anterior? | ✅ Sim (`resetEmailCode` remove o hash antes de gerar outro). Intervalo mínimo entre reenvios configurável (`resendCooldown`) |
| 4 | Versão do Keycloak | ✅ Builds para 26.5.x a **26.7.3**. A 26.8.0 ainda não tem build: o Keycloak fica na série **26.7** (26.7.3; **26.7.5** desde 2026-10-04, por correções de segurança da distribuição apontadas pelo Trivy na T073, com a extensão recompilada e os testes do realm repetidos) |
| 5 | Falhas de código contam para o bloqueio? | ❌ **Não** (corrigido na T012, achado A15). Pela leitura do código parecia que sim, mas o teste real no Keycloak 26.7.3 mostrou que as falhas de código não entram no contador. E, com brute force ligado, a extensão não aplica o próprio `maxAttempts`: **o código pode ser testado sem limite** durante a validade. **Corrigido por patch** (achado A15): o build compila a extensão a partir do commit fixado com `infra/keycloak/patches/0001-limit-email-code-attempts.patch` |

**Outros achados:**
- O assunto do e-mail vem da chave `emailCodeSubject` do tema; o tema `cap` traduz para
  PT-BR sem alterar a extensão.
- A extensão registra o e-mail do usuário em logs `INFO` (envio com sucesso) e `ERROR`
  (falha). Mitigação: nível `WARN` para a categoria `com.mesutpiskin` e redação na
  coleta de logs. Resta o e-mail em logs de erro de envio.
- O modo de simulação (`simulationMode`) escreve o código no log: o realm deve fixá-lo
  em `false` e o teste do realm (T012) deve verificar.
- Configuração equivalente aos padrões da spec: `length=6`, `ttl=600`,
  `resendCooldown=300` (no máximo 3 reenvios a cada 15 min).

**Decisão sobre o item 2 (2026-10-02, Fulvio Jorge da Silva):** envio e reenvio do
código saem do RF-021; o alerta de falha de envio vem do log de erro do Keycloak, pela
observabilidade. A extensão é usada sem alterações e sem Java próprio (achado A14).

## R2. Organizações: Keycloak Organizations ou Control Plane?

**Fatos verificados:** desde a versão 26, o Keycloak tem *Organizations*, com
participação em várias organizações e convites. A 26.7 trouxe grupos por organização com
herança de papéis.

**Decisão:** o Keycloak cuida **só da autenticação**. Organizações, vínculos, perfis e
escopo de Administrador ficam no **banco do Control Plane**.

**Motivos:**
- A autorização é avaliada no servidor a cada requisição a partir do banco, o que faz a
  mudança de perfil valer na próxima ação (RF-017) sem depender da renovação de tokens.
- O isolamento por organização usa RLS no PostgreSQL (Princípio IV), na mesma base dos
  agentes, Skills e demais recursos que virão nas próximas features.
- Mantém o Keycloak substituível e simplifica a auditoria, que fica toda no Control Plane.

**Alternativa rejeitada:** perfis como papéis do Keycloak por organização. Cria duas
fontes de verdade e obriga a sincronizar a cada mudança.

## R3. Sessão no navegador: tokens no front-end ou BFF?

**Decisão:** padrão **BFF (Backend for Frontend)** no Control Plane.
- Fluxo OIDC Authorization Code com PKCE entre o Control Plane e o Keycloak (Authlib,
  já na stack).
- O navegador recebe apenas um cookie de sessão opaco (`__Host-`, `HttpOnly`, `Secure`,
  `SameSite=Lax`). Tokens nunca chegam ao JavaScript (RNF-005).
- A sessão fica no Valkey; os tokens do Keycloak ficam cifrados com chave obtida do
  OpenBao (Princípio X).
- Proteção contra CSRF: `SameSite=Lax` mais token anti-CSRF em cabeçalho nas requisições
  que alteram estado.
- *Back-channel logout* do Keycloak para o Control Plane, para encerrar a sessão do BFF
  quando o Keycloak encerrar a sessão (ex.: troca de senha).

**Alternativas rejeitadas:**
- Tokens no navegador (SPA pública): expõe tokens a XSS.
- Auth.js no Next.js: põe a lógica de sessão em dois lugares (Next.js e API).

## R4. Eventos do Keycloak no Audit Trail

**Decisão:** um *worker* do Control Plane lê periodicamente (a cada 5 s) os eventos de
login e de administração pela Admin REST API do Keycloak, com cursor persistido, e os
grava no Audit Trail. O Keycloak guarda os eventos por 7 dias como margem.

**Alternativa rejeitada:** *event listener* SPI no Keycloak publicando em fila. Exige
Java próprio e um barramento de eventos que a Fase 1 ainda não definiu (NATS ou Kafka).

**Risco:** se o worker ficar parado por mais de 7 dias, eventos se perdem. Mitigação:
alerta quando o cursor atrasar mais de 5 minutos.

## R5. Rejeição de senhas vazadas (RF-007)

**Decisão:** política *Password Blacklist* nativa do Keycloak, com uma lista offline de
senhas vazadas (por exemplo, a lista de 1 milhão de senhas mais comuns do SecLists, MIT).
Junto com tamanho mínimo de 12 caracteres, histórico de 5 senhas e proibição de usar o
e-mail como senha.

**Alternativa rejeitada:** consulta online ao Have I Been Pwned. Depende de serviço
externo e envia prefixos de hash para fora da instalação do cliente.

## R6. Configuração do Keycloak como código

**Decisão:** **keycloak-config-cli** (adorsys, Apache 2.0) aplica de forma idempotente um
arquivo versionado com o realm, os clientes, o fluxo de login, as políticas e os tempos de
sessão. O mesmo arquivo serve ao ambiente local, ao CI e ao provisionamento.

**Alternativa rejeitada:** importação de realm na inicialização do Keycloak. Só funciona
na primeira subida e não aplica mudanças em instalações existentes.

## R7. Telas de login com a identidade da marca

**Decisão:** tema próprio do Keycloak que estende o tema padrão (`keycloak.v2`) com CSS e
mensagens em português, usando os tokens do media kit.

**Alternativa rejeitada:** Keycloakify (MIT). Permite telas em React, mas adiciona um
processo de build para poucas telas (login, código, troca de senha, recuperação, erro).

## R8. Ferramentas de engenharia (primeira feature com código)

Escolhas para as pendências 14 a 20 da lista de definições, todas com licença OSI:

| Necessidade | Escolha | Licença | Motivo |
|---|---|---|---|
| Organização do repositório | Monorepo: workspaces do uv (Python) e do pnpm (TypeScript) | — | Spec, contratos e código mudam juntos; sem Nx/Turborepo por enquanto |
| Pacotes Python | uv | Apache 2.0 / MIT | Rápido, lockfile, workspaces |
| Pacotes TypeScript | pnpm | MIT | Workspaces, lockfile estrito |
| Testes Python | pytest + pytest-asyncio + Testcontainers | MIT / Apache 2.0 | Testes de integração com PostgreSQL, Valkey e Keycloak reais |
| Lint, formatação e segurança Python | Ruff (inclui regras do Bandit) | MIT | Uma ferramenta para lint, formatação e análise estática de segurança |
| Tipos Python | mypy (modo estrito) | MIT | |
| Lint e formatação TypeScript | ESLint + Prettier | MIT | Padrão do ecossistema Next.js |
| Testes unitários de front-end | Vitest | MIT | Proposta, ainda não aprovada (pendência 7) |
| Testes E2E | Playwright | Apache 2.0 | Decidido (branch `docs/stack-playwright`) |
| E-mail em desenvolvimento e testes | Mailpit | MIT | Captura e-mails; os testes E2E leem o código do segundo fator por API |
| CI | GitHub Actions | — | Repositório no GitHub |
| Varredura de segredos | gitleaks | MIT | CI e pre-commit (Princípio X) |
| Vulnerabilidades em dependências e imagens | Trivy | Apache 2.0 | Já na stack (§3.14) |

## Fontes

- [Keycloak — Release Notes](https://www.keycloak.org/docs/latest/release_notes/index.html)
- [Keycloak 26.3.0 released](https://www.keycloak.org/2025/07/keycloak-2630-released)
- [Fórum Keycloak — Email OTP em 26.1.3 exige SPI](https://forum.keycloak.org/t/we-need-to-implement-mfa-in-keycloak-26-1-3-with-totp-and-email-otp-and-want-to-confirm-if-custom-spis-are-required-for-email-otp-support-and-dual-authentication-selection/29837)
- [mesutpiskin/keycloak-2fa-email-authenticator](https://github.com/mesutpiskin/keycloak-2fa-email-authenticator)
- [for-keycloak/email-otp-authenticator](https://github.com/for-keycloak/email-otp-authenticator)
- [Keycloak Organizations — anúncio](https://www.keycloak.org/2024/06/announcement-keycloak-organizations)
- [Keycloak — Organization Groups](https://www.keycloak.org/2026/04/org-groups)
- [Keycloak 25.0.0 — Argon2 como hash padrão](https://www.keycloak.org/2024/06/keycloak-2500-released)
