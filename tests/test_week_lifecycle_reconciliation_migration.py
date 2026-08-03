from pathlib import Path


MIGRATION = Path(
    "supabase/migrations/20260803124500_add_week_lifecycle_reconciliation.sql"
)


def test_week_lifecycle_reconciliation_is_durable_and_backend_owned():
    sql = MIGRATION.read_text()

    assert "create table if not exists public.week_lifecycle_reconciliations" in sql
    assert "status in ('pending', 'completed')" in sql
    assert "unique (athlete_id, plan_id, week_id)" in sql
    assert "attempt_count = public.week_lifecycle_reconciliations.attempt_count + 1" in sql
    assert "create or replace function public.begin_week_lifecycle_reconciliation" in sql
    assert "create or replace function public.complete_week_lifecycle_reconciliation" in sql
    assert "restricted to the backend service role" in sql
    assert "grant execute on function public.begin_week_lifecycle_reconciliation" in sql
    assert "grant execute on function public.complete_week_lifecycle_reconciliation" in sql
    assert "grant select on table public.week_lifecycle_reconciliations to authenticated" in sql
    assert "revoke all on table public.week_lifecycle_reconciliations from anon, authenticated" in sql
