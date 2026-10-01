from pathlib import Path

from api.schema_requirements import REQUIRED_COLUMNS, REQUIRED_FUNCTIONS, REQUIRED_TABLES, RLS_REQUIRED_TABLES

SQL = Path("supabase/migrations/20260930173118_injury_episode_prescription_history.sql").read_text().lower()


def test_server_owned_episode_events_have_owner_reads_and_no_client_mutations():
    assert "alter table public.injury_episode_events enable row level security" in SQL
    assert "using ((select auth.uid()) = athlete_id)" in SQL
    assert "revoke all on public.injury_episode_events from anon, authenticated, service_role" in SQL
    assert "grant select on public.injury_episode_events to authenticated, service_role" in SQL
    assert "from public, anon, authenticated" in SQL
    assert "grant execute on function public.record_injury_episode_event(uuid, jsonb) to service_role" in SQL


def test_concurrent_starts_preserve_one_revision_and_recheck_injury_context():
    assert "old.prescription_snapshot" in SQL
    assert "prescription_revision_conflict" in SQL
    assert "pg_advisory_xact_lock" in SQL
    assert "i.updated_at is not distinct from" in SQL
    assert "on public.today_checkins for each row" in SQL
    assert "c.updated_at is not distinct from" in SQL
    assert "c.training_day = new.training_day" in SQL


def test_historical_observations_survive_reopening_without_rebinding_episode():
    assert "foreign key (injury_id, athlete_id) references public.injury_flags (id, athlete_id)" in SQL
    assert "a.attname = 'injury_episode_id'" in SQL
    assert "and athlete_id = p_athlete_id for share" in SQL
    assert "v_injury.episode_id <>" in SQL


def test_deploy_gate_requires_episode_and_prescription_migrations():
    assert "injury_episode_events" in REQUIRED_TABLES
    assert "injury_episode_events" in RLS_REQUIRED_TABLES
    assert "prescription_snapshot" in REQUIRED_COLUMNS["session_completions"]
    assert "public.record_injury_episode_event" in REQUIRED_FUNCTIONS
    assert "public.pending_delayed_rehab" in REQUIRED_FUNCTIONS
