# Checklist OWASP ASVS nível 2 — identidade e acesso (T076)

- **Feature:** 001-identity-access · **Padrão:** OWASP ASVS 4.0.3, nível 2 · **Capítulos:**
  V2 (autenticação), V3 (sessão), V4 (controle de acesso)
- **Data:** 2026-10-04 · **Preenchido por:** agente de código, para revisão humana
- **Legenda:** ✅ atende · ⚠️ atende em parte (ver pendência) · ➖ não se aplica

A autenticação é do Keycloak 26.7.5 (realm `infra/keycloak/realm/cap-realm.yaml`); a sessão
do navegador e a autorização são do Control Plane (padrão BFF; plano, seções 4.1 e 4.2).

## V2 — Autenticação

| Item | Requisito (resumo) | Situação | Como é atendido / evidência |
|---|---|---|---|
| 2.1.1 | Senha com 12+ caracteres | ✅ | `length(12)` no realm; mínimo não afrouxável pela tela de segurança (`security_settings.py`) |
| 2.1.2 | Aceitar 64+ e recusar 128+ caracteres | ✅ | `maxLength(128)` fixo; `test_politica_aceita_64_e_recusa_mais_de_128_caracteres` |
| 2.1.3 | Sem truncamento | ✅ | Hash Argon2 do Keycloak sobre a senha inteira |
| 2.1.4 | Qualquer caractere Unicode | ✅ | Política sem restrição de caracteres |
| 2.1.5 | Pessoa troca a própria senha | ✅ | Menu "Trocar senha" (`GET /auth/password`, ação `UPDATE_PASSWORD`) |
| 2.1.6 | Troca exige a senha atual | ✅ | A troca da própria senha sempre pede nova autenticação, com senha e código (`prompt=login`, `max_age=0`; RF-031); `test_troca_de_senha_sempre_reautentica` |
| 2.1.7 | Recusar senhas vazadas | ✅ | `passwordBlacklist` com a lista Pwdb top 1M (research R5); `test_politica_recusa_senha_vazada` |
| 2.1.8 | Medidor de força da senha | ✅ | Indicador no tema `cap` do Keycloak, nas telas de definir e trocar senha (RF-032); E2E de ativação |
| 2.1.9 | Sem regras de composição | ✅ | Só tamanho, lista de vazadas, histórico e "diferente do e-mail" |
| 2.1.10 | Sem troca periódica obrigatória | ✅ | Nenhuma política de expiração |
| 2.1.11 | Colar e gerenciador de senhas permitidos | ✅ | Campos padrão do tema, sem bloqueio de colar |
| 2.1.12 | Mostrar a senha digitada | ✅ | Botão "Exibir senha" no tema `cap` |
| 2.2.1 | Proteção contra força bruta | ✅ | Bloqueio de 15 min após 5 falhas de senha **ou de código** (achado A15, patch); testes do realm |
| 2.2.2 | E-mail só como fator secundário | ✅ | O código por e-mail é o segundo fator, depois da senha; fatores mais fortes (aplicativo, chave física) previstos para fase futura (spec, fora de escopo) |
| 2.2.3 | Avisar a pessoa após mudança de credencial | ✅ | E-mail de senha alterada (worker, RF-005) e aviso ao e-mail antigo na troca de e-mail |
| 2.3.1 | Credenciais iniciais aleatórias e com validade | ✅ | Links de ativação de uso único (72 h) e recuperação (30 min); nenhuma senha inicial enviada |
| 2.4.1–2.4.5 | Armazenamento de senhas | ✅ | Delegado ao Keycloak (Argon2); o Control Plane nunca recebe senhas |
| 2.5.1 | Ativação não envia segredo em texto claro | ✅ | Só link de uso único |
| 2.5.2 | Sem dicas ou perguntas secretas | ✅ | Não existem |
| 2.5.3 | Recuperação não revela a senha atual | ✅ | Recuperação por link do Keycloak |
| 2.5.4 | Sem contas compartilhadas ou padrão | ✅ | O realm `cap` não tem contas padrão (`test_realm_sem_administradores_ou_clientes_extras`); o administrador de bootstrap do realm `master` é temporário em toda instalação (requisito do provisionamento, §53.2) |
| 2.5.5 | Avisar quando o fator de autenticação muda | ✅ | Como 2.2.3 |
| 2.5.6 | Recuperação segura | ✅ | Link de uso único com prazo; resposta igual para e-mail existente ou não (`test_enumeration.py`) |
| 2.5.7 | Perda do fator exige reidentificação | ✅ | Troca de e-mail confirmada pelo novo endereço; Super Administrador sem e-mail: `cap-admin reissue-activation` com chamado e verificação de identidade |
| 2.7.1 | Sem SMS ou telefone por padrão | ✅ | Só e-mail |
| 2.7.2 | Código expira em até 10 min | ✅ | 10 min (máximo configurável: 15 min) |
| 2.7.3 | Código de uso único | ✅ | Consumido no login e invalidado após 5 tentativas (patch A15) |
| 2.7.4 | Canal seguro até o autenticador | ✅ | SMTP com TLS obrigatório em toda instalação (requisito do provisionamento, §53.2; `KC_SMTP_STARTTLS`, `smtp_starttls`); só o ambiente local usa o Mailpit sem TLS |
| 2.7.5 | Código guardado só como hash | ✅ | SHA-256 na sessão de autenticação, comparação em tempo constante (research R1, item 1) |
| 2.7.6 | Código com gerador seguro e 20+ bits | ✅ | `SecretGenerator` do Keycloak, 6 dígitos (~20 bits), com bloqueio por tentativas |
| 2.8.x | OTP por aplicativo ou dispositivo | ➖ | Não oferecido nesta fase |
| 2.9.x | Verificador criptográfico | ➖ | Não oferecido nesta fase |
| 2.10.1 | Segredos entre serviços fora do código | ✅ | Variáveis de ambiente geradas por `init_env.py`; chave de cifra no OpenBao |
| 2.10.2 | Sem credenciais padrão entre serviços | ✅ | Todas geradas aleatoriamente por instalação |
| 2.10.3 | Credenciais de serviço protegidas | ✅ | Na produção, injetadas pelo OpenBao ou pelos segredos do cluster (requisito do provisionamento, §53.2); no ambiente local, `.env` fora do Git e da imagem (`.dockerignore`) |
| 2.10.4 | Segredos fora do código-fonte | ✅ | gitleaks no pre-commit e no CI |

