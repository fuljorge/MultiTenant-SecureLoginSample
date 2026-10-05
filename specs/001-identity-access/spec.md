# Spec: User Identity, Authentication and Access Control

- **ID:** 001-identity-access
- **Status:** Approved <!-- Draft | Approved | Implemented | Discarded -->
- **Phase (§48):** Phase 1 — Agent Builder (prerequisite for every feature in the phase)
- **References:** §4, §4.8, §29.2, §30, §39, §43, §44, §48, §51, §52, §53.2, §54, §56, §57.1 of
  the internal product reference (not included in this sample)
- **Roles involved (§4):** Super Administrator (vendor), Administrator, Agent Designer,
  Business Analyst, Supervisor, Developer / Integration Engineer, Financial
  Administrator
- **Created on:** 2026-10-02
- **Approved by / on:** Fulvio Jorge da Silva / 2026-10-04 (amendment: recent
  re-authentication and password strength meter, RF-031 and RF-032; previous versions
  approved on 2026-10-02 and 2026-10-03)

## 1. Context and problem

The platform is delivered in a hybrid model (§51): a **shared installation** serves
several customers, and customers that require physical isolation get a **dedicated
installation**. In both cases, each customer uses one or more **organizations**
(tenants), with isolated users and data (§44).

Organizations are created and managed by the **Super Administrator** (§4.8), a vendor
role. They invite the person who will be the **Administrator** of the new organization
and, from then on, that Administrator grants access to the people on their team, each
with the responsibilities of their role (§4). The Super Administrator manages
organizations, their Administrators and billing, but neither sees nor creates anything
inside them. The product requires RBAC, encryption and auditing (§43).

Without identity and access control, no other Phase 1 feature (creating agents, testing,
publishing, viewing costs) can be offered securely. This feature is therefore the
foundation for the others.

In this phase, access is **only via direct login to the platform** (e-mail and password)
with a **second factor via a code sent by e-mail**. Login through the corporate identity
provider (SSO) and vendor emergency access are left to Phase 2 (§48).

## 2. Goals and non-goals

**Goals**

- Allow only authorized people to access the platform, with direct login and a second
  factor via an e-mail code.
- Allow the vendor's Super Administrator to create, monitor, suspend and reactivate
  organizations and manage their Administrators, without access to their content.
- Allow each organization's Administrator to manage users and their roles without
  depending on the vendor.
- Ensure each role accesses only the functions and data that belong to it (§4, §57.1).
- Isolate users and data between organizations (tenants) of the same installation (§44),
  including between different customers on the shared installation, while allowing a
  person to work in more than one organization.
- Record every access event in the Audit Trail (§39).

**Out of scope**

- **Login via the corporate identity provider (SSO)** and corporate group mapping:
  Phase 2 (§48).
- **Vendor emergency access** to the customer's installation: Phase 2, with the Provider
  Console (§4.7, §48, §54). Rules already decided for that feature: access restricted to
  configuration and operations, no conversations or personal data, and always with prior
  approval from the customer's Administrator.
- Other second factors (authenticator app, security key, SMS): future phase.
- Custom roles and per-environment permissions (§30): future phase. §48 places multiple
  environments in Phase 2.
- System credentials for the Conversation API (API Key and OAuth Client Credentials,
  §29.1): separate feature.
- Expiring Demo Chat demonstration links (§29.2): part of the Demo Chat feature, reusing
  this one.
- Identity of the **end customer** who talks to the agents.
- Authorization of agent actions (tools, workflows), which is the Policy Engine's job
  (§18).
- Purchasing, payment and provisioning (§52, §53), including purchasing an organization on
  the shared installation through the website: this feature starts when the initial
  Super Administrator receives access.
- Billing screens and rules (invoices, plans, charging): Billing feature (§56). This
  feature creates the Super Administrator's billing permissions (RF-029).
- Permanent deletion of an organization, with data export and erasure (LGPD): future
  phase. This feature has suspension and reactivation (RF-026).

## 3. User stories and acceptance scenarios

### US1 — Login with an e-mail second factor (P1)

As a platform user, I want to sign in with e-mail, password and a code sent to my e-mail
so I can securely access the functions of my role.

**Why P1:** without login nothing else can be used.

