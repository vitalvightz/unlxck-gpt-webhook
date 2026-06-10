import re
from pathlib import Path


SCHEMA_PATH = Path(__file__).resolve().parents[1] / "supabase" / "schema.sql"
USERNAME_MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "supabase"
    / "migrations"
    / "20260518000000_add_profile_username.sql"
)
USERNAME_ATOMIC_MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "supabase"
    / "migrations"
    / "20260525000000_change_username_atomic_rpc.sql"
)
PLAN_RATE_LIMIT_MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "supabase"
    / "migrations"
    / "20260525110000_add_plan_generation_short_window_rate_limit.sql"
)
DAILY_CAP_MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "supabase"
    / "migrations"
    / "20260606005000_atomic_daily_generation_cap.sql"
)
CRITICAL_RLS_MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "supabase"
    / "migrations"
    / "20260531000000_harden_critical_table_rls.sql"
)
TERMINAL_RPCS_MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "supabase"
    / "migrations"
    / "20260608184148_harden_generation_job_terminal_rpcs.sql"
)
WORKER_OWNERSHIP_MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "supabase"
    / "migrations"
    / "20260610120000_add_generation_job_worker_ownership.sql"
)


def _read_schema() -> str:
    return SCHEMA_PATH.read_text(encoding="utf-8")


def _read_username_migration() -> str:
    return USERNAME_MIGRATION_PATH.read_text(encoding="utf-8")


def _read_username_atomic_migration() -> str:
    return USERNAME_ATOMIC_MIGRATION_PATH.read_text(encoding="utf-8")


def _read_plan_rate_limit_migration() -> str:
    return PLAN_RATE_LIMIT_MIGRATION_PATH.read_text(encoding="utf-8")


def _read_daily_cap_migration() -> str:
    return DAILY_CAP_MIGRATION_PATH.read_text(encoding="utf-8")


def _read_critical_rls_migration() -> str:
    return CRITICAL_RLS_MIGRATION_PATH.read_text(encoding="utf-8")


def _read_terminal_rpcs_migration() -> str:
    return TERMINAL_RPCS_MIGRATION_PATH.read_text(encoding="utf-8")


def _read_worker_ownership_migration() -> str:
    return WORKER_OWNERSHIP_MIGRATION_PATH.read_text(encoding="utf-8")


def test_profiles_table_declares_avatar_url_column():
    schema = _read_schema()
    profiles_definition = schema.split("create table if not exists public.profiles (", 1)[1].split(");", 1)[0]

    assert "avatar_url text," in profiles_definition


def test_generation_jobs_schema_declares_payload_hash_column():
    schema = _read_schema()
    generation_jobs_definition = schema.split(
        "create table if not exists public.generation_jobs (", 1
    )[1].split(");", 1)[0]

    assert "payload_hash text," in generation_jobs_definition
    assert "alter table public.generation_jobs add column if not exists payload_hash text;" in schema


def test_generation_jobs_schema_declares_failed_at_column():
    schema = _read_schema()
    generation_jobs_definition = schema.split(
        "create table if not exists public.generation_jobs (", 1
    )[1].split(");", 1)[0]

    assert "failed_at timestamptz," in generation_jobs_definition
    assert "alter table public.generation_jobs add column if not exists failed_at timestamptz;" in schema


def test_profiles_migration_backfills_avatar_url_column():
    schema = _read_schema()

    assert "alter table public.profiles add column if not exists avatar_url text;" in schema


def test_schema_does_not_hardcode_admin_email_promotions():
    schema = _read_schema()

    assert "Grant admin role to designated admin accounts." not in schema
    assert "vitalvightz@gmail.com" not in schema
    assert "michaelokaforjr@gmail.com" not in schema
    assert "unlxckedmind@gmail.com" not in schema
    assert "frankribery@mailfence.com" not in schema