## V3 — Sessão

| Item | Requisito (resumo) | Situação | Como é atendido / evidência |
|---|---|---|---|
| 3.1.1 | Token de sessão fora da URL | ✅ | Só em cookie |
| 3.2.1 | Novo token a cada autenticação | ✅ | Sessão criada no callback do login |
| 3.2.2 | 64+ bits de entropia | ✅ | 256 bits (`secrets`); no Valkey só o SHA-256 |
| 3.2.3 | Token só em cookie seguro | ✅ | Tokens do Keycloak ficam no servidor, cifrados pelo OpenBao Transit |
| 3.2.4 | Gerador criptográfico | ✅ | Módulo `secrets` |
| 3.3.1 | Logout invalida a sessão | ✅ | BFF e Keycloak; back-channel logout |
| 3.3.2 | Reautenticação periódica | ✅ | Inatividade de 30 min e máximo de 12 h, no BFF e no Keycloak; a tela de segurança não aceita sessão máxima acima de 24 h |
| 3.3.3 | Encerrar outras sessões ao trocar a senha | ✅ | Toda troca de senha encerra **todas** as sessões (RF-005) |
| 3.3.4 | Ver e encerrar as próprias sessões | ✅ | "Minhas sessões" (RF-006) |
| 3.4.1 | Atributo `Secure` | ✅ | `cookies.py` |
| 3.4.2 | Atributo `HttpOnly` | ✅ | No cookie de sessão; o cookie anti-CSRF é legível de propósito (double submit) |
| 3.4.3 | Atributo `SameSite` | ✅ | `Lax` |
| 3.4.4 | Prefixo `__Host-` | ✅ | `__Host-cap_session`, `__Host-cap_csrf`, `__Host-cap_login` |
| 3.4.5 | Escopo de caminho | ✅ | `Path=/`, sem `Domain` |
| 3.5.1 | Revogar tokens OAuth | ✅ | Encerrar a sessão apaga os tokens guardados e faz logout no Keycloak |
| 3.5.2 | Sessão não usa segredo estático | ✅ | Sessão por pessoa e por login |
| 3.5.3 | Tokens sem estado assinados e validados | ✅ | ID token validado (RS256, JWKS do realm, `nonce`) com joserfc |
| 3.7.1 | Reautenticação antes de ações sensíveis | ✅ | As 17 ações do RF-031 exigem login completo há no máximo 15 min (`require_recent`); lista conferida contra o contrato; `test_recent_auth.py` e E2E de gestão de usuários |

## V4 — Controle de acesso

| Item | Requisito (resumo) | Situação | Como é atendido / evidência |
|---|---|---|---|
| 4.1.1 | Regras aplicadas no servidor | ✅ | `require`/`require_any` em toda rota e RLS no PostgreSQL; teste estrutural de rotas (T058) |
| 4.1.2 | Atributos de autorização não manipuláveis | ✅ | Perfil e organização vêm do banco a cada requisição, nunca do cliente |
| 4.1.3 | Menor privilégio | ✅ | Matriz da spec (seção 5.1) lida pelo teste; Super Administrador sem acesso ao conteúdo das organizações (RF-028) |
| 4.1.5 | Falha segura | ✅ | Negação por padrão; rota sem proteção declarada reprova o CI |
| 4.2.1 | Proteção contra acesso direto a objetos (IDOR) | ✅ | RLS por organização; recurso de outra organização responde 404 e gera `access.denied` (`test_cross_org.py`, `test_super_admin_rls.py`) |
| 4.2.2 | Proteção contra CSRF | ✅ | Cabeçalho `X-CSRF-Token` (double submit) e `SameSite=Lax` |
| 4.3.1 | Interfaces administrativas com MFA | ✅ | Segundo fator obrigatório para todos, inclusive administradores |
| 4.3.2 | Sem listagem de diretórios nem metadados expostos | ✅ | `/docs` e `/openapi.json` desligados por padrão (`CAP_API_DOCS`); nenhum diretório servido |
| 4.3.3 | Segregação de funções em sistemas de alto valor | ✅ | Super Administrador separado dos perfis de organização, com *trigger* que impede vínculo (RF-028); último Administrador e último Super Administrador protegidos (RF-012) |

## Pendências para revisão

Decididas em 2026-10-04 (Fulvio Jorge da Silva) e resolvidas:

| # | Itens | Decisão | Onde |
|---|---|---|---|
| P1 | 2.1.6, 3.7.1 | Reautenticação recente na Fase 1 | RF-031; T093–T097, T099 |
| P2 | 2.1.8 | Medidor de força da senha | RF-032; T098 |
| P3 | 2.5.4 | Administrador de bootstrap do Keycloak temporário | Requisito do provisionamento (§53.2) |
| P4 | 2.7.4 | SMTP sempre com TLS | Requisito do provisionamento (§53.2) |
| P5 | 2.10.3 | Segredos de serviço pelo OpenBao ou pelo cluster | Requisito do provisionamento (§53.2) |

P3 a P5 são verificados na feature de provisionamento, que cria as instalações.