**Independent test:** an already registered user signs in with password and code,
navigates, signs out and cannot come back without a new login.

**Acceptance scenarios**
1. **Given** an active user, **when** they enter the correct e-mail and password,
   **then** they receive a one-time code at the registered e-mail and the platform asks
   for that code.
2. **Given** a received code within its validity, **when** the user enters it, **then**
   they access the platform in one of the organizations they belong to, with the role
   they have there.
3. **Given** an expired, already used or wrong code, **when** it is entered, **then**
   access is denied; after the attempt limit, the code is invalidated and the user must
   restart the login.
4. **Given** a user waiting for the code, **when** they request a resend, **then** they
   receive a new code, the previous one stops working, and resends respect a rate limit.
5. **Given** a user, **when** they enter a wrong e-mail or password, **then** they get a
   generic message that does not reveal whether the user exists, and no code is sent.
6. **Given** a user with several consecutive failed login attempts, **when** they reach
   the limit, **then** new attempts are temporarily blocked and the event is recorded.
7. **Given** a logged-in user, **when** they sign out or stay inactive beyond the time
   limit, **then** the session ends and access requires a new full login.
8. **Given** a user who forgot their password, **when** they request recovery, **then**
   they receive a single-use, short-lived link at the registered e-mail.
9. **Given** that the user changed their password (via recovery or voluntarily), **when**
   the change completes, **then** all their open sessions are ended and they receive an
   e-mail about the change, advising them to contact the Administrator if they do not
   recognize it.
10. **Given** a logged-in user whose last full login (password and code) was more than
    15 minutes ago, **when** they attempt a sensitive action (RF-031), **then** they must
    enter password and code again before the action happens; after that, they complete
    the action without losing what they were doing.
11. **Given** a logged-in user, **when** they ask to change their password, **then** they
    must enter password and code again, regardless of the time since the last login.
12. **Given** a user setting or changing their password, **when** they type, **then**
    they see a password strength indicator, which guides without replacing the policy
    (RF-032).

### US2 — First access of the initial Super Administrator (P1)

As the vendor's Super Administrator, I want to activate my access from the welcome
e-mail so I can start creating the customers' organizations.

**Why P1:** it is the entry point of every installation, shared or dedicated
(§51, §53.2).

**Independent test:** on a freshly provisioned installation, the initial Super
Administrator activates the account and reaches the organizations screen.

**Acceptance scenarios**
1. **Given** a freshly provisioned installation, **when** the initial Super Administrator
   opens the link in the welcome e-mail, **then** they set their password and access the
   platform as **Super Administrator**. Ownership of the e-mail is proven by the link
   itself.
2. **Given** an activation link that has already been used or has expired, **when** it is
   opened, **then** access is denied and the person is told to ask the vendor's
   operations team for a new link.
3. **Given** that the initial Super Administrator activated the account, **when** they
   look at the installation's Audit Trail, **then** they see the activation record.

### US3 — User management by the organization Administrator (P1)

As an organization Administrator, I want to invite, change, disable and re-enable users
to keep my team's access up to date.

**Why P1:** without this the platform has only one user.

**Independent test:** the Administrator invites a user, who activates the account; then
changes the role and disables the user, and access changes accordingly.

**Acceptance scenarios**
1. **Given** an Administrator, **when** they invite a person by entering name, e-mail,
   organization and role, **then** the person receives a single-use invitation with an
   expiry date, through which they set their password.
2. **Given** an active user, **when** the Administrator changes their role, **then** the
   new permissions apply from the user's next action, without a new login.
3. **Given** an active, logged-in user, **when** the Administrator disables them,
   **then** all their sessions are ended and no new access is allowed.
4. **Given** a disabled user, **when** the Administrator re-enables them, **then** they
   regain access with the same roles, after a new full login.
5. **Given** that an active organization has only one active Administrator, **when**
   someone tries to disable them or remove their Administrator role, **then** the
   operation is rejected.
6. **Given** a user who lost access to their own e-mail, **when** the Administrator
   changes the registered e-mail, **then** the new e-mail must be confirmed by the user
   before it takes effect, existing sessions are ended and the old e-mail is notified of
   the change.
7. **Given** an Administrator, **when** they look at the user list, **then** they see
   each user's name, e-mail, organizations, roles, status and last access, and can filter
   by these fields.

