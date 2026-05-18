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
