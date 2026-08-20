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


DURING_SQL = Path(
    "supabase/migrations/20260820150000_add_rehab_exposure_during_response.sql"
).read_text().lower()


def test_during_response_is_validated_at_the_database_boundary():
    assert "invalid during-work response" in DURING_SQL
    assert "'better','same','worse','not_sure','not_reported'" in DURING_SQL


def test_during_response_defaults_to_not_reported_not_to_an_answer():
    """An exposure logged without asking must not read as "nothing was wrong"."""
    assert "coalesce(v_response->>'during_response','not_reported')" in DURING_SQL


def test_unknown_is_an_accepted_demand_level_at_the_database_boundary():
    """A drill whose demand is unreviewed still produces a storable observation.

    The RPC is the only write path, so if it rejected ``'unknown'`` the whole
    athlete flow would stop at the database however permissive the Python
    contract is.
    """
    assert "'unknown','minimal','low','moderate','high'" in DURING_SQL  # load
    assert "'unknown','none','low','moderate','high'" in DURING_SQL  # impact
    assert "'unknown','low','moderate','high'" in DURING_SQL  # velocity


def test_the_sql_says_why_unknown_demand_is_not_capacity_evidence():
    """The rule lives in three languages; the SQL must not read as a blank cheque."""
    assert "has_unknown_demand" in DURING_SQL


def test_the_during_response_migration_keeps_every_earlier_guarantee():
    """It replaces the whole RPC, so the PR3 checks must all still be present."""
    for guarantee in (
        "exposure does not match injury episode, region and side",
        "invalid injury-specific pain response",
        "invalid next-day response",
        "invalid exposure demand",
        "completed dose is empty",
        "exposure id already used with different evidence",
    ):
        assert guarantee in DURING_SQL
    assert "grant execute on function public.record_rehab_exposure(uuid, jsonb) to service_role" in DURING_SQL
    assert "revoke all on function public.record_rehab_exposure(uuid, jsonb) from public, anon, authenticated" in DURING_SQL


FINAL_SQL = Path(
    "supabase/migrations/20260820160000_validate_rehab_dose_completion_state.sql"
).read_text().lower()


def test_unquantified_completion_state_is_validated_at_the_database_boundary():
    assert "'completion_state'" in FINAL_SQL
    assert "'performed_amount_unknown','partial_amount_unknown','quantified'" in FINAL_SQL
    assert "unquantified completion state contains a measured amount" in FINAL_SQL
    assert "quantified completion state lacks a measured amount" in FINAL_SQL


def test_final_rpc_revision_keeps_every_earlier_guarantee():
    for guarantee in (
        "exposure does not match injury episode, region and side",
        "invalid injury-specific pain response",
        "invalid next-day response",
        "invalid during-work response",
        "invalid exposure demand",
        "completed dose is empty",
        "exposure id already used with different evidence",
        "has_unknown_demand",
    ):
        assert guarantee in FINAL_SQL
    assert "grant execute on function public.record_rehab_exposure(uuid, jsonb) to service_role" in FINAL_SQL
    assert "revoke all on function public.record_rehab_exposure(uuid, jsonb) from public, anon, authenticated" in FINAL_SQL
