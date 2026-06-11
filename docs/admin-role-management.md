# Admin role management runbook

## Why this exists

`UNLXCK_ADMIN_EMAILS` **seeds** a profile's role the first time that profile is
created (`api/store.py::_default_role_for`) and is also checked by the backend
before any admin-only access decision.

- Adding an email does **not** promote an existing athlete unless their
  `profiles.role` is also changed to `admin`.
- Removing an email blocks runtime admin access after the backend restarts with
  the new env var, but it does **not** demote the existing database role.

So admin grants and revocations after first sign-in must go through the backend,
which updates `profiles.role` and writes an audit row to
`public.admin_role_audit`. The database `prevent_self_role_escalation` trigger
blocks role changes from anon/authenticated sessions; only the service role
(this tooling) may change roles.

## The tool

`tools/manage_admin.py` requires the same service-role credentials the backend
uses:

```bash
export SUPABASE_URL=...                  # staging or production project URL
export SUPABASE_SERVICE_ROLE_KEY=...     # service-role key (never commit)
export UNLXCK_ADMIN_ACTOR="you@unlxck"   # optional; recorded in the audit trail
```

### List current admins

```bash
python tools/manage_admin.py list
```

### Promote an athlete to admin

```bash
python tools/manage_admin.py promote athlete@example.com --reason "new head coach"
```

### Revoke admin (demote to athlete)

```bash
python tools/manage_admin.py revoke former-admin@example.com --reason "offboarded 2026-06-06"
```

Revoking the **only** remaining admin is blocked by default to prevent lockout —
the command exits non-zero and changes nothing. If you genuinely intend to leave
zero admins, re-run with `--force-last-admin`:

```bash
python tools/manage_admin.py revoke former-admin@example.com --force-last-admin
```

Each command is idempotent: re-running a promote/revoke that matches the current
role makes no change and writes no audit row. `--reason` is optional but strongly
encouraged — it is stored verbatim in the audit trail.

## Audit trail

Every actual change is recorded in `public.admin_role_audit`:

| column | meaning |
|---|---|
| `target_athlete_id` | profile id (nulled if the profile is later deleted) |
| `target_email` | email at time of change |
| `previous_role` / `new_role` | the transition |
| `action` | `promote` or `revoke` |
| `actor` | who ran the change (`UNLXCK_ADMIN_ACTOR` or `cli:<os-user>`) |
| `reason` | free-text justification |
| `created_at` | timestamp |

The table is service-role write-only (no insert/update/delete policy exists, so
even an admin browser session cannot forge or tamper with rows). Admins may read
it. To inspect recent changes via SQL:

```sql
select created_at, action, target_email, previous_role, new_role, actor, reason
from public.admin_role_audit
order by created_at desc
limit 50;
```

## Operational guardrails

- **Lockout safety:** revoking the last admin is **blocked** unless
  `--force-last-admin` is passed. The backend also logs the live admin count at
  startup (`[admin] startup_admin_count=...`) and warns when it is zero. Alert on
  that warning.
- **Run against the right project:** double-check `SUPABASE_URL` points at the
  intended environment before promoting/revoking.
- **Offboarding checklist:** revoke admin here **and** disable/remove the
  Supabase auth user — revoking the role alone leaves the account able to sign in
  as an athlete.
