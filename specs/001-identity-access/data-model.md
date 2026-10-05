# Data model: 001-identity-access

Control Plane database (PostgreSQL 17). Keycloak keeps its own database (credentials,
login sessions and events), which the Control Plane does not access directly: every
interaction goes through the Admin REST API.

## Who stores what

| Data | Source of truth | Notes |
|---|---|---|
| Password (Argon2 hash) | Keycloak | Never passes through the Control Plane |
| Second-factor code | Keycloak (authentication session, in memory) | See research R1 |
| Attempt lockout | Keycloak (brute force detection) | Read via the Admin API to display the "locked" status |
| User name, e-mail, status | Control Plane, mirrored in Keycloak | The Control Plane is in charge; Keycloak receives |
| Organizations, memberships, roles, Super Administrators | Control Plane | Basis for authorization (research R2) |
| Pending invitations and e-mail changes | Control Plane | Tokens stored only as hashes |
| BFF sessions | Valkey | See the "Sessions" section |
| Audit Trail | Control Plane (`audit` schema) | Includes events imported from Keycloak |

## `identity` schema

### `organization`

| Field | Type | Rules |
|---|---|---|
| `id` | uuid | PK |
| `name` | text | required, unique in the installation |
| `slug` | text | unique, kebab-case |
| `status` | enum `pending`, `active`, `suspended`, `cancelled` | `pending` until the first Administrator activates access (RF-018) |
| `status_changed_at`, `status_changed_by` | timestamptz, uuid | last status change |
| `version` | integer | optimistic lock |
| `created_at`, `created_by` | timestamptz, uuid | `created_by` is always a Super Administrator |

There is no default organization: the `is_default` column is dropped in migration 0004.

### `user_account`

