from pathlib import Path


MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "supabase"
    / "migrations"
    / "20260812155956_redesign_fight_camp_notifications.sql"
)


def test_notification_redesign_migration_is_private_and_auditable() -> None:
    sql = MIGRATION.read_text(encoding="utf-8").lower()
    for table in (
        "notification_evaluations",
        "notification_templates",
        "notification_action_states",
    ):
        assert f"create table if not exists public.{table}" in sql
        assert f"alter table public.{table} enable row level security" in sql
        assert f"revoke all on public.{table} from public, anon, authenticated" in sql
        assert f"grant all on public.{table} to service_role" in sql
    for function in (
        "claim_notification_delivery_v2",
        "record_notification_evaluation",
        "invalidate_notification_action",
    ):
        assert f"create or replace function public.{function}" in sql
        assert f"grant execute on function public.{function}" in sql
    assert "duplicate_dedupe_key" in sql
    assert "cooldown_active" in sql
    assert "daily_cap" in sql
    assert "user_action_already_done" in sql


def test_notification_templates_include_high_frequency_variants() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")
    for prefix in ("mr", "mc", "db", "sp", "sn", "sr", "pl", "ir", "hp", "rn"):
        for number in range(1, 5):
            assert f"'{prefix}-0{number}'" in sql

