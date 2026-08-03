from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LEGACY_COMPATIBILITY = (
    ROOT
    / "supabase"
    / "migrations"
    / "20260803174400_prepare_xp_legacy_compatibility.sql"
)
INITIAL_HARDENING = (
    ROOT
    / "supabase"
    / "migrations"
    / "20260803174500_harden_xp_abuse_boundaries.sql"
)
FEEDBACK_CAP = (
    ROOT / "supabase" / "migrations" / "20260803174600_cap_feedback_xp.sql"
)
FINAL_AWARD_MIGRATION = (
    ROOT
    / "supabase"
    / "migrations"
    / "20260803180000_remove_xp_session_sample_cap.sql"
)
MIGRATIONS = (
    LEGACY_COMPATIBILITY,
    INITIAL_HARDENING,
    FEEDBACK_CAP,
    ROOT / "supabase" / "migrations" / "20260803175500_enforce_xp_source_integrity.sql",
    FINAL_AWARD_MIGRATION,
    ROOT / "supabase" / "migrations" / "20260803181000_lock_xp_to_one_plan_per_day.sql",
    ROOT / "supabase" / "migrations" / "20260803182000_guard_timezone_day_rollover.sql",
)
TODAY_ROUTE = ROOT / "api" / "routes" / "today.py"


def _normalized(path: Path) -> str:
    return " ".join(path.read_text(encoding="utf-8").lower().split())


def _sql() -> str:
    return " ".join(
        "\n".join(path.read_text(encoding="utf-8") for path in MIGRATIONS)
        .lower()
        .split()
    )


def _final_rpc_sql() -> str:
    return _normalized(FINAL_AWARD_MIGRATION)


def test_legacy_compatibility_precedes_every_strict_xp_boundary():
    assert LEGACY_COMPATIBILITY.name < INITIAL_HARDENING.name < FEEDBACK_CAP.name

    compatibility = _normalized(LEGACY_COMPATIBILITY)
    hardening = _normalized(INITIAL_HARDENING)

    assert "create or replace function public.xp_legacy_calendar_date" in compatibility
    assert compatibility.index(
        "create or replace function public.xp_legacy_calendar_date"
    ) < compatibility.index("create or replace function public.award_athlete_xp")
    assert "p_calendar_date date default null" in compatibility
    assert "v_calendar_date date := p_calendar_date" in compatibility
    assert (
        "if v_calendar_scoped and v_calendar_date is null then "
        "v_calendar_date := public.xp_legacy_calendar_date"
    ) in compatibility

    # The deployed backend sends only athlete/action/key. Session dates must be
    # recovered from terminal completion ids, while check-in/injury dates come
    # from the existing server-owned YYYY-MM-DD key suffix.
    assert "v_action in ('training_logged', 'planned_session_completed')" in compatibility
    assert "from public.session_completions as completion" in compatibility
    assert "substring(v_key from '([0-9]{4}-[0-9]{2}-[0-9]{2})$')" in compatibility

    # No later initial-boundary migration may replace the compatible RPC with a
    # version that rejects those old three-parameter calls mid-deployment.
    assert "create or replace function public.award_athlete_xp" not in hardening
    assert "calendar date is required for this xp action" not in hardening


def test_one_time_activation_rewards_are_unique_by_action_not_only_key():
    sql = _sql()
    assert "xp_awards_one_time_action_per_athlete" in sql
    assert "on public.xp_awards (athlete_id, action)" in sql
    for action in (
        "profile_completed",
        "first_intake_completed",
        "first_plan_ready",
        "first_checkin_completed",
        "first_plan_completed",
    ):
        assert f"'{action}'" in sql


def test_calendar_scopes_and_daily_unique_rewards_are_database_enforced():
    sql = _sql()
    assert "xp_awards_calendar_scope_check" in sql
    assert "xp_awards_one_daily_action_per_athlete" in sql
    assert "on public.xp_awards (athlete_id, action, calendar_date)" in sql
    for action in (
        "full_training_week_completed",
        "readiness_checkin_completed",
        "injury_update_completed",
        "stop_decision_followed",
    ):
        assert f"'{action}'" in sql


def test_session_awards_require_active_scheduled_terminal_completions():
    sql = _sql()
    assert "from public.session_completions" in sql
    assert "inactive plan cannot earn session xp" in sql
    assert "session xp source is not scheduled in the active plan" in sql
    assert "status in ('done', 'modified')" in sql
    assert "xp_resolved_active_plan_id" in sql


