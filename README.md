# MultiTenant SecureLogin Sample

Sample of a **multi-tenant** application with secure login, role-based access control and
an immutable audit trail. It is a portfolio excerpt of the identity layer of a larger
platform. It was built with Spec-Driven Development: specification, plan and tasks were
approved before any code was written.

> **License: reference only.** You may read and study the code. Copying, using or
> redistributing it requires permission. Details in [LICENSE](LICENSE).

## What the sample demonstrates

- **Direct login with a second factor** via a code sent by e-mail (Keycloak), with:
  - lockout after failed attempts, counting both password **and** code;
  - password recovery;
  - a breached-password list;
  - a password strength meter.
- **BFF-pattern session.** Tokens never reach the browser:
  - `__Host-`, `HttpOnly` and `SameSite` cookies;
  - CSRF protection via *double submit*;
  - 30 min idle timeout and 12 h maximum lifetime;
  - *back-channel logout*.
- **Multi-tenancy with PostgreSQL RLS.** Each transaction sets who is acting and in which
  organization, and no database role bypasses the policies.
- **Two levels of administration:**
  - a **Super Administrator** creates and suspends organizations without seeing anything
    inside them, which is enforced by the database;
  - an **Administrator** manages the people in their own organization.
- **Six fixed roles** enforced on every API route. A structural test fails CI if any route
  does not declare its protection.
- **Recent re-authentication** (password and code) before sensitive actions, when the
  login is more than 15 minutes old.
- **Append-only Audit Trail with a hash chain.** Trigger against `UPDATE` and `DELETE`,
  filtered queries, CSV export and retention-based purge of IP and browser data
  (LGPD, Brazil's data protection law).
- **Right-to-be-forgotten request** (LGPD): anonymizes the person without breaking the
  audit trail.

## Architecture

```text
Browser ──session cookie──▶ Studio (Next.js) ──/api──▶ Control Plane (FastAPI)
                                                          │   ├── PostgreSQL 17 (RLS, audit)
     login and code screens ◀── Keycloak (OIDC + PKCE) ◀──┘   ├── Valkey (sessions)
                                                              ├── OpenBao (token encryption)
                                                              └── SMTP (Mailpit locally)
```

| Folder | Contents |
|---|---|
| `services/control-plane/` | FastAPI API, Alembic migrations, `cap-admin` CLI, `cap-worker` worker |
| `apps/studio/` | UI (Next.js 16, React 19, shadcn/ui, TanStack Query) |
| `packages/api-client/` | TypeScript client generated from OpenAPI (orval) |
| `infra/` | Local Docker Compose, Keycloak image and realm (theme, e-mail code extension) |
| `tests/e2e/` | Playwright, desktop and mobile |
| `specs/001-identity-access/` | Specification, plan, tasks, contracts and checklists (OWASP ASVS L2, performance) |

Code comments and specs refer to the "constitution" and to `§N` sections of a product
reference. These are internal documents of the original project and are not included here.

## How to run

Prerequisites: Python 3.12 with [uv](https://docs.astral.sh/uv/), Node 24 with `corepack`
and Docker. On Windows, use `127.0.0.1` (not `localhost`) for PostgreSQL and Valkey.

```sh
uv sync && corepack pnpm install
uv run python infra/compose/init_env.py          # generates local credentials (.env, not in Git)
docker compose -f infra/compose/docker-compose.yml up -d

cd services/control-plane
export CAP_ENV_FILE=../../infra/compose/.env.control-plane
(set -a; . $CAP_ENV_FILE; uv run alembic upgrade head)
uv run uvicorn cap_control_plane.main:run --factory --host 127.0.0.1 --port 8000
uv run cap-worker                                 # in another terminal
uv run cap-admin bootstrap-super-admin --email you@example.com --name "Your Name"

cd ../../apps/studio && corepack pnpm dev        # http://localhost:3000
```

The activation link and login codes arrive in Mailpit, at http://localhost:8025.

## Tests and quality

| What | Command |
|---|---|
| Lint and types (Python) | `uv run ruff check services/` · `cd services/control-plane && uv run mypy` |
| Unit and contract tests | `cd services/control-plane && uv run pytest -m "not integration"` |
| Integration tests (real services) | `cd services/control-plane && uv run pytest` |
| Lint, types and Vitest (TypeScript) | `corepack pnpm lint` · `corepack pnpm typecheck` · `corepack pnpm test` |
| E2E | `corepack pnpm e2e` |

CI (`.github/workflows/ci.yml`) runs:
- lint, type checks and unit tests for Python and TypeScript;
- a check that the generated client is up to date with the OpenAPI spec;
- gitleaks;
- Trivy on the code and the images;
- the E2E tests against the project images, followed by a secret scan of the logs.

## License

Copyright © 2026 Fulvio Jorge da Silva. All rights reserved. Published for reference only,
as a portfolio sample. See [LICENSE](LICENSE).

Third-party components keep their own licenses, listed in the dependency manifests
(`pyproject.toml`, `package.json` and `infra/keycloak/providers.lock`).