### US4 — Role-based access (P1)

As the person responsible for security, I want each role to see and do only what belongs
to it, to reduce mistakes and abuse.

**Why P1:** it guarantees that the other features respect the roles (§4).

**Independent test:** users of each role try to access functions outside their role and
are blocked, with a record in the Audit Trail.

**Acceptance scenarios**
1. **Given** a user of any role, **when** they access the platform, **then** they see
   only the menus, screens and actions allowed to their role in the active organization
   (matrix in section 5.1).
2. **Given** a user, **when** they try to perform a disallowed action directly (without
   the UI), **then** the action is denied and the event is recorded.
3. **Given** an Agent Designer or Business Analyst, **when** they look at costs, **then**
   they see only the costs of the agents under their responsibility (§57.1).
4. **Given** a user who is not an Agent Designer, **when** they try to publish an agent,
   **then** the action is denied.
5. **Given** an organization Administrator, **when** they try to create an organization
   or change the installation's security policy, **then** the action is denied and the
   event is recorded.

### US5 — Organization management by the Super Administrator (P1)

As the vendor's Super Administrator, I want to create organizations by invitation,
monitor, suspend and reactivate them and manage their Administrators, without access to
what exists inside them, so I can bring customers onto the platform and keep them
isolated from one another (§4.8, §44).

**Why P1:** on the shared installation, it is the only way for a customer to start using
the platform; on a dedicated one, it is how the customer gets their first Administrator.

**Independent test:** the Super Administrator invites a new organization; the invitee
activates the account and starts administering it; the Super Administrator sees the
active organization with its Administrator, cannot see its other users or its data, and
on suspending it all users lose access.

**Acceptance scenarios**
1. **Given** a Super Administrator, **when** they invite a new organization by entering
   the organization name and the owner's name and e-mail, **then** the organization comes
   into existence as **pending**, isolated and with no data, and the owner receives a
   single-use invitation with an expiry date.
2. **Given** a valid organization invitation, **when** the owner accepts it and sets the
   password, **then** they become that organization's **Administrator**, and the
   organization becomes **active**.
3. **Given** any user who is not a Super Administrator, including an organization
   Administrator, **when** they try to create an organization, **then** the action is
   denied and the event is recorded.
4. **Given** a Super Administrator, **when** they look at the organizations, **then**
   they see every organization in the installation, with name, status, Administrators,
   creation date and billing status, and can filter by these fields.
5. **Given** an organization, **when** the Super Administrator invites a new
   Administrator, or disables and re-enables an existing Administrator, **then** the
   change applies as in US3, and the organization is never left without an active
   Administrator (RF-012).
6. **Given** an active organization with logged-in users, **when** the Super
   Administrator suspends it, **then** the sessions in that organization are ended,
   nobody can access the organization any more and the data is preserved; **when** they
   reactivate it, users regain access with the same roles, after a new full login.
7. **Given** a Super Administrator, **when** they try to see users who are not
   Administrators, or create, change or see any object of an organization (agents,
   integrations, conversations, settings), by any path, **then** the action is denied and
   the event is recorded.
8. **Given** a user of organization A, **when** they try to access any resource of
   organization B, to which they do not belong, **then** access is denied and the event
   is recorded.
9. **Given** a person who belongs to organizations A and B, with different roles in
   each, **when** they switch from organization A to B, **then** they see only B's data,
   with the role they have in B, without having to log in again.
10. **Given** a person with more than one organization, **when** they complete the login,
    **then** they enter the last active organization used and can switch organizations
    at any time.

### US6 — Access auditing (P2)

As an Administrator, I want to look up the history of access events to investigate
incidents and prove compliance.

**Why P2:** events are recorded from P1 on; this story covers querying them.

**Independent test:** after logins, failures and role changes, the Administrator finds
each event by filtering by user, type and period.

**Acceptance scenarios**
1. **Given** recorded access events, **when** the Administrator filters by user, event
   type and period, **then** they see who, what, when, from where and with what result.
2. **Given** an organization Administrator, **when** they look at the audit, **then**
   they see only their organization's events, including the Super Administrator's actions
   on it. The Super Administrator sees installation management events (organizations,
   Administrators, security policy and Super Administrator access), without the
   organizations' internal events.
