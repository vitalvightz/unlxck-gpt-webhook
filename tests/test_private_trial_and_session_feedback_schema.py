"""Schema parity for the private trial gate and the session feedback surface.

The canonical `schema.sql` and the migrations that get a live database there
have to agree — a constraint that exists in only one of them is a deploy-time
surprise, not a test-time one.
"""

from pathlib import Path

from api.models import SESSION_FEEDBACK_SESSION_ID_MAX_CHARS


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = (ROOT / "supabase" / "schema.sql").read_text(encoding="utf-8")
TRIAL_MIGRATION = (
    ROOT / "supabase" / "migrations" / "20260806120000_add_private_trial_acknowledgement.sql"
).read_text(encoding="utf-8")
SESSION_MIGRATION = (
    ROOT / "supabase" / "migrations" / "20260806120500_add_session_feedback_surface.sql"
).read_text(encoding="utf-8")


def _beta_feedback_table(sql: str) -> str:
    return sql.split("create table if not exists public.beta_feedback (", 1)[1].split("\n);", 1)[0]


def test_private_trial_acknowledgement_column_exists_in_both():
    assert "private_trial_ack_at timestamptz" in SCHEMA
    assert "add column if not exists private_trial_ack_at timestamptz" in TRIAL_MIGRATION


def test_private_trial_migration_is_additive():
    # A column with no default and no NOT NULL: every existing profile stays
    # valid and simply reads as "has not acknowledged yet".
    assert "not null" not in TRIAL_MIGRATION.lower()
    assert "drop column" not in TRIAL_MIGRATION.lower()


def test_session_surface_and_category_are_admitted_in_both():
    for sql in (SCHEMA, SESSION_MIGRATION):
        assert "'plan', 'daily_recommendation', 'session', 'global'" in sql
        assert "'session_review'" in sql
        assert "(surface = 'session' and category = 'session_review')" in sql


def test_session_rows_carry_no_response_or_reason():
    for sql in (SCHEMA, SESSION_MIGRATION):
        assert "(surface in ('global', 'session') and response is null)" in sql
        assert "(surface in ('global', 'session') and reason is null)" in sql


def test_structured_answers_are_constrained_to_the_offered_choices():
    for sql in (SCHEMA, SESSION_MIGRATION):
        assert "beta_feedback_structured_response_check" in sql
        assert "in ('too_easy', 'appropriate', 'too_hard')" in sql
        assert "in ('clear', 'unclear')" in sql
        assert "in ('felt_right', 'something_wrong')" in sql
        # Non-session surfaces must not accumulate structured answers.
        assert "else structured_response = '{}'::jsonb" in sql


def test_session_id_is_present_exactly_on_session_rows():
    for sql in (SCHEMA, SESSION_MIGRATION):
        assert "beta_feedback_session_id_check" in sql
        assert "(surface = 'session' and session_id is not null" in sql
        assert "(surface <> 'session' and session_id is null)" in sql


def test_session_id_ceiling_matches_the_api_and_fits_the_context_key():
    # "session:{plan_id}:{session_id}:{training_day}" is 56 characters of frame
    # around a UUID plan id and an ISO date; context_key allows 180.
    assert 56 + SESSION_FEEDBACK_SESSION_ID_MAX_CHARS <= 180
    for sql in (SCHEMA, SESSION_MIGRATION):
        assert (
            f"char_length(session_id) between 1 and {SESSION_FEEDBACK_SESSION_ID_MAX_CHARS}" in sql
        )
        assert "char_length(context_key) between 1 and 180" in SCHEMA


def test_new_feedback_columns_default_so_existing_rows_stay_valid():
    assert "structured_response jsonb not null default '{}'::jsonb" in SESSION_MIGRATION
    assert "add column if not exists session_id text" in SESSION_MIGRATION
    table = _beta_feedback_table(SCHEMA)
    assert "structured_response jsonb not null default '{}'::jsonb" in table
    assert "session_id text," in table


def test_session_feedback_is_never_the_safety_priority():
    # The priority constraint routes only recommendation_safety and safety_issue
    # to the safety queue, so session_review can only ever be 'normal'. The
    # migration leaves that constraint alone, which is the point of asserting it.
    assert (
        "(priority = 'normal' and category not in ('recommendation_safety', 'safety_issue'))"
        in SCHEMA
    )
    assert "beta_feedback_priority_check" not in SESSION_MIGRATION
