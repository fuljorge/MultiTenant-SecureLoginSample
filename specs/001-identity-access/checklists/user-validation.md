# User validation script (T079)

- **Feature:** 001-identity-access · **Criteria:** CS-001, CS-002, CS-003 and CS-008
- **When:** completion stage (SDD, stage 7), before marking the spec as Implemented
- **Run by:** a team member (facilitator) · **Participants:** 3 to 5 people who have
  never used SecureLogin
- **Environment:** staging or local (`AGENTS.md`, section 9), with real e-mail or Mailpit

Machine timings (RNF-007) were measured separately
([performance-rnf-007.md](performance-rnf-007.md)). This script measures the **person's**
time: reading the e-mail, understanding the screen, typing.

## Preparation

1. One e-mail account per participant (or Mailpit addresses, with the facilitator
   showing the inbox).
2. For CS-001, an installation without a Super Administrator (fresh database) and the
   command `cap-admin bootstrap-super-admin --email <participant> --name <name>`. Without a
   fresh installation, use the Super Administrator invitation from the UI, which follows
   the same activation path.
3. A stopwatch and this sheet. The facilitator does not help; they note where the person
   hesitated.

## Tasks

| # | Criterion | Who | Task given to the person | Starts | Ends | Target |
|---|---|---|---|---|---|---|
| T1 | CS-001 | Super Administrator | "You received a welcome e-mail. Sign in to SecureLogin." | Person opens the e-mail | Super Administrator home screen | < 5 min |
| T2 | CS-008 (invitation) | Super Administrator | "Invite the organization *Test Company* with *yourself* as the owner, using the second e-mail." | Click on Organizations | "Invitation sent" message | < 1 min |
| T3 | CS-008 (activation) | Invited owner | "You received an invitation. Sign in and reach the home screen." | Person opens the e-mail | Home screen as Administrator | < 5 min |
| T4 | CS-002 (invitation) | Administrator | "Invite a person with the Agent Designer role." | Click on Users | "Invitation sent" message | < 1 min |
| T5 | CS-002 (activation) | Invited person | "You received an invitation. Activate your account." | Person opens the e-mail | Home screen | < 3 min |
| T6 | CS-003 | Each participant, 3 times | "Sign out and sign in again." | Login screen open | Home screen | < 1 min (95% of attempts) |

## Log

| Participant | T1 | T2 | T3 | T4 | T5 | T6 (1) | T6 (2) | T6 (3) | Where they hesitated / comments |
|---|---|---|---|---|---|---|---|---|---|
| P1 | | | | | | | | | |
| P2 | | | | | | | | | |
| P3 | | | | | | | | | |
| P4 | | | | | | | | | |
| P5 | | | | | | | | | |

## Result

- [ ] CS-001: all initial activations under 5 min
- [ ] CS-002: invitations under 1 min and activations under 3 min
- [ ] CS-003: at least 95% of logins under 1 min
- [ ] CS-008: organization invitations under 1 min and activations under 5 min
- [ ] Usability problems noted have become tasks or spec adjustments

**Run on:** — · **Facilitator:** — · **Conclusion:** —