def test_same_day_session_xp_uses_immutable_plan_provenance_without_a_count_cap():
    sql = _sql()
    assert "add column if not exists source_plan_id uuid" in sql
    assert "new.source_plan_id := v_completion_plan_id" in sql
    assert "previous_award.source_plan_id is distinct from v_completion_plan_id" in sql
    assert "session xp source plan is immutable" in sql
    assert "xp_awards_source_plan_immutable" in sql
    assert "session xp is already locked to another plan for this training day" in sql
    final_rpc = _final_rpc_sql()
    assert "v_daily_count" not in final_rpc
    assert "< 2" not in final_rpc
    assert "insert into public.xp_awards" in final_rpc


def test_full_week_award_requires_every_structured_session():
    sql = _sql()
    assert "full-week xp source has no planned sessions" in sql
    assert "full-week xp requires every planned session to be completed or modified" in sql
    assert "completion.status in ('done', 'modified')" in sql


def test_activation_awards_require_authoritative_persisted_state_and_athlete_role():
    sql = _sql()
    assert "role::text = 'athlete'" in sql
    assert "profile activation milestone is not complete" in sql
    assert "intake activation milestone is not complete" in sql
    assert "plan activation milestone is not complete" in sql
    assert "first check-in milestone is not complete" in sql
    assert "daily check-in milestone is not complete" in sql


def test_feedback_xp_is_capped_without_blocking_an_existing_comment_upgrade():
    sql = _sql()
    assert "v_daily_count >= 3" in sql
    assert "v_cap_reached := true" in sql
    assert "elsif v_existing.amount < p_target_amount" in sql
    assert "v_delta := 3 - v_existing.amount" in sql
    assert "feedback xp must use reconcile_feedback_xp" in sql


def test_regenerated_plans_share_stable_phase_and_camp_reward_scope():
    sql = _sql()
    assert "xp_plan_reward_scope" in sql
    assert "'phase-completed:' || p_athlete_id::text || ':' || v_scope" in sql
    assert "'camp-completed:' || p_athlete_id::text || ':' || v_scope" in sql
    assert "camp milestone requires a dated fight camp" in sql
    assert "plan is not eligible for new progress milestones" in sql


def test_timezone_hopping_cannot_move_the_xp_training_day_repeatedly():
    sql = _sql()
    assert "athlete_timezone_updated_at" in sql
    assert "athlete_timezone must be a valid iana timezone" in sql
    assert "athlete_timezone cannot be cleared after it is set" in sql
    assert "athlete_timezone can only be changed once every 24 hours" in sql
    assert "athlete_timezone cannot change within 12 hours of training or xp activity" in sql
    assert "from public.xp_awards as award" in sql
    assert "from public.session_completions as completion" in sql
    assert "from public.today_checkins as checkin" in sql
    assert "profiles_validate_athlete_timezone_update" in sql


def test_dormant_reward_types_are_rejected_until_live_hooks_exist():
    sql = _sql()
    assert "recommended_fighter_content_watched" in sql
    assert "stop_decision_followed" in sql
    assert "xp action has no live authoritative earning hook" in sql


def test_hardening_readiness_rpc_requires_indexes_and_all_source_guards():
    sql = _sql()
    assert "validate_xp_abuse_hardening" in sql
    assert "xp_awards_one_time_action_per_athlete" in sql
    assert "xp_awards_one_daily_action_per_athlete" in sql
    assert "column_name = 'source_plan_id'" in sql
    assert "xp_awards_source_integrity" in sql
    assert "xp_awards_plan_lock_and_week_completion" in sql
    assert "xp_awards_source_plan_immutable" in sql
    assert "profiles_validate_athlete_timezone_update" in sql
    assert "'version', '20260803182000'" in sql
    assert "xp abuse hardening is incomplete" in sql


def test_all_xp_mutation_and_validation_rpcs_are_service_role_only():
    sql = _sql()
    for signature in (
        "public.award_athlete_xp(uuid, text, text, date)",
        "public.reconcile_feedback_xp(uuid, uuid, integer)",
        "public.record_plan_milestone(uuid, uuid, text, text, text, jsonb)",
        "public.prevent_xp_source_plan_rewrite()",
        "public.validate_xp_abuse_hardening()",
    ):
        assert f"revoke all on function {signature} from public, anon, authenticated" in sql
        assert f"grant execute on function {signature} to service_role" in sql


def test_today_route_gates_plan_rewards_and_does_not_loop_injury_awards():
    source = TODAY_ROUTE.read_text(encoding="utf-8")
    assert "if plan_completion_xp_eligible(" in source
    assert "updated_injuries=request_body.injuries" in source
    assert "for injury in result.get(\"open_injuries\"" not in source
