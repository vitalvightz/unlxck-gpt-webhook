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


def _read_schema() -> str:
    return SCHEMA_PATH.read_text(encoding="utf-8")


def _read_username_migration() -> str:
    return USERNAME_MIGRATION_PATH.read_text(encoding="utf-8")


def _read_username_atomic_migration() -> str:
    return USERNAME_ATOMIC_MIGRATION_PATH.read_text(encoding="utf-8")


def test_profiles_table_declares_avatar_url_column():
    schema = _read_schema()
    profiles_definition = schema.split("create table if not exists public.profiles (", 1)[1].split(");", 1)[0]

    assert "avatar_url text," in profiles_definition


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


def test_schema_has_update_delete_rls_policies():
    schema = _read_schema()

    assert re.search(r'create policy "plans_self_or_admin_update" on public\.plans\s+for update\s+using\s+\(athlete_id = auth\.uid\(\) or public\.is_admin\(\)\)\s+with check\s+\(athlete_id = auth\.uid\(\) or public\.is_admin\(\)\);', schema, re.IGNORECASE)
    assert re.search(r'create policy "plans_self_or_admin_delete" on public\.plans\s+for delete\s+using\s+\(athlete_id = auth\.uid\(\) or public\.is_admin\(\)\);', schema, re.IGNORECASE)
    assert re.search(r'create policy "intakes_self_or_admin_delete" on public\.athlete_intakes\s+for delete\s+using\s+\(athlete_id = auth\.uid\(\) or public\.is_admin\(\)\);', schema, re.IGNORECASE)
    assert re.search(r'create policy "generation_jobs_self_or_admin_delete" on public\.generation_jobs\s+for delete\s+using\s+\(athlete_id = auth\.uid\(\) or public\.is_admin\(\)\);', schema, re.IGNORECASE)


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
