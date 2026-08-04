from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "supabase" / "migrations" / "20260804082630_block_empty_global_feedback_xp.sql"
GLOBAL_FEEDBACK = ROOT / "web" / "components" / "feedback" / "global-feedback.tsx"


def test_blank_global_feedback_is_rejected_by_the_authoritative_xp_rpc():
    sql = MIGRATION.read_text(encoding="utf-8")

    assert "v_feedback_surface <> 'global'" in sql
    assert "regexp_replace(coalesce(v_feedback_comment, ''), '[[:space:]]+', '', 'g') <> ''" in sql
    assert "or v_feedback_has_screenshot" in sql
    assert "if v_feedback_eligible then" in sql
    assert "'eligible', v_feedback_eligible" in sql


def test_feedback_daily_cap_remains_three_rewardable_records_per_utc_day():
    sql = MIGRATION.read_text(encoding="utf-8")

    assert "v_daily_count >= 3" in sql
    assert "at time zone 'UTC'" in sql


def test_settings_ui_cannot_submit_an_empty_feedback_form():
    source = GLOBAL_FEEDBACK.read_text(encoding="utf-8")

    assert "const hasSubmission = Boolean(description.trim() || screenshot);" in source
    assert "if (!hasSubmission)" in source
    assert "disabled={submitting || !hasSubmission}" in source
