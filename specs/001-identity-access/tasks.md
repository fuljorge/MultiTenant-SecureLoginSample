# Tasks: User Identity, Authentication and Access Control

- **ID:** 001-identity-access
- **Spec / Plan:** [spec.md](spec.md) · [plan.md](plan.md) (both approved on
  2026-10-03, Super Administrator revision)
- **Status:** Approved <!-- Draft | Approved -->
- **Amendment 2026-10-04:** new Phase 10 (T093–T099: recent re-authentication and
  strength meter), analysis (A20, A21) and traceability (RF-031, RF-032).
- **Revision 2026-10-03:** new Phase 7 (migration to the Super Administrator,
  T080–T090), US5 rewritten (T060–T064, T091, T092), adjustments to T065 and T066,
  dependencies, analysis (A16–A19) and traceability.
- **Created on:** 2026-10-02
- **Approved by / on:** Fulvio Jorge da Silva / 2026-10-04 (ASVS amendment; previous
  versions approved on 2026-10-02 and 2026-10-03)

## Format

`- [ ] T001 [P] [US1] Description with path/to/file`

- `[P]`: can run in parallel (different files, no pending dependency).
- `[US1]`: spec story served (setup and foundation phases carry no marker).
- Tests come before the corresponding implementation and must fail before it.

Abbreviated paths: `cp/` = `services/control-plane/`, `cpkg/` =
`services/control-plane/src/cap_control_plane/`, `studio/` = `apps/studio/`.

## Phase 1 — Setup

- [x] T001 Create the monorepo: `pyproject.toml` (uv workspace), `pnpm-workspace.yaml`,
  `.editorconfig` and the `apps/`, `services/`, `packages/`, `infra/`, `tests/` folders
- [x] T002 [P] Create the Control Plane project in `cp/pyproject.toml` (FastAPI,
  Pydantic v2, SQLAlchemy 2, Alembic, Authlib, httpx, redis-py, OpenTelemetry) with
  Ruff (including `S` rules) and strict mypy; minimal app with `/healthz` in `cpkg/main.py`
- [x] T003 [P] Create the Studio in `studio/` (Next.js, strict TypeScript, Tailwind,
  shadcn/ui, TanStack Query/Table, i18next, ESLint + Prettier, Vitest) with the media kit
  tokens in `studio/src/styles/tokens.css` and dark theme by default
- [x] T004 [P] Configure Playwright in `tests/e2e/` (`playwright.config.ts` with desktop
  and mobile projects; helper that reads e-mails from Mailpit)
- [x] T005 [P] Create `.gitleaks.toml` and `.pre-commit-config.yaml` (gitleaks, Ruff,
  Prettier)
- [x] T006 Create `infra/compose/docker-compose.yml` with PostgreSQL 17 (`cap` and
  `keycloak` databases), Valkey, OpenBao (dev mode, Transit enabled) and Mailpit
- [x] T007 Create `.github/workflows/ci.yml` with jobs: Ruff + mypy + unit pytest;
  ESLint + `tsc` + Vitest; gitleaks; Trivy in filesystem mode

## Phase 2 — Foundation (blocks the stories)

### Keycloak

- [x] T008 **Blocking R1 check** of the `keycloak-2fa-email-authenticator` extension:
  (1) is the code stored in clear text in the authentication session? (2) does it emit
  send, resend and failure events? (3) does a resend invalidate the previous code? (4)
  which Keycloak version is supported? (5) do code failures count toward Keycloak's
  attempt lockout (RF-003)? Record the result in `research.md` (R1). If any item fails
  with no possible fix, **stop** and bring plan B up for decision
- [x] T009 Create `infra/keycloak/Dockerfile` (official image at the version defined in
  T008, optimized build) and `infra/keycloak/providers.lock` with the extension's URL,
  version and SHA-256; the build fails if the checksum does not match
- [x] T010 [P] Create the `infra/keycloak/themes/cap/` theme (login: CSS with the tokens,
  `messages_pt_BR.properties`; e-mail: Brazilian Portuguese templates for code,
  invitation/welcome and password recovery)
- [x] T011 Create `infra/keycloak/realm/cap-realm.yaml` per the plan (§4.9): password →
  code flow, registration disabled, login by e-mail, brute force, password policy with
  the SecLists list (downloaded with checksum), session and link timeouts, events kept
  for 7 days, `cap-control-plane` and `cap-admin-bridge` clients; add Keycloak and
  keycloak-config-cli to compose
