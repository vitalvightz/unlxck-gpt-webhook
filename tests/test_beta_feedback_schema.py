from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = (ROOT / "supabase" / "schema.sql").read_text(encoding="utf-8")
MIGRATION = (ROOT / "supabase" / "migrations" / "20260712134054_secure_beta_feedback.sql").read_text(encoding="utf-8")


def test_feedback_schema_uses_profile_identity_and_contextual_uniqueness():
    for sql in (SCHEMA, MIGRATION):
        assert "submitted_by_profile_id uuid not null references public.profiles(id) on delete cascade" in sql
        assert "unique (submitted_by_profile_id, context_key)" in sql
        assert "athlete_id uuid" not in sql.split("create table if not exists public.beta_feedback (", 1)[1].split(");", 1)[0]


def test_feedback_priority_constraint_has_no_duplicate_implicit_name():
    for sql in (SCHEMA, MIGRATION):
        table = sql.split("create table if not exists public.beta_feedback (", 1)[1].split(");", 1)[0]
        assert "priority text not null default 'normal'," in table
        assert "priority text not null default 'normal' check" not in table
        assert table.count("constraint beta_feedback_priority_check") == 1


def test_feedback_tables_are_service_role_only_with_rls():
    for sql in (SCHEMA, MIGRATION):
        assert "alter table public.beta_feedback enable row level security;" in sql
        assert "alter table public.beta_feedback_rate_limits enable row level security;" in sql
        assert "revoke all on public.beta_feedback from anon, authenticated;" in sql
        assert "revoke all on public.beta_feedback_rate_limits from anon, authenticated;" in sql
        assert "grant all on public.beta_feedback to service_role;" in sql
        policy_statements = [
            statement.lower()
            for statement in sql.split(";")
            if "create policy" in statement.lower()
        ]
        assert not any(
            "on public.beta_feedback" in statement
            for statement in policy_statements
        )


def test_feedback_rpc_is_atomic_configurable_and_private():
    assert "pg_advisory_xact_lock" in MIGRATION
    assert "p_report_limit integer" in MIGRATION
    assert "p_screenshot_limit integer" in MIGRATION
    assert "p_has_screenshot boolean" in MIGRATION
    assert "revoke all on function public.claim_beta_feedback_rate_limit" in MIGRATION
    assert "grant execute on function public.claim_beta_feedback_rate_limit" in MIGRATION


def test_private_bucket_retention_index_and_account_delete_guard_exist():
    assert "'feedback-screenshots'" in MIGRATION
    assert "false," in MIGRATION.split("insert into storage.buckets", 1)[1]
    assert "beta_feedback_screenshot_expiry_idx" in MIGRATION
    assert "guard_profile_feedback_screenshots_before_delete" in MIGRATION
    assert "feedback_screenshots_must_be_purged" in MIGRATION