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


def test_plans_schema_includes_manual_review_override_columns():
    schema = _read_schema()
    plans_definition = schema.split("create table if not exists public.plans (", 1)[1].split(");", 1)[0]

    assert "manual_injury_review_required boolean not null default false," in plans_definition
    assert "approved_for_stage2 boolean not null default false," in plans_definition
    assert "liability_disclaimer_acknowledged boolean not null default false," in plans_definition
