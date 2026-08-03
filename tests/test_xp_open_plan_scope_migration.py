from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCOPE_MIGRATION = (
    ROOT
    / "supabase"
    / "migrations"
    / "20260803183400_scope_open_plan_phase_rewards.sql"
)
GATE_MIGRATION = (
    ROOT
    / "supabase"
    / "migrations"
    / "20260803183500_finalize_xp_rollout_readiness.sql"
)


def test_open_plan_phase_scope_uses_stable_projection_anchor() -> None:
    scope_sql = " ".join(
        SCOPE_MIGRATION.read_text(encoding="utf-8").lower().split()
    )
    gate_sql = " ".join(
        GATE_MIGRATION.read_text(encoding="utf-8").lower().split()
    )

    assert "open_ongoing_system" in scope_sql
    assert "xp_open_plan_anchor_date(plan.id)" in scope_sql
    assert "'open-anchor:'" in scope_sql
    assert "grant execute on function public.xp_plan_reward_scope(uuid) to service_role" in scope_sql
    assert "'open_plan_scope_ready', true" in gate_sql
