# Contract: audit event catalog (identity and access)

Covers the RF-021 list. Fields of each record: see
[data-model.md](../data-model.md#audit_event-append-only-39). No event carries a password,
code, token or link in `details`. Events for Super Administrator actions record
`installation_scope = true` and, when they concern an organization, its
`organization_id` (the organization's Administrator sees them too).

| `event_type` | Source | When | `details` (examples) |
|---|---|---|---|
| `auth.login` | Keycloak `LOGIN` | Full login (password + code) | initial `organization_id` |
| `auth.login_failed` | Keycloak `LOGIN_ERROR` | Wrong password or code | `reason`: `invalid_credentials`, `invalid_code`, `expired_code` |
| `auth.locked` | Keycloak (brute force) | Temporary lockout | `until` |
| `auth.logout` | Control Plane / Keycloak `LOGOUT` | Logout, inactivity, expiry | `reason`: `user`, `idle`, `max_age`, `revoked` |
| `auth.session_revoked` | Control Plane | Session ended by someone else or by the user themselves | `revoked_by` |
| `auth.password_changed` | Keycloak `UPDATE_PASSWORD` | Voluntary change | — |
| `auth.password_reset_requested` | Keycloak `SEND_RESET_PASSWORD` | Recovery request | — |
| `auth.password_reset` | Keycloak `RESET_PASSWORD` | Password reset via the link | — |
| `user.activated` | Control Plane | First login after invitation or welcome e-mail | `via`: `invitation`, `organization_invitation`, `bootstrap` |
| `user.invited` | Control Plane | Invitation created | `profile`, `organization_id` |
| `user.invitation_revoked` | Control Plane | Invitation revoked | — |
| `user.profile_changed` | Control Plane | Role changed in the organization | `from`, `to` |
| `user.membership_added` / `user.membership_removed` | Control Plane | Added to or removed from an organization | `organization_id`, `profile` |
| `user.email_change_requested` / `user.email_changed` | Control Plane | E-mail change | without the e-mails in clear text |
| `user.disabled` / `user.enabled` | Control Plane | Account deactivation and reactivation | — |
| `user.membership_disabled` / `user.membership_enabled` | Control Plane | Deactivation and reactivation of the organization membership (including an Administrator's, by the Super Administrator) | `organization_id`, `profile` |
| `user.anonymized` | `cap-admin` CLI | Right-to-be-forgotten request (LGPD); `actor_kind = support` | ticket number |
| `org.created` / `org.renamed` | Control Plane | Organization invitation (created as `pending`) or rename | `name` |
| `org.activated` | Control Plane | First Administrator activated access | — |
| `org.suspended` / `org.reactivated` | Control Plane | Suspension and reactivation by the Super Administrator | `sessions_revoked` |
| `org.invitation_resent` / `org.cancelled` | Control Plane | Invitation resent and pending organization cancelled | — |
| `org.switched` | Control Plane | Active organization switched | `from`, `to` |
| `super_admin.invited` / `super_admin.disabled` / `super_admin.enabled` | Control Plane | Super Administrator management (RF-030) | — |
| `super_admin.converted` | Migration 0004 | Installation administrator converted into Super Administrator; memberships marked `removed` | `memberships_removed` |
| `security.settings_changed` | Control Plane | Security settings changed | changed fields (no sensitive values) |
| `access.denied` | Control Plane | Action without permission (target: the route) or on a person from another organization (target: the person; the response is `404`, US5 scenario 8) | `permission` and `method`, or `reason: other_organization` |
| `audit.exported` | Control Plane | History export | filter used |
| `audit.tamper_attempt` | Alert on the PostgreSQL log | Attempt to change or delete an event (rejected by the trigger) | `operation`, database role |
| `audit.origin_purged` | Control Plane | Purge of old IP and browser data | time range |
| `support.activation_reissued` | `cap-admin` CLI | Link reissued by support | ticket number |