def test_schema_guards_against_self_role_escalation():
    schema = _read_schema()

    function_match = re.search(
        r"create or replace function public\.prevent_self_role_escalation\(\).*?\$\$;",
        schema,
        re.IGNORECASE | re.DOTALL,
    )
    assert function_match is not None

    function_section = function_match.group(0)

    assert "security definer" in function_section
    assert "set search_path = public" in function_section
    assert "tg_op = 'INSERT'" in function_section
    assert "new.role <> 'athlete'" in function_section
    assert "tg_op = 'UPDATE'" in function_section
    assert "new.role is distinct from old.role" in function_section
    assert "before insert or update on public.profiles" in schema
    assert "Only admins can change profile roles." in schema


def test_profiles_table_declares_username_check_constraints():
    schema = _read_schema()

    assert re.search(
        r"profiles_username_length[^;]*char_length\(username\)\s+between\s+3\s+and\s+24",
        schema,
        re.IGNORECASE | re.DOTALL,
    )
    assert re.search(
        r"profiles_username_lowercase[^;]*username\s*=\s*lower\(username\)",
        schema,
        re.IGNORECASE | re.DOTALL,
    )
    assert re.search(
        r"profiles_username_format[^;]*\^\[a-z0-9\]\(\[a-z0-9\._-\]\*\[a-z0-9\]\)\?\$",
        schema,
        re.IGNORECASE | re.DOTALL,
    )


def test_username_migration_backfills_check_constraints():
    migration = _read_username_migration()

    for constraint in (
        "profiles_username_length",
        "profiles_username_lowercase",
        "profiles_username_format",
    ):
        assert constraint in migration, f"missing {constraint} in username migration"

    assert re.search(
        r"char_length\(username\)\s+between\s+3\s+and\s+24",
        migration,
        re.IGNORECASE,
    )
    assert re.search(r"username\s*=\s*lower\(username\)", migration, re.IGNORECASE)
    assert "^[a-z0-9]([a-z0-9._-]*[a-z0-9])?$" in migration


def test_prevent_username_policy_bypass_function_exists():
    schema = _read_schema()

    function_match = re.search(
        r"create or replace function public\.prevent_username_policy_bypass\(\).*?\$\$;",
        schema,
        re.IGNORECASE | re.DOTALL,
    )
    assert function_match is not None, "prevent_username_policy_bypass function missing"

    function_section = function_match.group(0)
    assert "security definer" in function_section
    assert "set search_path = public" in function_section
    assert "auth.role() <> 'service_role'" in function_section
    assert "public.is_admin()" in function_section
    assert "new.username is distinct from old.username" in function_section
    assert (
        "new.username_change_history is distinct from old.username_change_history"
        in function_section
    )
    assert "Use the username change endpoint." in function_section


def test_prevent_username_policy_bypass_trigger_runs_before_update():
    schema = _read_schema()

    assert "drop trigger if exists profiles_prevent_username_policy_bypass on public.profiles;" in schema
    assert re.search(
        r"create trigger profiles_prevent_username_policy_bypass\s+before update on public\.profiles\s+for each row\s+execute function public\.prevent_username_policy_bypass\(\);",
        schema,
        re.IGNORECASE,
    )


def test_username_migration_installs_bypass_trigger():
    migration = _read_username_migration()

    assert "create or replace function public.prevent_username_policy_bypass()" in migration
    assert "drop trigger if exists profiles_prevent_username_policy_bypass on public.profiles;" in migration
    assert re.search(
        r"create trigger profiles_prevent_username_policy_bypass\s+before update on public\.profiles\s+for each row\s+execute function public\.prevent_username_policy_bypass\(\);",
        migration,
        re.IGNORECASE,
    )


def test_direct_non_admin_username_update_is_blocked_by_schema():
    schema = _read_schema()

    function_match = re.search(
        r"create or replace function public\.prevent_username_policy_bypass\(\).*?\$\$;",
        schema,
        re.IGNORECASE | re.DOTALL,
    )
    assert function_match is not None
    function_section = function_match.group(0)

    # A non-service-role, non-admin update touching username or its history must raise.
    guard_match = re.search(
        r"if\s+auth\.role\(\)\s*<>\s*'service_role'\s+and\s+not\s+public\.is_admin\(\)\s+then\s+if\s+new\.username\s+is\s+distinct\s+from\s+old\.username\s+or\s+new\.username_change_history\s+is\s+distinct\s+from\s+old\.username_change_history\s+then\s+raise\s+exception\s+'Use the username change endpoint\.';",
        function_section,
        re.IGNORECASE | re.DOTALL,
    )
    assert guard_match is not None, "non-admin username/history update must raise"


