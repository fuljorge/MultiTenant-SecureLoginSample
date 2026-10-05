# Infrastructure

## Local environment

```sh
uv run python infra/compose/init_env.py          # generates infra/compose/.env (local credentials)
docker compose -f infra/compose/docker-compose.yml up -d
```

| Service | Address | Notes |
|---|---|---|
| PostgreSQL 17 | `127.0.0.1:5432` | Databases `cap` (Control Plane) and `keycloak`. Use `127.0.0.1`, not `localhost`: on Windows the driver hangs trying IPv6 |
| Valkey | `127.0.0.1:6379` | BFF sessions |
| OpenBao (dev) | `http://127.0.0.1:8200` | Transit with the `cap-session` key |
| Keycloak | `http://localhost:8080/idp` | Realm `cap`, applied by the `keycloak-config` service |
| Mailpit | `http://localhost:8025` | Every e-mail sent ends up here |

First access: provisioning creates only the initial **Super Administrator**, who invites
organizations through the platform (spec 001, §4.8). Locally:

```sh
cd services/control-plane
CAP_ENV_FILE=../../infra/compose/.env.control-plane uv run cap-admin bootstrap-super-admin \
  --email you@example.com --name "Your Name"   # the activation link arrives in Mailpit
```

## Images (T073)

The build context is the repository root; `.dockerignore` excludes `.env*`,
`DevNotes.MD` and local artifacts.

```sh
docker build -f services/control-plane/Dockerfile -t cap-control-plane .   # API, cap-worker, cap-admin, alembic
docker build -f apps/studio/Dockerfile -t cap-studio .                     # Next.js standalone
docker build -t cap-keycloak infra/keycloak
```

CI builds all three and runs Trivy: it fails on any high or critical vulnerability that has
a fix, unless a mitigation is recorded in `.trivyignore.yaml` (justification, path and
expiry date). The E2E job uses these same images and scans the logs with
`infra/ci/scan_logs_for_secrets.py` (CS-007).

## Keycloak

- `keycloak/Dockerfile`: image pinned by digest; e-mail code extension built from a pinned
  commit with the patch for finding A15; breached-password list with checksum.
  Details and provenance in `keycloak/providers.lock`.
- `keycloak/realm/cap-realm.yaml`: realm configuration (keycloak-config-cli).
  keycloak-config-cli variable substitution applies even inside comments.
- `keycloak/themes/cap/`: login screens and e-mails in Brazilian Portuguese with the brand
  identity.

## Alert on attempts to modify the Audit Trail

`audit.audit_event` accepts inserts only (specs/001-identity-access, data-model.md). Any
`UPDATE`, `DELETE` or `TRUNCATE` is rejected:

- for the application role (`cap_app`), due to missing privilege: `permission denied for table
  audit_event`;
- for any role, including the owner, by the `audit_event_no_change` trigger:
  `audit.audit_event é append-only: <operação> recusado` (the message is in Portuguese:
  "audit.audit_event is append-only: <operation> rejected").

PostgreSQL logs both errors and the statement in the server log (default configuration:
`log_min_messages = warning` and `log_min_error_statement = error`). The deployment's
observability stack must collect this log and raise an alert, plus the
`audit.tamper_attempt` event, whenever it finds one of the messages above with the
`audit_event` table. Until that collection exists, the attempt stays in the `postgres`
container log:

```sh
docker compose -f infra/compose/docker-compose.yml logs postgres | grep -E "append-only|permission denied for table audit_event"
```

## Deployment notes (production)

- **Source IP in Keycloak events:** behind a proxy/ingress, set
  `KC_PROXY_HEADERS=xforwarded` (or `forwarded`) and trust only the deployment's own proxy.
  Without it, the Audit Trail records the proxy's IP, not the user's (locally you will see
  the Docker gateway, e.g. `172.18.0.1`).
- **Event import:** the `cap-worker` process must always be running. Observability must
  alert on the log message `Importação de eventos do Keycloak parada` ("Keycloak event
  import stalled": cursor has not advanced for more than 5 minutes; events are kept for
  7 days in Keycloak).
