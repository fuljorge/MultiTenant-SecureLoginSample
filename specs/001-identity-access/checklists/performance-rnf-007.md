# Performance — RNF-007 (T075)

- **Date:** 2026-10-04
- **How to measure:** `corepack pnpm --filter e2e exec playwright test --config playwright.perf.config.ts`
  (`PERF_LOGINS`, default 50). The result is also written to `tests/e2e/test-results/perf-login.json`.
- **Environment:** local (Windows 11, Docker Desktop), Studio as a production build
  (`next build` + `next start`), Control Plane with uvicorn, Keycloak 26.7.5, local SMTP
  (Mailpit). One warm-up round is excluded from the results.

| Step | p50 | p95 | Max | Target (p95) | Status |
|---|---|---|---|---|---|
| Open the login (Studio → Keycloak screen) | 83 ms | 109 ms | 145 ms | 2 s | ✅ |
| Password → code screen | 127 ms | 137 ms | 143 ms | 2 s | ✅ |
| Code → Studio home screen | 167 ms | 229 ms | 291 ms | 2 s | ✅ |
| E-mail with the code (sent → received) | 83 ms | 94 ms | 103 ms | 60 s | ✅ |
| Organization switch | 168 ms | 179 ms | 185 ms | 2 s | ✅ |

Session revocation within 60 s: verified by the integration tests (deactivation, password
change and organization suspension end access on the next request; CS-005, CS-009).

**Limits of this measurement:** a single machine and no real network. E-mail delivery
through a real SMTP server depends on the provider and on the SPF/DKIM of the
installation's domain (plan, section 10); repeat this measurement in the staging
environment before production.
