from pathlib import Path


SQL = Path("supabase/migrations/20260820120000_add_rehab_exposures.sql").read_text().lower()


def test_exposure_id_is_the_idempotency_key():
    assert "id uuid primary key" in SQL


def test_exposure_is_bound_to_athlete_injury_and_episode():
    assert "foreign key (injury_id, athlete_id, injury_episode_id)" in SQL
    assert "references public.injury_flags (id, athlete_id, episode_id)" in SQL


def test_exposure_rls_is_owner_scoped():
    assert "alter table public.rehab_exposures enable row level security" in SQL
    for operation in ("select", "insert", "update", "delete"):
        assert f'"rehab_exposures_owner_{operation}"' in SQL
    assert SQL.count("athlete_id = auth.uid()") >= 5


def test_persistence_keeps_prescribed_and_completed_dose_separate():
    assert "prescribed_dose jsonb" in SQL
    assert "completed_dose jsonb not null" in SQL


def test_generic_context_is_not_persisted_as_local_evidence():
    assert "camp_phase" not in SQL
    assert "session_rpe" not in SQL
    assert "pain_after" not in SQL
    assert "updated_at" not in SQL