def test_schema_blocks_direct_critical_table_mutations():
    schema = _read_schema()

    for policy in (
        "intakes_self_or_admin_insert",
        "intakes_self_or_admin_update",
        "intakes_self_or_admin_delete",
        "athlete_intakes_self_or_admin_insert",
        "athlete_intakes_self_or_admin_update",
        "athlete_intakes_self_or_admin_delete",
        "plans_self_or_admin_insert",
        "plans_self_or_admin_update",
        "plans_self_or_admin_delete",
        "generation_jobs_self_or_admin_insert",
        "generation_jobs_self_or_admin_update",
        "generation_jobs_self_or_admin_delete",
    ):
        assert f'drop policy if exists "{policy}"' in schema
        assert f'create policy "{policy}"' not in schema

    for policy in (
        "intakes_self_or_admin_select",
        "plans_self_or_admin_select",
        "generation_jobs_self_or_admin_select",
    ):
        assert f'create policy "{policy}"' in schema


def test_critical_table_rls_hardening_migration_drops_direct_mutation_policies():
    migration = _read_critical_rls_migration()

    for policy in (
        "intakes_self_or_admin_insert",
        "intakes_self_or_admin_update",
        "intakes_self_or_admin_delete",
        "athlete_intakes_self_or_admin_insert",
        "athlete_intakes_self_or_admin_update",
        "athlete_intakes_self_or_admin_delete",
        "plans_self_or_admin_insert",
        "plans_self_or_admin_update",
        "plans_self_or_admin_delete",
        "generation_jobs_self_or_admin_insert",
        "generation_jobs_self_or_admin_update",
        "generation_jobs_self_or_admin_delete",
    ):
        assert f'drop policy if exists "{policy}"' in migration
        assert f'create policy "{policy}"' not in migration


def test_change_profile_username_rpc_exists_in_schema():
    schema = _read_schema()
    parser_function_match = re.search(
        r"create or replace function public\.try_parse_timestamptz\(p_value text\).*?\$\$;",
        schema,
        re.IGNORECASE | re.DOTALL,
    )
    assert parser_function_match is not None
    parser_function_section = parser_function_match.group(0)

    function_match = re.search(
        r"create or replace function public\.change_profile_username\(.*?\$\$;",
        schema,
        re.IGNORECASE | re.DOTALL,
    )
    assert function_match is not None
    function_section = function_match.group(0)

    assert "create or replace function public.change_profile_username(" in schema
    assert "create or replace function public.try_parse_timestamptz(" in schema
    assert "stable" in parser_function_section
    assert "immutable" not in parser_function_section
    assert "for update;" in schema
    assert "raise exception 'username_rate_limit_exceeded:%'" in schema
    assert "(value #>> '{}')::timestamptz" not in schema
    assert "jsonb_typeof(v_profile.username_change_history) = 'array'" in function_section
    assert "public.try_parse_timestamptz(value_text)" in function_section
    assert "value_text::timestamptz" not in function_section
    assert "revoke execute on function public.change_profile_username(uuid, text) from public;" in schema
    assert "revoke execute on function public.change_profile_username(uuid, text) from anon;" in schema
    assert "revoke execute on function public.change_profile_username(uuid, text) from authenticated;" in schema
    assert "grant execute on function public.change_profile_username(uuid, text) to service_role;" in schema