3. **Given** an audit record, **when** someone tries to change or delete it, **then** the
   operation is not possible and the attempt is recorded.
4. **Given** the Administrator, **when** they request an export of the filtered history,
   **then** they receive the file, and the export itself is recorded.

## 4. Edge cases

- Invitation sent to an e-mail that already belongs to a user: instead of creating another
  user, the invitation adds the person to the organization, with the given role.
- User with an expired invitation tries to activate the account.
- The e-mail with the code is delayed or never arrives (resend with a limit; no
  alternative path that skips the second factor).
- User requests several codes in a row: only the last one is valid.
- An intercepted code is used after the user has already signed in: the code is
  single-use and has already been consumed.
- User loses access to their own e-mail: only the Administrator can change the registered
  e-mail (US3, scenario 6).
- An organization's only Administrator loses access to their own e-mail: the Super
  Administrator invites a new Administrator to the organization and, after activation,
  disables the previous one.
- A person starts a sensitive action with their last login more than 15 minutes ago:
  they authenticate again and return to the same screen; if the new authentication fails,
  nothing changes.
- The only Super Administrator loses access to their own e-mail: the vendor's operations
  team reissues the activation link to a new e-mail, after identity verification, with a
  record in the Audit Trail.
- An Administrator tries to downgrade their own role while being the organization's only
  Administrator.
- Organization invitation expires without being accepted: the organization stays
  pending; the Super Administrator can resend the invitation or cancel it (a pending
  organization has no data).
- Organization invitation to the e-mail of an already registered person: the person
  becomes Administrator of the new organization with their existing account, without
  creating another.
- Organization or user invitation to a Super Administrator's e-mail: it is rejected,
  because the Super Administrator cannot have organization memberships.
- Suspended organization with a person who also belongs to another active organization:
  the person loses access only to the suspended one and keeps the other.
- Suspension of an organization with a long-running operation in progress in it.
- User removed from the active organization while logged in: they lose access to it on
  the next action and, if they have no other organization, the session is ended.
- Two administrators change the same user at the same time.
- Role change during a long-running operation in progress.
- Password recovery requested for a non-existent e-mail: the response must not reveal
  whether the e-mail exists.
- E-mail sending service unavailable: the login does not complete without the second
  factor, and the failure is recorded and alerted.

## 5. Requirements

### Functional

**Authentication**

- **RF-001:** The system MUST authenticate users by direct login (e-mail and password)
  followed by a mandatory second factor: a one-time code sent to the registered e-mail.
  *(US1, §43)*
- **RF-002:** The second-factor code MUST be unpredictable, single-use, valid for a few
  minutes, invalidated after a limited number of attempts and replaced on every resend;
  resends MUST be rate-limited. *(US1)*
- **RF-003:** The system MUST temporarily lock login after consecutive failed attempts
  (password or code) and record the event. *(US1)*
- **RF-004:** The system MUST offer password recovery via a single-use, short-lived link
  sent to the registered e-mail. *(US1)*
- **RF-005:** Every password change MUST end the user's existing sessions and send them a
  notice by e-mail. *(US1)*
- **RF-006:** The system MUST end sessions on logout, inactivity and maximum lifetime, and
  let the user see and end their active sessions. *(US1)*
- **RF-007:** The system MUST enforce a password policy configurable by the Super
  Administrator, with a secure default and rejection of known breached passwords. *(US1)*
- **RF-031:** Sensitive actions MUST require the last full login (password and code) to
  have happened at most 15 minutes ago; otherwise, the person authenticates again and the
  action proceeds. Sensitive actions are: disabling, re-enabling or removing a person from
  an organization; changing another person's e-mail; ending another person's sessions;
  suspending, reactivating or cancelling an organization; inviting, disabling or
  re-enabling an organization Administrator or a Super Administrator; changing the
  security settings; and exporting the Audit Trail. Changing one's own password MUST
  always require a new authentication. *(US1, US3, US5, US6; OWASP ASVS 2.1.6 and 3.7.1)*
- **RF-032:** The set and change password screens MUST show a password strength indicator
  while the person types; the indicator guides and does not replace the RF-007 policy.
  *(US1, US2; OWASP ASVS 2.1.8)*

