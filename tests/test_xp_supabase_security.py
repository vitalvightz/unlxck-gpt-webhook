from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA = (REPO_ROOT / "supabase" / "schema.sql").read_text()
MIGRATION = (
    REPO_ROOT
    / "supabase"
    / "migrations"
    / "20260801203204_add_account_xp_ledger.sql"
).read_text()


def test_xp_tables_use_account_foreign_keys_and_two_idempotency_guards():
    for sql in (SCHEMA, MIGRATION):
        assert "athlete_id uuid primary key references public.profiles(id) on delete cascade" in sql
        assert "athlete_id uuid not null references public.profiles(id) on delete cascade" in sql
        assert "unique (athlete_id, idempotency_key)" in sql
        assert "xp_awards_one_daily_login_per_calendar_date" in sql


def test_xp_reward_values_are_database_enforced():
    for sql in (SCHEMA, MIGRATION):
        assert "action = 'daily_login' and amount = 10" in sql
        assert "action = 'training_logged' and amount = 25" in sql
        assert "action = 'planned_session_completed' and amount = 50" in sql
        assert "action = 'recommended_fighter_content_watched' and amount = 10" in sql
        assert "action = 'full_training_week_completed' and amount = 100" in sql


def test_rls_is_forced_and_authenticated_access_is_owner_read_only():
    for table in ("xp_accounts", "xp_awards"):
        assert f"alter table public.{table} enable row level security;" in SCHEMA
        assert f"alter table public.{table} force row level security;" in SCHEMA
        assert f"grant select on table public.{table} to authenticated;" in SCHEMA
        assert f"revoke all on table public.{table} from public, anon, authenticated;" in SCHEMA
        assert f"grant select, insert, update, delete on table public.{table} to service_role;" in SCHEMA

    assert "for select to authenticated\nusing ((select auth.uid()) = athlete_id);" in SCHEMA
    assert "for insert to authenticated" not in MIGRATION
    assert "for update to authenticated" not in MIGRATION
    assert "for delete to authenticated" not in MIGRATION


def test_atomic_award_function_is_service_role_only_and_security_invoker():
    for sql in (SCHEMA, MIGRATION):
        assert "create or replace function public.award_athlete_xp(" in sql
        assert "security invoker" in sql
        assert "coalesce(auth.role(), '') <> 'service_role'" in sql
        assert "revoke all on function public.award_athlete_xp(uuid, text, text, date)" in sql
        assert "grant execute on function public.award_athlete_xp(uuid, text, text, date)" in sql
        assert "to service_role;" in sql