def test_change_profile_username_rpc_migration_exists():
    migration = _read_username_atomic_migration()
    parser_function_match = re.search(
        r"create or replace function public\.try_parse_timestamptz\(p_value text\).*?\$\$;",
        migration,
        re.IGNORECASE | re.DOTALL,
    )
    assert parser_function_match is not None
    parser_function_section = parser_function_match.group(0)

    function_match = re.search(
        r"create or replace function public\.change_profile_username\(.*?\$\$;",
        migration,
        re.IGNORECASE | re.DOTALL,
    )
    assert function_match is not None
    function_section = function_match.group(0)

    assert "create or replace function public.change_profile_username(" in migration
    assert "create or replace function public.try_parse_timestamptz(" in migration
    assert "stable" in parser_function_section
    assert "immutable" not in parser_function_section
    assert "for update;" in migration
    assert "raise exception 'username_rate_limit_exceeded:%'" in migration
    assert "(value #>> '{}')::timestamptz" not in migration
    assert "jsonb_typeof(v_profile.username_change_history) = 'array'" in function_section
    assert "public.try_parse_timestamptz(value_text)" in function_section
    assert "value_text::timestamptz" not in function_section
    assert "revoke execute on function public.change_profile_username(uuid, text) from public;" in migration
    assert "revoke execute on function public.change_profile_username(uuid, text) from anon;" in migration
    assert "revoke execute on function public.change_profile_username(uuid, text) from authenticated;" in migration
    assert "grant execute on function public.change_profile_username(uuid, text) to service_role;" in migration


def test_plan_generation_short_window_rate_limit_schema_and_migration():
    schema = _read_schema()
    migration = _read_plan_rate_limit_migration()

    for sql in (schema, migration):
        assert "create table if not exists public.plan_generation_rate_limits (" in sql
        assert "athlete_id uuid not null references public.profiles(id) on delete cascade" in sql
        assert "alter table public.plan_generation_rate_limits enable row level security;" in sql
        assert "create index if not exists plan_generation_rate_limits_athlete_created_idx" in sql
        assert "create or replace function public.check_plan_generation_short_window_limit(" in sql
        assert "delete from public.plan_generation_rate_limits" in sql
        assert "where athlete_id = p_athlete_id" in sql
        assert "created_at <= v_cutoff" in sql
        assert "pg_advisory_xact_lock(" in sql
        assert "hashtext('plan_generation_rate_limits')" in sql
        assert "hashtext(p_athlete_id::text)" in sql
        assert (
            "revoke all on function public.check_plan_generation_short_window_limit(uuid, integer, double precision) from public;"
            in sql
        )
        assert (
            "revoke all on function public.check_plan_generation_short_window_limit(uuid, integer, double precision) from anon;"
            in sql
        )
        assert (
            "revoke all on function public.check_plan_generation_short_window_limit(uuid, integer, double precision) from authenticated;"
            in sql
        )
        assert (
            "grant execute on function public.check_plan_generation_short_window_limit(uuid, integer, double precision) to service_role;"
            in sql
        )


def test_daily_generation_cap_atomic_create_rpc_schema_and_migration():
    schema = _read_schema()
    migration = _read_daily_cap_migration()

    for sql in (schema, migration):
        assert "create or replace function public.create_generation_job_with_daily_limit(" in sql
        assert "returns table (job jsonb, limit_exceeded boolean)" in sql
        assert "pg_advisory_xact_lock(" in sql
        assert "hashtext('generation_jobs_daily_cap')" in sql
        assert "hashtext(p_athlete_id::text)" in sql
        assert "where athlete_id = p_athlete_id" in sql
        assert "and created_at >= p_day_start" in sql
        assert "v_count >= p_daily_limit" in sql
        assert "insert into public.generation_jobs" in sql
        assert "raise exception 'generation_job_in_flight'" in sql

    assert (
        "revoke all on function public.create_generation_job_with_daily_limit(uuid, text, text, jsonb, integer, timestamptz, text[], uuid, uuid, text) from public;"
        in schema
    )
    assert (
        "grant execute on function public.create_generation_job_with_daily_limit(uuid, text, text, jsonb, integer, timestamptz, text[], uuid, uuid, text) to service_role;"
        in schema
    )
    assert (
        "revoke all on function public.create_generation_job_with_daily_limit(uuid, text, text, jsonb, integer, timestamptz, text[], uuid, uuid) from public;"
        in migration
    )
    assert (
        "grant execute on function public.create_generation_job_with_daily_limit(uuid, text, text, jsonb, integer, timestamptz, text[], uuid, uuid) to service_role;"
        in migration
    )

    assert "Rollback notes:" in migration
    assert "drop function if exists public.create_generation_job_with_daily_limit" in migration