- [x] T012 [P] Realm integration test in `cp/tests/integration/keycloak/test_realm.py`:
  login requires a code, registration disabled, password policy rejects a password from
  the list, lockout after 5 failures (password and code); the realm has no administrative
  users other than the `cap-admin-bridge` service account, and no clients beyond the
  planned ones (RF-024)

### Control Plane base

- [x] T013 Create test fixtures in `cp/tests/conftest.py` with Testcontainers
  (PostgreSQL, Valkey, OpenBao, Mailpit, Keycloak with the project's image and realm)
- [x] T014 [P] Create `cpkg/core/settings.py`, `cpkg/core/secrets.py` (reading secrets and
  encrypt/decrypt via OpenBao Transit) and `cpkg/core/telemetry.py` (OpenTelemetry)
- [x] T015 [P] Test in `cp/tests/unit/core/test_logging.py`: password, code, token, link,
  full e-mail and full IP are redacted in logs
- [x] T016 Create `cpkg/core/logging.py` (structured logs with redaction of sensitive
  fields)
- [x] T017 [P] Create `cpkg/core/email.py` (SMTP with Brazilian Portuguese templates for
  Control Plane notices)

### Database and isolation

- [x] T018 RLS integration test in `cp/tests/integration/db/test_rls.py`: without context
  reads nothing; with organization A does not read B's `membership`/`invitation`;
  installation Administrator reads all; the application role has no `BYPASSRLS`
- [x] T019 Create `cpkg/core/db.py` (engine, session, `SET LOCAL app.user_id`,
  `app.organization_id`, `app.is_installation_admin` per transaction) and the
  application's database role
- [x] T020 Alembic migration for the `identity` schema in `cp/migrations/` (tables from
  [data-model.md](data-model.md), enums, indexes, RLS policies)

### Audit Trail

- [x] T021 [P] Chain unit tests in `cp/tests/unit/audit/test_chain.py`
  (canonical JSON, chaining, tamper detection)
- [x] T022 Integration test in `cp/tests/integration/audit/test_audit_store.py`:
  `UPDATE`/`DELETE`/`TRUNCATE` rejected; concurrent writes keep the chain intact;
  `details` without forbidden fields
- [x] T023 Alembic migration for the `audit` schema (`audit_event`, `audit_event_origin`,
  `keycloak_event_cursor`, `INSERT`/`SELECT`-only privileges, anti-change trigger)
- [x] T024 Create `cpkg/audit/chain.py`, `cpkg/audit/writer.py` (serialized writes with an
  advisory lock) and `cpkg/audit/verify.py`
- [x] T025 Configure the compose PostgreSQL to log trigger rejections and document in
  `infra/README.md` the alert rule that produces `audit.tamper_attempt` (collected by
  observability)

### Permissions and sessions

- [x] T026 [P] Matrix unit tests in `cp/tests/unit/identity/test_permissions.py`:
  role × permission table equal to spec section 5.1, Administrator scopes, deny by
  default
- [x] T027 Create `cpkg/identity/permissions.py` (catalog, matrix, `require(permission)`
  dependency that responds `403` and records `access.denied`), including
  `costs:read:own`, unused in this feature
- [x] T028 [P] Integration tests in `cp/tests/integration/identity/test_sessions.py`:
  creation, renewal up to 30 min of inactivity, 12 h limit, revocation of all of a
  user's sessions, encrypted tokens in Valkey, `sid` stored as a hash
- [x] T029 Create `cpkg/identity/sessions.py`
- [x] T030 [P] Admin API client integration tests in
  `cp/tests/integration/identity/test_keycloak_admin.py` (create user, e-mail actions,
  disable, logout, read events and lockout status)
- [x] T031 Create `cpkg/identity/keycloak_admin.py` (service account, httpx, timeouts and
  retries)

## Phase 3 — US1: Login with an e-mail second factor (P1) — MVP

**Goal:** a registered user signs in with password and code, uses the platform and signs
out. **Independent test:** spec, US1.

### Tests

- [x] T032 [P] [US1] BFF integration tests in
  `cp/tests/integration/identity/test_bff_auth.py`: `state` and PKCE, `__Host-` cookie
  with `HttpOnly`/`Secure`/`SameSite=Lax`, CSRF rejected without the header, logout,
  back-channel logout ends the BFF session; the user lists their own sessions and ends
  one of them (RF-006)
- [x] T033 [P] [US1] Worker integration tests in
  `cp/tests/integration/audit/test_keycloak_ingestor.py`: imports events without
  duplicates, maps them to the catalog, a password change ends BFF sessions and sends a
  notice; with SMTP unavailable, the login does not complete and Keycloak logs the error
- [x] T034 [P] [US1] E2E in `tests/e2e/login.spec.ts`: login with the code read from
  Mailpit; wrong, expired and resent code; lockout after 5 failures; generic message;
  logout; inactivity (short timeout in the test environment); password recovery with
  notice and sessions ended; mobile viewport
- [x] T035 [P] [US1] Enumeration test in `cp/tests/integration/identity/test_enumeration.py`:
  same response and similar timing for existing and non-existing e-mails (login and
  recovery)

### Implementation

- [x] T036 [US1] Create `cpkg/identity/oidc.py` (Authlib, Authorization Code + PKCE) and
  `cpkg/identity/api/auth.py` (`/auth/login`, `/auth/callback`, `/auth/logout`,
  `/auth/backchannel-logout`, `/auth/password`)
- [x] T037 [US1] Create the session and CSRF middleware in `cpkg/identity/middleware.py`
  and the `GET /me` route in `cpkg/identity/api/me.py`
- [x] T038 [US1] Create `cpkg/audit/keycloak_ingestor.py` (polls every 5 s, cursor,
  deduplication, mapping; on password change removes BFF sessions and sends a notice;
  login, failure and lockout metrics; cursor lag alert — RNF-004)
- [x] T039 [US1] Create `GET /me/sessions` and `DELETE /me/sessions/{id}` in
  `cpkg/identity/api/me.py`
- [x] T040 [US1] In the Studio: `studio/src/lib/auth/` (query `/me`, send the CSRF token,
  redirect to login), protected layout, Sign out button, "Change password" link and the
  `studio/src/app/(app)/conta/sessoes/` screen
- [x] T041 [US1] Generate the client in `packages/api-client/` (orval) and add to CI the
  drift check against the OpenAPI

**Checkpoint:** US1 works and is testable on its own (user created by a fixture).

## Phase 4 — US2: First access of the initial Administrator (P1)

### Tests

- [x] T042 [P] [US2] Integration test in `cp/tests/integration/cli/test_bootstrap.py`:
  `bootstrap-admin` creates the default organization, the Keycloak user, the membership
  and the installation scope and sends the e-mail; `reissue-activation` with and without
  a new e-mail; events with `actor_kind = support`
- [x] T043 [P] [US2] E2E in `tests/e2e/activation.spec.ts`: welcome link → set password →
  login with code → home screen; an already used or expired link is rejected

### Implementation

- [x] T044 [US2] Create `cpkg/cli/cap_admin.py` (`bootstrap-admin`,
  `reissue-activation`, with a mandatory ticket number for the latter)
- [x] T045 [US2] In the login callback, activate the user and `pending` memberships and
  record `user.activated`

**Checkpoint:** a new installation delivers a working initial Administrator.

## Phase 5 — US3: User management by the Administrator (P1)

### Tests

- [x] T046 [P] [US3] Integration tests in `cp/tests/integration/identity/test_users.py`:
  invitation of a new person and of an already registered person; invitation
  revocation; role change takes effect on the next request; deactivation revokes
  sessions within 60 s; reactivation; last installation Administrator (including two
  simultaneous operations); concurrent edit responds `412`; filtered listing
- [x] T047 [P] [US3] Integration tests in `cp/tests/integration/identity/test_email_change.py`:
  confirmation via the new e-mail, sessions ended, notice to the old one, single-use and
  expired token
- [x] T048 [P] [US3] Integration tests in `cp/tests/integration/identity/test_security_settings.py`:
  reading and writing the realm, including the validity of invitations and activation
  links (RF-010); minimum limits rejected (RF-007)
- [x] T049 [P] [US3] E2E in `tests/e2e/user-management.spec.ts`: Administrator invites →
  person activates → Administrator changes role → disables → person loses access

### Implementation

- [x] T050 [US3] Create `cpkg/identity/service/users.py` and `cpkg/identity/service/invitations.py`
  (invitation, activation, deactivation, last Administrator and optimistic lock rules)
- [x] T051 [US3] Create `cpkg/identity/service/email_change.py`
- [x] T052 [US3] Create the user, invitation and e-mail change routes in
  `cpkg/identity/api/users.py`
- [x] T053 [US3] Create `cpkg/identity/api/security_settings.py`
- [x] T054 [US3] In the Studio: `studio/src/app/(app)/admin/usuarios/` (filtered list,
  invitation, detail, change role, disable/re-enable, change e-mail, end sessions) and
  `studio/src/app/(app)/admin/seguranca/`

**Checkpoint:** the Administrator manages the team without the vendor.

## Phase 6 — US4: Role-based access (P1)

### Tests

- [x] T055 [P] [US4] Table-driven test in
  `cp/tests/integration/identity/test_route_permissions.py`: for each route of the
  feature and each role, expected response (`2xx` or `403`) and `access.denied`
  recorded; fails if any route has no declared permission; no role or route grants
  access to the vendor (RF-024)
- [x] T056 [P] [US4] Component test in `studio/src/components/nav/nav.test.tsx`: menus
  shown according to the `/me` permissions
- [x] T057 [P] [US4] E2E in `tests/e2e/profiles.spec.ts`: a Business Analyst does not see
  administration and gets `403` when calling the API directly

### Implementation

- [x] T058 [US4] Ensure `require()` on every route and register in CI the test for routes
  without permission
- [x] T059 [US4] Permission-driven Studio navigation in `studio/src/components/nav/`

**Checkpoint:** all P1 stories delivered (MVP).

## Phase 7 — Migration to the Super Administrator (revision 2026-10-03; blocks US5)

Adapts what US1–US4 delivered (plan, section 12). At the end of this phase, the
installation Administrator no longer exists and the Super Administrator reads nothing
inside organizations.

### Tests

- [x] T080 [P] Unit tests in `cp/tests/unit/identity/test_permissions.py` and
  `cp/tests/unit/identity/test_route_permissions.py`: installation permissions
  (`SUPER_ADMIN_PERMISSIONS`) and organization permissions are disjoint; the Super
  Administrator receives no organization permission; no role receives an installation
  permission; every permission belongs to some role or to the Super Administrator
  (RF-016, RF-024, RF-028)
- [x] T081 [P] Integration test in `cp/tests/integration/identity/test_super_admin_rls.py`:
  queries run directly in the database with the Super Administrator context see all
  organizations, only memberships and invitations with the `administrator` role, only
  people who are Administrators or Super Administrators and no e-mail change; inserting a
  membership with another role is rejected; the *trigger* rejects a membership for a
  Super Administrator and a Super Administrator for someone with an active membership
  (RF-028, RNF-001)
- [x] T082 [P] Integration test in `cp/tests/integration/test_migration_0004.py`: starting
  from the 0003 state with an installation Administrator, memberships and a default
  organization, 0004 creates `super_admin`, marks their memberships as `removed`, records
  `super_admin.converted`, leaves existing organizations `active`, drops `is_default` and
  keeps the audit chain valid
- [x] T083 [P] Adjust the existing tests to the new model: `tests/support/people.py`
  (`create_person(super_admin=...)`), `tests/support/seed_person.py` (`--super-admin`),
  `test_activation.py` (US2 creates the initial Super Administrator, with no
  organization), `test_users.py` (per-membership deactivation, last Administrator per
  organization), `test_security_settings.py` (Super Administrator only), the
  `test_route_permissions.py` matrix with the Super Administrator as principal (`403` and
  `access.denied` on every organization route) and the E2E `activation.spec.ts`,
  `user-management.spec.ts` and `profiles.spec.ts`

### Implementation

- [x] T084 Migration `cp/migrations/versions/0004_super_admin.py` per
  [data-model.md](data-model.md): `super_admin` (from `installation_admin`), the
  `identity.is_super_admin()` function and per-table policies replacing
  `has_installation_scope()`, the RF-028 *triggers*, `organization.status` and status
  columns, `membership.status` with `disabled`, `audit_event.installation_scope`, removal
  of `is_default` and conversion of existing data
- [x] T085 Permissions and principal: `cpkg/identity/permissions.py`
  (`SUPER_ADMIN_PERMISSIONS`, `effective_permissions` without mixing), `cpkg/core/db.py`
  (`DbContext.is_super_admin`), `cpkg/identity/authz.py` and `cpkg/identity/directory.py`
  (Super Administrator without an organization; the organization must be `active` in the
  per-request revalidation)
- [x] T086 Login and `/me`: the Super Administrator signs in without an active
  organization; `GET /me` reports the principal type; regenerate the OpenAPI and the
  TypeScript client
- [x] T087 Users (US3) per membership: `cpkg/identity/service/users.py` and
  `cpkg/identity/api/users.py` with membership deactivation and reactivation (account
  only when there is no other active membership), last Administrator per organization
  with locking (RF-012), e-mail change rejected (`409`) for someone who belongs to other
  organizations
- [x] T088 Audit: `installation_scope` in `cpkg/audit/chain.py` and
  `cpkg/audit/writer.py` (part of the hash); Super Administrator events record the
  affected organization and `installation_scope = true`
- [x] T089 CLI: `cap-admin bootstrap-super-admin` (no organization) and
  `reissue-activation` for the Super Administrator, in `cpkg/cli/cap_admin.py`; update
  `infra/README.md`
- [x] T090 Studio: menus per principal type (Organizations, Super Administrators and
  Security for the Super Administrator), header showing "Super Administrator" in place of
  the organization, Super Administrator home page; update
  `studio/src/components/nav/nav.test.tsx`

**Checkpoint:** all existing tests pass on the new model, and the Super Administrator
gets `403` on every organization route.

## Phase 8 — US5: Organization management by the Super Administrator (P1)

### Tests

- [x] T060 [P] [US5] Integration tests in `cp/tests/integration/identity/test_organizations.py`:
  organization invitation for a new person and for an already registered person
  (`pending` organization, active when the Administrator activates access); only the
  Super Administrator creates (an organization Administrator gets `403` and
  `access.denied`); filtered list; rename with `If-Match`; resend and cancel a pending
  invitation; invitation to a Super Administrator's e-mail rejected; invite, disable and
  re-enable an Administrator, with `409` for the last active one; suspend (organization
  sessions removed, access denied on the next request, CS-009) and reactivate (new
  login); a person with another active organization loses only the suspended one;
  organization switch only for a valid membership and an active organization
- [x] T061 [P] [US5] Isolation test in `cp/tests/integration/identity/test_cross_org.py`:
  for each route, a user from A accessing a resource of B → `404`/`403` and
  `access.denied`
- [x] T091 [P] [US5] Integration tests in `cp/tests/integration/identity/test_super_admins.py`:
  invite, disable and re-enable a Super Administrator; `409` for the last active one
  (RF-012, RF-030); invitation rejected for an e-mail with an organization membership
  (RF-028)
- [x] T062 [P] [US5] E2E in `tests/e2e/specs/organizations.spec.ts`: the Super
  Administrator invites an organization; the invitee activates via e-mail (Mailpit) and
  signs in as Administrator; the Super Administrator sees the active organization and its
  Administrator, gets "No permission" on Users and suspends the organization, and the
  Administrator loses access; a person with two organizations switches via the selector
  and sees only the active one's data; mobile viewport

### Implementation

- [x] T063 [US5] Create `cpkg/identity/service/organizations.py` and
  `cpkg/identity/api/organizations.py` (the contract's organization and organization
  Administrator routes) and `PUT /me/active-organization`
- [x] T092 [US5] Create `cpkg/identity/service/super_admins.py` and
  `cpkg/identity/api/super_admins.py`
- [x] T064 [US5] In the Studio: `studio/src/components/org-switcher/` (only shown with
  more than one organization), `studio/src/app/(app)/admin/organizacoes/` (list,
  invitation, detail with Administrators, suspend and reactivate) and
  `studio/src/app/(app)/admin/super-administradores/`

**Checkpoint:** all P1 stories of the revised spec delivered.

## Phase 9 — US6: Access auditing (P2)

### Tests

- [x] T065 [P] [US6] Integration tests in `cp/tests/integration/audit/test_audit_api.py`:
  filters; the Administrator sees the organization's events, including the Super
  Administrator's actions on it; the Super Administrator sees only those with
  `installation_scope` or performed by Super Administrators; CSV export records
  `audit.exported`
- [x] T066 [P] [US6] Coverage test in `cp/tests/unit/audit/test_event_catalog.py`
  (static: needs no services):
  each type in [contracts/audit-events.md](contracts/audit-events.md) is produced by
  some scenario, with the RF-022 fields (CS-006)
- [x] T067 [P] [US6] Purge integration test in
  `cp/tests/integration/audit/test_origin_purge.py`: removes old origin data, records
  `audit.origin_purged`, the chain stays valid

### Implementation

- [x] T068 [US6] Create `cpkg/audit/api.py` (query and export)
- [x] T069 [US6] Create `cpkg/audit/purge.py` (daily routine in the worker process) and
  the `cap-admin audit verify` command
- [x] T070 [US6] In the Studio: `studio/src/app/(app)/admin/auditoria/` (filters, table,
  export)

## Final phase — Polish

- [x] T071 [P] Test in `cp/tests/integration/test_no_secret_leak.py` and a CI step that
  scans the E2E run logs for passwords, codes, tokens and links (CS-007)
- [x] T072 [P] Create the `cap-admin anonymize-user` command (right-to-be-forgotten
  request, LGPD) with a test in `cp/tests/integration/cli/test_anonymize.py`
- [x] T073 [P] Create `services/control-plane/Dockerfile` and `apps/studio/Dockerfile`;
  add to CI the build and Trivy scan of the three images (Control Plane, Studio,
  Keycloak), failing on high or critical vulnerabilities without a recorded mitigation
- [x] T074 Add the E2E job to CI (starts compose, runs Playwright desktop and mobile)
- [x] T075 Measure the RNF-007 targets with `tests/e2e/perf/login-timing.spec.ts` (p95 of
  50 logins: time of each step, arrival of the code e-mail, organization switch) and
  record the result in the PR
- [x] T076 Fill in `specs/001-identity-access/checklists/asvs-l2.md` (OWASP ASVS chapters
  V2, V3 and V4)
- [x] T077 Update `AGENTS.md` (section 9: install, local environment, test and lint
  commands) and the project status
- [x] T078 [P] Contract test in `cp/tests/contract/test_identity_contract.py`: every route
  in [contracts/identity-api.md](contracts/identity-api.md) exists in the OpenAPI with the
  stated method and permission, and the OpenAPI has no route outside the contract
- [ ] T079 User validation script in
  `specs/001-identity-access/checklists/user-validation.md` for CS-001, CS-002 and
  CS-003 (activation, invitation and login times measured with real people), run at the
  completion stage

## Phase 10 — Recent re-authentication and strength meter (amendment 2026-10-04)

### Tests

- [x] T093 [P] Unit test in `cp/tests/unit/identity/test_route_permissions.py`: the
  RF-031 routes (list in the contract) declare `require_recent_auth`, and no other does
- [x] T094 [P] Integration tests in `cp/tests/integration/identity/test_recent_auth.py`:
  a sensitive action with a login older than 15 min responds `401 reauth_required` and
  changes nothing; with a recent login, it proceeds; `GET /auth/login?reauth=1` sends
  `prompt=login` and `max_age=0` and replaces the previous session; `GET /auth/password`
  sends `max_age=0`; refreshing tokens does not change `auth_time`
- [x] T095 [P] Component test in `studio/src/lib/auth/reauth.test.ts`: the
  `reauth_required` error leads to the new authentication with the current screen as the
  return target

### Implementation

- [x] T096 `auth_time` in the session (`cpkg/identity/sessions.py`, callback),
  `require_recent_auth` dependency in `cpkg/identity/authz.py`, `reauth=1` and
  `max_age=0` in `cpkg/identity/oidc.py` and `cpkg/identity/api/auth.py`; apply to the
  RF-031 routes and mark them in the `contracts/identity-api.md` contract
- [x] T097 Studio: handling of `reauth_required` in the client and in the UI (message on
  return); regenerate the client
- [x] T098 Strength meter in the Keycloak `cap` theme (`infra/keycloak/themes/cap/`), on
  the set and change password screens; E2E in `tests/e2e/specs/activation.spec.ts` checks
  the indicator; test in `cp/tests/unit/test_keycloak_theme.py`
- [x] T099 Update `checklists/asvs-l2.md` (2.1.6, 2.1.8, 3.7.1 and open items) and the
  E2E `tests/e2e/specs/user-management.spec.ts` with a sensitive action after the new
  authentication

**Checkpoint:** ASVS checklist open items P1 and P2 resolved.

## Dependencies and order

- Setup (T001–T007) → Foundation (T008–T031) → US1 → US2 → US3 → US4 → Migration to the
  Super Administrator (T080–T090) → US5 → US6 → Polish.
- In the migration: T084 → T085 → T086 → T087; T088 and T089 after T084; T090 after
  T086 (generated client).
- **T008 blocks T009–T012** and, consequently, all stories.
- In the Foundation: T013 before the integration tests; T018 → T019 → T020; T022 → T023 →
  T024; T026 → T027; T028 → T029; T030 → T031.
- US2 depends on US1 (login callback). US3 depends on US2 (existing Administrator).
  US4 only closes after the US1–US3 routes exist. US5 and US6 depend on the migration
  (T080–T090) and can proceed in parallel after it.
- T041 (generated client) before the Studio screens that consume the API (T040 onward).

## Analysis (filled in before implementing)

Run on 2026-10-02 over the spec, plan, research, data model, contracts, tasks and
constitution v1.1.0. Revised on 2026-10-03 for the Super Administrator (A16–A19).

| Check | Result |
|---|---|
| Every RF/RNF has a task | ✅ after adjustments A1–A8 (matrix below) |
| Every task maps to a requirement/story | ✅ Setup and Foundation serve all stories; other tasks marked with `[USn]` or with the requirement |
| Spec, plan and tasks consistent (terms, scope) | ✅ after the decision on finding A9 |
| No `[NEEDS CLARIFICATION]` remaining | ✅ |
| Compliance with the constitution | ✅ no violations |

### Findings

| # | Severity | Finding | Resolution |
|---|---|---|---|
| A1 | High | RF-024 (vendor without access) had no task or test | Included in T012 (realm without extra administrators or clients) and T055 |
| A2 | High | No check that **code** failures count toward lockout (RF-003); depends on the extension | Item (5) in T008; T012 tests lockout by password and by code |
| A3 | Medium | RNF-004: login, failure and lockout metrics and the e-mail send failure alert (spec edge case) were missing | Included in T033 and T038; the send failure alert was reclassified in A14 |
| A4 | Medium | RF-006: listing and ending one's own sessions had no test | Included in T032 |
| A5 | Medium | RF-009 and edge case: removal from an organization while the person is logged in had no test | Included in T060 |
| A6 | Medium | RF-010: invitation and link validity was not configurable from the security screen | Included in T048; the `PUT /security-settings` contract now covers these periods |
| A7 | Medium | Principle VIII: the plan called for comparing the OpenAPI with the contract, but there was no task | New T078 |
| A8 | Low | CS-001 to CS-003 measure real people's time and had no verification; RNF-007 did not measure e-mail arrival | New T079 (user validation); T075 expanded. Trivy now fails on high or critical vulnerabilities (T073, Principle X) |
| A9 | Medium | **RF-015** (costs of one's own agents only) is a spec requirement, but the plan delivers only the permission and defers the filter to the Cost Dashboard feature, because "agent owner" does not exist yet | **Decided on 2026-10-02 (Fulvio Jorge da Silva):** RF-015 completed in the Cost Dashboard feature; recorded in the spec |
| A10 | Low | US2, scenario 3 (seeing the activation in the Audit Trail) depends on the audit screen, which belongs to US6 (P2) | Accepted: until US6, the check is done via the API in T042 |
| A11 | Low | The `audit.tamper_attempt` event depends on observability log collection, which does not exist yet | Accepted: the attempt is already in the PostgreSQL log (US6, scenario 3); the automatic alert comes with observability |
| A12 | Low | Data of disabled users has no retention period (RNF-002) | Accepted: kept until a right-to-be-forgotten request, to preserve the audit trail; review with the DPO together with the plan's 12-month retention |
| A13 | Process | This branch starts from `docs/constitution-security`; stack §3.16 cites Playwright from §3.1, which is in the `docs/stack-playwright` branch | Merge order: `docs/constitution-security` → `docs/stack-playwright` → `001-identity-access` |
| A14 | Medium | T008: the e-mail code extension does not emit send and resend events, nor send failure events | **Decided on 2026-10-02 (Fulvio Jorge da Silva):** send and resend are removed from RF-021 (spec updated; `auth.code_sent` removed from the catalog). The send failure alert comes from the Keycloak error log, collected by observability (same situation as A11) |
| A16 | **Critical** | Revision 2026-10-03: the code delivered in US1–US4 gives the installation Administrator an implicit Administrator role in every organization and bypasses RLS (`has_installation_scope()`), which violates RF-016 and RF-028 of the revised spec | Phase 7 (T080–T090) before US5; the checkpoint requires `403` for the Super Administrator on every organization route |
| A17 | Medium | CS-008 (organization invitation in under 1 min; activation in under 5 min) measures real people's time | Included in the user validation script (T079) |
| A18 | Medium | RF-029 (billing for all organizations) only creates the permission, because the screens belong to the Billing feature | Same solution as A9, already recorded in the spec (Out of scope and RF-029) |
| A20 | High | ASVS checklist (T076): no re-authentication before sensitive actions (2.1.6, 3.7.1) | **Decided on 2026-10-04 (Fulvio Jorge da Silva):** implement in Phase 1 (RF-031; T093–T097, T099) |
| A21 | Medium | ASVS checklist: no password strength meter (2.1.8); P3 to P5 depend on provisioning | **Decided on 2026-10-04:** meter in this feature (RF-032; T098); P3 to P5 became provisioning requirements (§53.2) |
| A19 | Process | The revision is a significant scope change, which per `docs/sdd/README.md` would be a new feature | **Decided on 2026-10-03 (Fulvio Jorge da Silva):** revision within 001, with new approval of spec, plan and tasks |
| A15 | **Critical** | T012: with brute force enabled, code failures do not count toward lockout and the extension does not limit attempts; the code can be tried without limit (violates RF-002, RF-003 and Principle X) | **Fixed on 2026-10-02** (decision: patch the extension). Cause: Keycloak only counts failures in the `password`, `otp` and recovery code categories. Patch `infra/keycloak/patches/0001-limit-email-code-attempts.patch` applied at build time on top of the pinned v26.5.0 commit: attempts always counted, code invalidated after 5 errors, failure recorded as `otp`. Validated by the extension's 71 tests and the realm tests. Fix proposed upstream in [PR #155](https://github.com/mesutpiskin/keycloak-2fa-email-authenticator/pull/155) (issue #146); remove the patch once it is released |

### Traceability matrix

| Requirement | Tasks |
|---|---|
| RF-001 login + code | T008, T011, T012, T034, T036 |
| RF-002 code rules | T008, T011, T034 |
| RF-003 lockout | T008, T011, T012, T034 |
| RF-004 password recovery | T011, T034 |
| RF-005 password change ends sessions and notifies | T033, T034, T038 |
| RF-006 sessions | T028, T029, T032, T034, T039, T040 |
| RF-007 configurable password policy | T011, T012, T048, T053, T054, T083 |
| RF-008 initial Super Administrator | T042–T045, T083, T089 |
| RF-009 user management | T046, T047, T049–T052, T054, T060, T083, T087 |
| RF-010 single-use invitations and validity | T011, T042, T046, T048 |
| RF-011 deactivation ends sessions | T046, T049, T050, T087 |
| RF-012 last Administrator and last Super Administrator | T046, T050, T060, T083, T087, T091 |
| RF-013 fixed roles | T026, T027 |
| RF-014 matrix enforced on the server | T026, T027, T055–T059 |
| RF-015 costs of one's own agents | T027 (permission) — see A9 |
| RF-016 Administrator only within the organization | T026, T080, T085 |
| RF-017 role takes effect on the next action | T046, T050 |
| RF-018 only the Super Administrator creates organizations | T060, T062, T063, T064 |
| RF-019 multiple organizations and switching | T060, T062–T064 |
| RF-020 isolation between organizations | T018–T020, T061 |
| RF-021 audited events | T022–T024, T033, T038, T066 |
| RF-022 event fields | T022, T066 |
| RF-023 query and export | T065, T068, T070, T088 |
| RF-024 vendor only as Super Administrator | T012, T055, T080, T083 |
| RF-025 list and edit organizations | T060, T063, T064 |
| RF-026 suspend and reactivate | T060, T062, T063, T064, T085 |
| RF-027 organization Administrators | T060, T063, T064 |
| RF-028 Super Administrator outside organizations | T080, T081, T083, T084, T085 |
| RF-029 billing for all organizations | T080 (permission) — see A18 |
| RF-030 Super Administrator management | T091, T092, T064 |
| RF-031 recent re-authentication | T093–T097, T099 |
| RF-032 password strength meter | T098 |
| RNF-001 multi-tenant | T018–T020, T061, T081 |
| RNF-002 LGPD | T015, T016, T067, T069, T072 |
| RNF-003 policy | not applicable (no agents) |
| RNF-004 observability and audit | T014, T033, T038, T066 |
| RNF-005 application security | T005, T007, T009, T028, T032, T035, T071, T073, T076 |
| RNF-006 AI safety | not applicable (no LLM); guaranteed by design |
| RNF-007 performance | T075 |
| CS-001 to CS-003 | T079 |
| CS-004 | T055, T061 |
| CS-005 | T046 |
| CS-006 | T066 |
| CS-007 | T015, T071 |
| CS-008 | T062, T079 |
| CS-009 | T060 |

**Blockers:** none.