**User lifecycle**

- **RF-008:** The system MUST allow the initial Super Administrator to activate their
  account via the welcome link generated at provisioning. *(US2, §53.2)*
- **RF-009:** The system MUST allow the organization Administrator to invite, change
  role, add to and remove from organizations, change e-mail (with confirmation by the new
  e-mail and a notice to the old one), disable, re-enable and list users, within their
  scope (RF-016). *(US3, US5)*
- **RF-010:** Invitations and activation links MUST be single-use, with configurable
  validity. *(US2, US3)*
- **RF-011:** Disabling a user MUST end all their sessions immediately. *(US3)*
- **RF-012:** The system MUST NOT allow the installation to be left without any active
  Super Administrator, nor an active organization to be left without any active
  Administrator. *(US3, US5)*

**Authorization**

- **RF-013:** The system MUST offer the fixed organization roles of §4.1 to §4.6
  (Administrator, Agent Designer, Business Analyst, Supervisor, Developer / Integration
  Engineer and Financial Administrator) and the Super Administrator installation role
  (§4.8), with no custom roles in this phase. *(US4, US5, §4)*
- **RF-014:** The system MUST enforce the role matrix of section 5.1 on every action, in
  the UI and on the server, considering the user's role in the active organization;
  nothing is allowed by default. *(US4, §4)*
- **RF-015:** The system MUST restrict the cost view of Agent Designers and Business
  Analysts to the agents under their responsibility. *(US4, §57.1)* This feature creates
  the permission; the owner filter is implemented and verified in the Cost Dashboard
  feature, which depends on the agent owner concept.