def test_generation_job_terminal_rpcs_schema_and_migration():
    schema = _read_schema()
    migration = _read_terminal_rpcs_migration()

    for sql in (schema, migration):
        assert "alter table public.generation_jobs" in sql
        assert "add column if not exists failed_at timestamptz" in sql
        assert "create or replace function public.complete_generation_job(" in sql
        assert "create or replace function public.fail_generation_job(" in sql
        assert "returns jsonb" in sql
        assert "security definer" in sql
        assert "set search_path = public" in sql
        assert "for update;" in sql
        assert "p_expected_attempt_count" in sql
        assert "wrong_generation_job_status" in sql
        assert "stale_generation_job_attempt" in sql
        assert "generation_job_missing" in sql
        assert "completed_at = v_completed_at" in sql
        assert "failed_at = v_failed_at" in sql
        assert "updated_at = now()" in sql

    # The original migration carries the pre-ownership signatures; the schema
    # (and the worker-ownership migration) carry the p_expected_worker_id ones.
    assert (
        "revoke all on function public.complete_generation_job(uuid, text, integer, text, jsonb, uuid, text, timestamptz, timestamptz) from public;"
        in migration
    )
    assert (
        "grant execute on function public.complete_generation_job(uuid, text, integer, text, jsonb, uuid, text, timestamptz, timestamptz) to service_role;"
        in migration
    )
    assert (
        "revoke all on function public.fail_generation_job(uuid, text, integer, text, jsonb, uuid, jsonb, timestamptz, timestamptz) from public;"
        in migration
    )
    assert (
        "grant execute on function public.fail_generation_job(uuid, text, integer, text, jsonb, uuid, jsonb, timestamptz, timestamptz) to service_role;"
        in migration
    )


def test_generation_job_worker_ownership_schema_and_migration():
    schema = _read_schema()
    migration = _read_worker_ownership_migration()

    for sql in (schema, migration):
        assert "add column if not exists claimed_by text" in sql
        assert "add column if not exists claimed_at timestamptz" in sql
        assert "create or replace function public.claim_generation_job(" in sql
        assert "p_worker_id" in sql
        assert "missing_generation_job_worker_id" in sql
        assert "claimed_by = v_worker_id" in sql
        assert "claimed_at = v_claimed_at" in sql
        assert "and coalesce(attempt_count, 0) = p_expected_attempt_count" in sql
        # Terminal RPCs must carry the ownership guard.
        assert "p_expected_worker_id text default null" in sql
        assert "stale_generation_job_worker" in sql
        # The pre-ownership terminal RPC signatures must be dropped so PostgREST
        # never sees two overloads.
        assert (
            "drop function if exists public.complete_generation_job(uuid, text, integer, text, jsonb, uuid, text, timestamptz, timestamptz);"
            in sql
        )
        assert (
            "drop function if exists public.fail_generation_job(uuid, text, integer, text, jsonb, uuid, jsonb, timestamptz, timestamptz);"
            in sql
        )
        assert (
            "revoke all on function public.claim_generation_job(uuid, text, text, integer, jsonb, timestamptz) from public;"
            in sql
        )
        assert (
            "revoke all on function public.claim_generation_job(uuid, text, text, integer, jsonb, timestamptz) from anon;"
            in sql
        )
        assert (
            "revoke all on function public.claim_generation_job(uuid, text, text, integer, jsonb, timestamptz) from authenticated;"
            in sql
        )
        assert (
            "grant execute on function public.claim_generation_job(uuid, text, text, integer, jsonb, timestamptz) to service_role;"
            in sql
        )
        assert (
            "grant execute on function public.complete_generation_job(uuid, text, integer, text, jsonb, uuid, text, timestamptz, timestamptz, text) to service_role;"
            in sql
        )
        assert (
            "grant execute on function public.fail_generation_job(uuid, text, integer, text, jsonb, uuid, jsonb, timestamptz, timestamptz, text) to service_role;"
            in sql
        )