| Field | Type | Rules |
|---|---|---|
| `id` | uuid | PK; same as the user id in Keycloak |
| `email` | citext | unique in the installation (the person's identifier) |
| `name` | text | |
| `status` | enum `invited`, `active`, `disabled` | `blocked` is derived from Keycloak, not persisted |
| `last_login_at` | timestamptz | updated from login events |
| `anonymized_at` | timestamptz | set on a right-to-be-forgotten request (LGPD) |
| `version` | integer | optimistic lock against concurrent edits |
| `created_at`, `updated_at` | timestamptz | |

### `super_admin`

People with the **Super Administrator** role (spec §4.8). Before the 2026-10-03 revision,
`installation_admin` (renamed in migration 0004).

| Field | Type | Rules |
|---|---|---|
| `user_id` | uuid | PK, FK `user_account` |
| `granted_at`, `granted_by` | timestamptz, uuid | |

- RF-012: a transaction that removes a row or disables a Super Administrator locks the
  rows (`SELECT … FOR UPDATE OF super_admin, user_account`) and rejects the operation if
  no active one would remain. The UPDATE policy exists only to allow the lock
  (migration 0003).
- RF-028: a *trigger* rejects inserting here anyone with an `active` or `pending`
  membership, and rejects inserting a membership for anyone who is here.

### `membership`

A person's membership in an organization (RF-019).

| Field | Type | Rules |
|---|---|---|
| `id` | uuid | PK |
| `organization_id` | uuid | FK; **RLS** |
| `user_id` | uuid | FK; unique with `organization_id` |
| `profile` | enum `administrator`, `agent_designer`, `business_analyst`, `supervisor`, `developer`, `financial_admin` | RF-013 |
| `status` | enum `pending`, `active`, `disabled`, `removed` | `pending` until the first login after the invitation; `disabled` on per-organization deactivation (plan, section 4.4) |
| `version` | integer | optimistic lock |
| `created_at`, `created_by`, `updated_at` | | |

### `invitation`

| Field | Type | Rules |
|---|---|---|
| `id` | uuid | PK |
| `organization_id` | uuid | FK; **RLS** |
| `email` | citext | |
| `profile` | enum (same as `membership.profile`) | |
| `token_hash` | bytea | SHA-256 of a random 256-bit token; used only for already registered people |
| `expires_at` | timestamptz | default: 72 h |
| `status` | enum `pending`, `accepted`, `expired`, `revoked` | |
| `invited_by`, `created_at`, `accepted_at` | | |

### `email_change_request`

| Field | Type | Rules |
|---|---|---|
| `id` | uuid | PK |
| `user_id` | uuid | FK |
| `new_email` | citext | |
| `token_hash` | bytea | SHA-256 of a random 256-bit token |
| `expires_at` | timestamptz | default: 24 h |
| `status` | enum `pending`, `confirmed`, `expired`, `revoked` | |
| `requested_by`, `created_at`, `confirmed_at` | | |

### RLS (Principle IV)

- Each transaction sets `app.user_id`, `app.organization_id` (active organization) and
  `app.is_super_admin`; the `identity.is_super_admin()` function is true only if the
  person is also in `super_admin`.
- No role bypasses RLS. The Super Administrator policies are specific:

| Table | Member of the active organization | Super Administrator |
|---|---|---|
| `organization` | their own organizations | all (read, create, update) |
| `membership` | those of the active organization and their own | only `profile = 'administrator'` |
| `invitation` | those of the active organization | only `profile = 'administrator'` |
| `user_account` | the person themselves and anyone with a membership in the active organization | the person themselves, anyone with an Administrator membership and the Super Administrators |
| `super_admin` | only their own row | all |
| `email_change_request` | as before | none |

- The application's database role does not own the tables and does not have `BYPASSRLS`.

## `audit` schema

### `audit_event` (append-only, §39)

| Field | Type | Rules |
|---|---|---|
| `seq` | bigint | PK, sequential; reserved by the writer with `nextval` before the INSERT (an `INSERT … RETURNING` would require the actor to be able to read the event under the read policies) |
| `occurred_at` | timestamptz | event time at the source |
| `recorded_at` | timestamptz | time of recording |
| `organization_id` | nullable uuid | null for installation events (e.g. login before choosing an organization) |
| `installation_scope` | boolean | true for installation management events (Super Administrator actions), including those with an `organization_id`; part of the hash |
| `actor_user_id` | nullable uuid | who did it |
| `actor_kind` | enum `user`, `system`, `support` | `support` = vendor action via the operations tool (e.g. link reissue) |
| `event_type` | text | catalog in [contracts/audit-events.md](contracts/audit-events.md) |
| `target_type`, `target_id` | text, text | target of the action |
| `result` | enum `success`, `failure`, `denied` | |
| `details` | jsonb | **never** contains a password, code, token, link, IP or e-mail |
| `source` | enum `control_plane`, `keycloak` | |
| `source_event_id` | text | event id in Keycloak; unique with `source`, prevents duplicates on import |
| `prev_hash`, `hash` | bytea | `hash = SHA-256(prev_hash ‖ canonical JSON of the record)` |

- The application role has only `INSERT` and `SELECT`; a *trigger* also rejects
  `UPDATE`, `DELETE` and `TRUNCATE` for any role. The rejection rolls back its own
  transaction, so the attempt is recorded in the **PostgreSQL log**, collected by the
  observability stack, which raises an alert and the `audit.tamper_attempt` event in a
  separate transaction (US6, scenario 3).
- Writes are serialized by locking the single row of `audit.chain_head` (`FOR UPDATE`),
  which stores the position and hash of the last record. The head is outside RLS (it has
  no customer data), so the writer gets the previous hash even when the last record
  belongs to another organization.
- Integrity check: a routine that recomputes the chain and alerts on mismatch.
- Right-to-be-forgotten request: the event is not changed; personal data lives in
  `user_account`, which is anonymized. `actor_user_id` keeps pointing to a record with no
  name or e-mail.

### Who reads the Audit Trail (US6, scenario 2)

| Who | Sees |
|---|---|
| Administrator | events of the active organization (including Super Administrator actions on it) and events with no organization, outside installation management, performed by people with a non-removed membership in the organization (logins and failures coming from Keycloak; migration 0005) |
| Super Administrator | events with `installation_scope` and events performed by Super Administrators (migration 0004) |

The origin (`audit_event_origin`) follows the event's visibility.

### `audit_event_origin`

Connection origin of each event ("from where", RF-022). It is kept **outside the hash
chain** because it is personal data with limited retention (LGPD).

| Field | Type | Rules |
|---|---|---|
| `seq` | bigint | PK, FK `audit_event` |
| `source_ip` | inet | |
| `user_agent` | text | |

- A daily purge in `cap-worker` removes rows older than 12 months
  (`audit_origin_retention_days`, default 365) and records an `audit.origin_purged` event
  with the purged range. The `audit_event` chain remains verifiable.

### `chain_head`

Single row with the head of the chain (`last_seq`, `last_hash`). Starts with the genesis
hash (32 zero bytes). The application role can only read and update it.

### `keycloak_event_cursor`

Single row with the timestamp of the last imported event (`last_time`, in milliseconds)
and the ids already imported at that timestamp (`last_ids`), because several events can
share the same time. Used by the research R4 worker.

## Sessions (Valkey)

| Key | Content | TTL |
|---|---|---|
| `cap:sess:{sid}` | `user_id`, `keycloak_sid`, `active_organization_id`, `csrf_token_hash`, **encrypted** Keycloak tokens, `created_at`, `last_seen_at` | renewed on every request up to 30 min of inactivity; never exceeds 12 h since `created_at` |
| `cap:user-sess:{user_id}` | set of the user's `sid`s | used to end all of a user's sessions |

- `sid`: 256 random bits; the cookie carries the `sid`, the Valkey key uses its SHA-256.
- Sessions belong to the person, not to an organization; the active organization is a
  session attribute and is revalidated against `membership` on every request.

## State transitions

```text
organization.status:   pending ──(1st Administrator active)──▶ active ◀──(reactivate)── suspended
                          │                                    └────(suspend)────▶ suspended
                          └──(cancel)──▶ cancelled
user_account.status:   invited ──(1st login)──▶ active ◀──(reactivate)── disabled
                                                   └─────(disable)─────▶ disabled
membership.status:     pending ──(1st login / acceptance)──▶ active ◀──(reactivate)── disabled
                                                               ├──(disable)──▶ disabled
                                                               └──(remove)───▶ removed
invitation.status:     pending ──▶ accepted | expired | revoked
email_change_request:  pending ──▶ confirmed | expired | revoked
```
