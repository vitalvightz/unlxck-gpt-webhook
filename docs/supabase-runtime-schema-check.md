# Supabase Runtime Schema Check

A deployment gate that verifies the **live, connected Supabase database** matches
the schema the backend depends on — before the backend is deployed or started.

This complements the static SQL-text test (`tests/test_supabase_schema.py`),
which only inspects `supabase/schema.sql` and the migration files. The static
test confirms the *intended* schema is written down; this check confirms the
*actual* database has it.

## What the check does

The checker connects to the real Supabase project and asks the database to
introspect its own catalog via the `public.runtime_schema_introspection()` RPC.
That RPC returns **catalog metadata only** — table/column/function/index/
constraint names and per-table RLS flags. It never reads application or user row
data, and no secrets are ever printed.

The returned snapshot is diffed against the centralized requirements in
[`api/schema_requirements.py`](../api/schema_requirements.py):

- **Required tables:** `profiles`, `plans`, `generation_jobs`,
  `athlete_intakes`, `plan_generation_rate_limits`.
- **Required columns** on `plans`, `generation_jobs`, and `profiles` (including
  the Stage 1/Stage 2 plan runtime columns such as `stage2_payload`,
  `planning_brief`, and `parsing_metadata`).
- **Required functions/RPCs:** `change_profile_username`,
  `try_parse_timestamptz`, `check_plan_generation_short_window_limit`,
  `prevent_self_role_escalation`, `prevent_username_policy_bypass`, `is_admin`.
- **Required indexes/constraints:** the `generation_jobs` active-job
  uniqueness/lock, the `generation_jobs` athlete/client-request uniqueness, the
  `plan_generation_rate_limits` athlete/created index, and `profiles` username
  uniqueness.
- **RLS enabled** on `profiles`, `plans`, `athlete_intakes`, `generation_jobs`,
  and `plan_generation_rate_limits`.

> **Note on the intakes table.** The application stores athlete intakes in the
> `public.athlete_intakes` table (see `api/store.py`); there is no table named
> `intakes`. The checker therefore requires `athlete_intakes`, which is the
> canonical name the backend actually depends on.

## When to run it

Run it as a **deploy gate**, after database migrations are applied and before
the backend starts serving traffic. Because it exits non-zero on any missing or
incorrect schema piece, it is safe to wire into a deploy pipeline or a manual
release checklist.

## Required environment variables

The check reuses the backend's existing Supabase service-role integration:

| Variable                    | Purpose                                              |
| --------------------------- | ---------------------------------------------------- |
| `SUPABASE_URL`              | Supabase project URL                                 |
| `SUPABASE_SERVICE_ROLE_KEY` | Service-role key (the introspection RPC is restricted to `service_role`) |

These are the same variables the backend uses; no new credential pattern is
introduced. The values are never printed by the checker.

## Command

```bash
python tools/check_supabase_runtime_schema.py
```

### Output

On success:

```
✅ Supabase runtime schema check passed.
```

On failure (only sections with problems are shown):

```
❌ Supabase runtime schema check failed.
Missing tables:
- plan_generation_rate_limits
Missing columns:
- plans.stage2_payload
Missing functions:
- public.check_plan_generation_short_window_limit
Missing indexes/constraints:
- plan_generation_rate_limits athlete/created index
RLS issues:
- generation_jobs RLS is not enabled
```

### Exit codes

| Code | Meaning                                                              |
| ---- | ------------------------------------------------------------------- |
| `0`  | Schema check passed.                                                |
| `1`  | Schema check ran but found missing/incorrect schema pieces.         |
| `2`  | The check could not run (missing env vars, the introspection RPC is not installed, or a connection error). |

If you see exit code `2` complaining that `runtime_schema_introspection` was not
found, apply the migrations first (see below) — the RPC ships in
`supabase/migrations/20260602000000_add_runtime_schema_introspection_rpc.sql`.

## Deployment rule

**Run migrations first, then run the schema check, then deploy the backend.**

```text
1. Apply Supabase migrations (supabase db push / your migration runner).
2. python tools/check_supabase_runtime_schema.py   # must exit 0
3. Deploy / start the backend.
```

This ordering matters: the introspection RPC is itself shipped as a migration,
so the schema check can only succeed once migrations have been applied.

## Running the live check in CI (optional)

The default backend CI workflow (`.github/workflows/backend-checks.yml`) runs
only the unit tests, which use fake catalog data and need no credentials.

To additionally run the **live** check in CI, add these GitHub repository
secrets and call the script in a job after migrations have run against the
target database:

- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`

Example step (only safe where the secrets are configured and point at the
correct, already-migrated environment):

```yaml
- name: Live Supabase runtime schema check
  if: ${{ secrets.SUPABASE_URL != '' && secrets.SUPABASE_SERVICE_ROLE_KEY != '' }}
  env:
    SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
    SUPABASE_SERVICE_ROLE_KEY: ${{ secrets.SUPABASE_SERVICE_ROLE_KEY }}
  run: python tools/check_supabase_runtime_schema.py
```

Do not point the live check at production unless production migrations have
already been applied.
