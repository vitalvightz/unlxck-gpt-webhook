from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION_DIR = ROOT / "supabase" / "migrations"
ROLLOUT_START = "20260803174400"
ROLLOUT_END = "20260803183500"


def _normalized(path: Path) -> str:
    return " ".join(path.read_text(encoding="utf-8").lower().split())


def _rollout_migrations() -> list[Path]:
    return [
        path
        for path in sorted(MIGRATION_DIR.glob("*.sql"))
        if ROLLOUT_START <= path.name[:14] <= ROLLOUT_END
    ]


def test_every_award_rpc_redefinition_keeps_old_backend_calls_compatible() -> None:
    migrations = _rollout_migrations()
    assert migrations
    assert migrations[0].name.startswith(
        "20260803174400_prepare_xp_legacy_compatibility"
    )

    compatibility = _normalized(migrations[0])
    assert "create or replace function public.xp_legacy_calendar_date" in compatibility
    assert compatibility.index(
        "create or replace function public.xp_legacy_calendar_date"
    ) < compatibility.index("create or replace function public.award_athlete_xp")

    redefining = []
    for path in migrations:
        sql = _normalized(path)
        if "create or replace function public.award_athlete_xp" not in sql:
            continue
        redefining.append(path.name)
        assert "p_calendar_date date default null" in sql, path.name
        assert "v_calendar_date date := p_calendar_date" in sql, path.name
        assert (
            "if v_calendar_scoped and v_calendar_date is null then "
            "v_calendar_date := public.xp_legacy_calendar_date"
        ) in sql, path.name
        assert "training_day = v_calendar_date" in sql, path.name
        assert "v_key, v_calendar_date" in sql, path.name
        assert "v_calendar_scoped <> (p_calendar_date is not null)" not in sql, path.name
        assert "calendar date is required for this xp action" not in sql, path.name

    assert redefining == [
        "20260803174400_prepare_xp_legacy_compatibility.sql",
        "20260803180000_remove_xp_session_sample_cap.sql",
        "20260803183300_keep_legacy_xp_calls_compatible.sql",
    ]


def test_strict_calendar_constraint_is_installed_after_compatibility() -> None:
    migrations = _rollout_migrations()
    compatibility_index = next(
        index
        for index, path in enumerate(migrations)
        if path.name.startswith("20260803174400_prepare_xp_legacy_compatibility")
    )
    constraint_index = next(
        index
        for index, path in enumerate(migrations)
        if "xp_awards_calendar_scope_check" in _normalized(path)
    )
    assert compatibility_index < constraint_index

    constraint_sql = _normalized(migrations[constraint_index])
    assert "create or replace function public.award_athlete_xp" not in constraint_sql
