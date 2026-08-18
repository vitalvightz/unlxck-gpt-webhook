from pathlib import Path


MIGRATION = Path("supabase/migrations/20260818130000_add_atomic_streak_activity_rpc.sql")


def test_activity_rpc_serializes_insert_and_streak_aggregate_update():
    sql = MIGRATION.read_text()

    assert "record_athlete_daily_activity" in sql
    assert "pg_advisory_xact_lock" in sql
    assert "on conflict (athlete_id, activity_date) do nothing" in sql
    assert "login_best = greatest" in sql
    assert "grant execute on function public.record_athlete_daily_activity(uuid, date) to service_role" in sql
    assert "revoke all on function public.record_athlete_daily_activity(uuid, date) from authenticated" in sql
