from pathlib import Path


SQL = Path("supabase/migrations/20260820120000_add_rehab_exposures.sql").read_text().lower()


def test_exposure_id_is_the_idempotency_key():
    assert "id uuid primary key" in SQL


def test_exposure_is_bound_to_athlete_injury_and_episode():
    assert "foreign key (injury_id, athlete_id, injury_episode_id)" in SQL
    assert "references public.injury_flags (id, athlete_id, episode_id)" in SQL


def test_resolved_to_active_transition_rotates_episode_atomically():
    assert "create trigger rotate_injury_evidence_episode" in SQL
    assert "old.status = 'resolved' and new.status in ('open', 'monitoring')" in SQL
    assert "new.episode_id := gen_random_uuid()" in SQL


def test_exposure_rls_is_owner_scoped():
    assert "alter table public.rehab_exposures enable row level security" in SQL
    assert '"rehab_exposures_owner_select"' in SQL
    assert "for select using (athlete_id = auth.uid())" in SQL


def test_authenticated_clients_cannot_mutate_evidence_directly():
    assert "revoke all on table public.rehab_exposures from anon, authenticated, service_role" in SQL
    assert "grant select on table public.rehab_exposures to authenticated" in SQL
    assert "grant select, insert" not in SQL
    assert "for update" not in SQL
    assert "for delete" not in SQL


def test_validated_rpc_is_service_only_and_rejects_identity_mismatch():
    assert "create or replace function public.record_rehab_exposure" in SQL
    assert "grant execute on function public.record_rehab_exposure(uuid, jsonb) to service_role" in SQL
    assert "exposure does not match injury episode, region and side" in SQL
    assert "invalid injury-specific pain response" in SQL


def test_persistence_keeps_prescribed_and_completed_dose_separate():
    assert "prescribed_dose jsonb" in SQL
    assert "completed_dose jsonb not null" in SQL


def test_generic_context_is_not_persisted_as_local_evidence():
    assert "camp_phase" not in SQL
    assert "session_rpe" not in SQL
    assert "pain_after" not in SQL
    assert "updated_at" not in SQL
