from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = (
    ROOT
    / "supabase"
    / "migrations"
    / "20260803184000_scope_open_plan_phase_rewards.sql"
)


def test_open_plan_phase_scope_uses_stable_projection_anchor() -> None:
    sql = " ".join(MIGRATION.read_text(encoding="utf-8").lower().split())

    assert "open_ongoing_system" in sql
    assert "xp_open_plan_anchor_date(plan.id)" in sql
    assert "'open-anchor:'" in sql
    assert "'open_plan_scope_ready', true" in sql
    assert "grant execute on function public.xp_plan_reward_scope(uuid) to service_role" in sql