- **RF-016:** The Administrator role MUST apply only in the organization where the person
  holds it. The installation scope (organizations, their Administrators, the
  installation's security policy and billing for all organizations) belongs only to the
  Super Administrator. *(US4, US5, §4.1, §4.8)*
- **RF-017:** Role changes MUST take effect from the user's next action. *(US3)*

**Organizations (tenants)**

- **RF-018:** Only the Super Administrator MUST be able to create organizations, always by
  inviting the person who will be the Administrator; the organization stays pending until
  the invitation is accepted. *(US5, §4.8, §44)*
- **RF-019:** A person MUST be able to belong to one or more organizations, with one role
  in each, and switch the active organization without a new login. *(US5)*
- **RF-020:** An organization's users and data MUST NOT be accessible to anyone who does
  not belong to it, not even by a direct attempt. *(US5, §44)*

**Auditing**

- **RF-021:** The system MUST record in the Audit Trail: login, logout, password and code
  failures, lockouts, activation, invitation, role, organization and e-mail changes,
  active organization switch, deactivation, reactivation, password change and recovery,
  organization invitation, creation, editing, suspension and reactivation, security
  policy changes and denied access. *(US6, §39)*
- **RF-022:** Each record MUST contain who, what, when, from where (connection origin),
  organization and result, without passwords, codes or links. *(US6, §39)*
- **RF-023:** The system MUST allow querying, filtering and exporting access records,
  respecting the scope of whoever is querying (US6, scenario 2) and recording the export
  itself. *(US6)*

**Vendor**

- **RF-024:** The vendor MUST NOT have access to the organizations' functions or data
  through the platform, beyond what the Super Administrator role allows (RF-025 to
  RF-030). Vendor emergency access is left to Phase 2. *(§4.7, §4.8)*

**Super Administrator**

- **RF-025:** The system MUST allow the Super Administrator to list and filter all of the
  installation's organizations, with name, status (pending, active, suspended),
  Administrators, creation date and billing status, and to edit the organization name.
  *(US5, §4.8)*
- **RF-026:** The system MUST allow the Super Administrator to suspend and reactivate
  organizations. Suspension MUST end the sessions in the organization, prevent any access
  to it and preserve the data. *(US5, §4.8, §53.3)*
- **RF-027:** The system MUST allow the Super Administrator to invite, disable and
  re-enable each organization's Administrators and to resend or cancel organization
  invitations, respecting RF-012. *(US5, §4.8)*
- **RF-028:** The Super Administrator MUST NOT have a membership or role in any
  organization, nor create, change or read objects inside them, nor see users who are not
  Administrators. Every attempt MUST be denied on the server and recorded. *(US5, §4.8)*
- **RF-029:** The system MUST give the Super Administrator permission to view and manage
  billing for all organizations. The billing screens and rules belong to the Billing
  feature (§56). *(§4.8, §56)*
- **RF-030:** The system MUST allow the Super Administrator to invite, disable and
  re-enable other Super Administrators, respecting RF-012. *(US5, §4.8)*

### Non-functional (check against the constitution)

- **RNF-001 Multi-tenant (Principle IV):** users, organization memberships, sessions and
  audit records are isolated per organization; no query returns data from an
  organization the user does not belong to. On the shared installation, this is what
  separates one customer from another. Automated isolation tests are mandatory, including
  organization switching and the Super Administrator (who does not read organization
  data).
- **RNF-002 LGPD (Principle V):** users' personal data (name, e-mail, connection origin)
  have a purpose and a defined retention and do not appear in clear text in technical
  logs. See the assumption on auditing × right to be forgotten.
- **RNF-003 Policy and guardrails (Principle III):** does not apply to agent actions in
  this feature; user authorization follows RF-014.
- **RNF-004 Observability and auditing (Principle VII):** every RF-021 event goes to the
  immutable Audit Trail; login, failure and lockout metrics available for monitoring.
  Failures to send the code e-mail are recorded in the identity provider's error log and
  alerted by observability.
- **RNF-005 Application security (Principle X):**
  - passwords are never stored in a recoverable form nor appear in logs, screens or
    messages;
  - second-factor codes, invitations, activation and recovery links are single-use,
    unpredictable, expire and are never stored in clear text;
  - e-mail sending service credentials live in the secrets vault;
  - sessions resist theft and reuse (they expire, are revocable and are not accessible to
    page scripts);
  - protection against brute force (on password and code), user enumeration and
    cross-site request forgery;
  - verification against OWASP ASVS level 2 in the authentication, session and access
    control chapters.
- **RNF-006 AI safety (Principle XI):** no agent or LLM takes part in user authentication
  or authorization decisions; identity data is never sent to models.
- **RNF-007 Performance/limits:** login steps respond within 2 s at the 95th percentile
  (not counting user typing); the code e-mail arrives within 60 s in 95% of sends;
  organization switch within 2 s; session revocation effective within 60 s.

### 5.1 Role matrix

Derived from §4, §4.8 and §57.1. Organization roles apply to the role the user has in the
active organization. The Super Administrator (Super) acts on the installation, outside
organizations (RF-028).

| Area | Super | Admin | Agent Designer | Business Analyst | Supervisor | Dev / Integr. | Financial Admin |
|---|---|---|---|---|---|---|---|
| Organizations (create, suspend, reactivate) | Manage | — | — | — | — | — | — |
| Installation security policy | Manage | — | — | — | — | — | — |
| Super Administrators | Manage | — | — | — | — | — | — |
| Organization Administrators | Manage | Manage (own org) | — | — | — | — | — |
| Other users and roles | — | Manage | — | — | — | — | — |
| Organization settings | — | Manage | — | — | — | — | — |
| Environments (§30) | — | Manage | View | — | — | View | — |
| AI models (§40) | — | Manage | View | — | — | View | — |
| Corporate connections, APIs, MCP | — | Manage | View | — | — | Manage | — |
| Agents, Goals, Skills, prompts, RAG, workflows | — | View | Manage | View | View | View | — |
| Test Cockpit and Demo Chat | — | Use | Use | Use | Use | Use | — |
| Agent publishing | — | — | Execute | — | — | — | — |
| Conversations and effectiveness analysis | — | View | View | Manage reviews | View | — | — |
| Operational monitoring and handoffs | — | View | View | View | Manage | — | — |
| Costs (§57) | — | Full | Own agents | Own agents | — | — | Full |
| Invoices, plans, budgets | Manage (all) | View | — | — | — | — | Manage |
| Audit Trail | Installation | Organization | — | — | — | — | — |

The **Platform Operator** (§4.7) has no access to the customer's platform in this phase
(RF-024). The vendor acts on organizations only through the Super Administrator role.

## 6. Key entities

- **Organization (tenant):** isolation unit within the installation (company, brand,
  business unit; on the shared installation, also what separates one customer from
  another). It has users and all other platform resources (§44). Status: pending
  (invitation not accepted), active or suspended. Only the Super Administrator creates
  it.
- **User:** a person with access to the platform; has a name, e-mail and status
  (invited, active, disabled, locked). Can belong to one or more organizations.
- **Organization membership:** the association between a user and an organization, with
  the role they have there.
- **Role:** one of the six fixed organization roles of §4.1 to §4.6, always tied to an
  organization.
- **Super Administrator:** the vendor's role on the installation (§4.8), with no
  organization membership.
- **Invitation:** a single-use, time-limited authorization to create a user's access, add
  them to an organization or create an organization with its Administrator.
- **Verification code:** single-use second factor sent by e-mail, with short validity and
  an attempt limit.
- **Session:** a user's authenticated period, with the active organization; it can be
  ended by the user, by inactivity, by expiry or by the Administrator.
- **Audit event:** immutable record of an access event (§39).

## 7. Success criteria

- **CS-001:** The initial Super Administrator activates the account and reaches the
  organizations screen in under 5 minutes after opening the welcome e-mail.
- **CS-002:** An Administrator invites a user in under 1 minute, and the user completes
  activation in under 3 minutes.
- **CS-003:** A registered user completes the login with the e-mail code in under
  1 minute in 95% of attempts.
- **CS-004:** 100% of attempts to access functions outside the role or data of an
  organization the user does not belong to, including by the Super Administrator, are
  denied and recorded, proven by automated tests for each role and matrix area.
- **CS-005:** A disabled user loses all access within 60 seconds.
- **CS-006:** 100% of the events listed in RF-021 appear in the Audit Trail with the
  RF-022 fields.
- **CS-007:** No password, code, single-use link, secret or token appears in logs,
  screens or API responses, proven by automated tests and scanning.
- **CS-008:** The Super Administrator invites an organization in under 1 minute, and the
  owner activates it and reaches the home screen as Administrator in under 5 minutes.
- **CS-009:** A suspended organization has no access at all within 60 seconds.

## 8. Assumptions

- The e-mail code second factor is mandatory for all users, on every login. There is no
  "remember this device" option in this phase.
- On activation (initial Administrator and invitations), the single-use link sent to the
  e-mail itself proves ownership of the e-mail; no additional code is requested at that
  point.
- Initial defaults, adjustable by the Super Administrator: 6-digit code, valid for
  10 minutes, with up to 5 attempts; up to 3 resends every 15 minutes; 30 minutes of
  inactivity; maximum session lifetime of 12 hours; 15-minute lockout after 5 failed
  attempts; invitation valid for 72 hours; recovery link valid for 30 minutes.
- The e-mail is the person's unique identifier within the installation, even when they
  belong to several organizations.
- The installation starts with no organizations; each customer's first organization is
  created by invitation from the Super Administrator. On a dedicated installation, this
  replaces the customer's "initial Administrator User" (§53.2): provisioning creates the
  initial Super Administrator, who invites the first organization.
- The organization switcher does not appear for people with only one organization.
- Super Administrators are managed by other Super Administrators (RF-030); the initial
  one comes from provisioning.
- The Super Administrator's second factor and session rules are the same as other users'
  in this phase.
- Disabled users are not deleted, to preserve the audit trail. On a right-to-be-forgotten
  request (LGPD), the user's personal data is anonymized and the audit records point to an
  anonymous identifier.
- Sending e-mails (welcome, invitations, codes, notices, recovery) uses an e-mail service
  configured at provisioning, with a sender from the installation's domain.
- The Super Administrator sees the name and e-mail of organization Administrators, so they
  can manage them; this is the only personal data from inside organizations they have
  access to.
- The UI is in Brazilian Portuguese and follows the brand identity (constitution,
  Section 2).

## 9. Clarifications

| Date | Question | Answer |
|---|---|---|
| 2026-10-02 | With SSO active, are local accounts still allowed? | SSO moves entirely to Phase 2 (§48 updated). In Phase 1, direct login only (e-mail and password). |
| 2026-10-02 | Which second factor to use? | A one-time code sent to the registered e-mail, mandatory on every login. |
| 2026-10-02 | Password recovery and the code go to the same e-mail; do we accept the risk? | Yes, in Phase 1. Mitigation: every password change ends sessions and sends an e-mail notice (RF-005). |
| 2026-10-02 | Can a person belong to more than one organization? | Yes, with one role in each and organization switching without a new login (RF-019). |
| 2026-10-02 | Is there a group Administrator? | Yes: the Administrator has installation or organization scope (RF-016). *Superseded on 2026-10-03: installation scope moved to the Super Administrator.* |
| 2026-10-02 | Fixed or custom roles? Per-environment permissions? | Fixed roles from §4 in Phase 1. No per-environment permissions (multiple environments are Phase 2). Publishing only by the Agent Designer. |
| 2026-10-02 | Scope and approval of vendor emergency access? | Configuration and operations only, no conversations or personal data, always with the customer's approval. The story leaves this spec and moves to Phase 2 with the Provider Console (§4.7 and §48 updated). |
| 2026-10-02 | RF-015 depends on "agent owner", which does not exist yet. Where to complete it? | This feature creates the permission; the filter is completed in the Cost Dashboard feature (analysis, finding A9). |
| 2026-10-02 | The identity provider does not emit code send and resend events (research R1, T008). How to audit? | Code send and resend are removed from RF-021. Login, code failures and lockout remain audited; resend is limited to one every 5 minutes. Send failures are alerted from the error log, via observability. |
| 2026-10-03 | What is the delivery model? | Hybrid: shared installation (multi-tenant, default) and dedicated as an option (§51 updated). |
| 2026-10-03 | Who manages the organizations? | The vendor's Super Administrator (§4.8), who replaces the installation Administrator. Only they create organizations. They neither see nor create anything inside them and see only the organizations' Administrators. |
| 2026-10-03 | On a dedicated installation, who is the Super Administrator? | Also the vendor. The customer keeps the Administrators of their organizations. |
| 2026-10-03 | How does the organization invitation work? | The Super Administrator enters the organization name and the owner's name and e-mail; the organization is created pending and becomes active when the owner activates the account and becomes its Administrator. Company registration data is left to purchasing (§52). |
| 2026-10-03 | What does the Super Administrator do in billing? | Views and manages billing for all organizations. This feature creates the permission; screens and rules are in the Billing feature (§56). |
| 2026-10-03 | Does the Super Administrator manage the organization lifecycle? | Yes: suspend and reactivate. Permanent deletion comes later. |
| 2026-10-03 | New feature or revision of 001? | Revision of 001 (decision of the responsible person), with new approval of spec, plan and tasks. |
| 2026-10-04 | ASVS checklist (T076), P1: re-authenticate before sensitive actions? | Yes, in Phase 1: full login no older than 15 min for the RF-031 actions; password change always re-authenticates. |
| 2026-10-04 | ASVS checklist, P2: password strength meter? | Yes, on the set and change password screens, advisory only (RF-032). |
| 2026-10-04 | ASVS checklist, P3 to P5 (`master` realm administrator, SMTP TLS, production secrets)? | Requirements of the provisioning feature (§53.2 updated); in this feature, documented dependencies. |

## 10. Impact of the 2026-10-03 revision on what has already been implemented

US1 to US4 were implemented with the previous version of this spec. The revision changes:

- the **installation Administrator** becomes the **Super Administrator**: they are no
  longer an implicit Administrator in every organization and lose access to their users
  and data (RF-016, RF-028);
- the initial Administrator activation (US2) now creates the initial Super
  Administrator, and the "default organization" no longer exists;
- the security settings (RF-007) and the "never without an administrator" rule (RF-012)
  move to the Super Administrator and to each organization;
- the role matrix (section 5.1) and the test that verifies it gain the Super column.

The plan and tasks will be revised after this spec is approved again.

## 11. Spec quality checklist

- [x] No implementation details (language, framework, database, API).
- [x] Every story has a priority, an independent test and acceptance scenarios.
- [x] Every requirement is testable and unambiguous.
- [x] Success criteria are measurable and technology-independent.
- [x] Scope bounded (goals and out of scope).
- [x] Non-functional requirements from the constitution considered (III, IV, V, VII, X, XI).
- [x] No `[NEEDS CLARIFICATION]` remaining.
- [x] `§N` references correct.
