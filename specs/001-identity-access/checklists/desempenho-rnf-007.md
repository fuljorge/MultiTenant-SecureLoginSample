# Desempenho — RNF-007 (T075)

- **Data:** 2026-10-04
- **Como medir:** `corepack pnpm --filter e2e exec playwright test --config playwright.perf.config.ts`
  (`PERF_LOGINS`, padrão 50). Resultado também em `tests/e2e/test-results/perf-login.json`.
- **Ambiente:** local (Windows 11, Docker Desktop), Studio em build de produção
  (`next build` + `next start`), Control Plane com uvicorn, Keycloak 26.7.5, SMTP local
  (Mailpit). Uma volta de aquecimento não entra na conta.

| Etapa | p50 | p95 | Máximo | Meta (p95) | Situação |
|---|---|---|---|---|---|
| Abrir o login (Studio → tela do Keycloak) | 83 ms | 109 ms | 145 ms | 2 s | ✅ |
| Senha → tela do código | 127 ms | 137 ms | 143 ms | 2 s | ✅ |
| Código → tela inicial do Studio | 167 ms | 229 ms | 291 ms | 2 s | ✅ |
| E-mail com o código (envio → recebimento) | 83 ms | 94 ms | 103 ms | 60 s | ✅ |
| Troca de organização | 168 ms | 179 ms | 185 ms | 2 s | ✅ |

Revogação de sessão em até 60 s: verificada pelos testes de integração (desativação,
troca de senha e suspensão de organização encerram o acesso na requisição seguinte;
CS-005, CS-009).

**Limites desta medição:** uma só máquina e sem rede real. A entrega de e-mail por um SMTP
de verdade depende do provedor e do SPF/DKIM do domínio da instalação (plano, seção 10);
repetir esta medição no ambiente de homologação antes da produção.
