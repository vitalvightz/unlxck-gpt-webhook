import re
from pathlib import Path


SCHEMA_PATH = Path(__file__).resolve().parents[1] / "supabase" / "schema.sql"


def _read_schema() -> str:
    return SCHEMA_PATH.read_text(encoding="utf-8")


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


def test_schema_has_update_delete_rls_policies():
    schema = _read_schema()

    assert "plans_self_or_admin_update" in schema
    assert "plans_self_or_admin_delete" in schema
    assert "intakes_self_or_admin_delete" in schema
    assert "generation_jobs_self_or_admin_delete" in schema
    assert "for update using (athlete_id = auth.uid() or public.is_admin())" in schema
    assert "for delete using (athlete_id = auth.uid() or public.is_admin())" in schema
