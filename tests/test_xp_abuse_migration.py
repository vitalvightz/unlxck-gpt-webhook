from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "supabase" / "migrations" / "20260803174500_harden_xp_abuse_boundaries.sql"
TODAY_ROUTE = ROOT / "api" / "routes" / "today.py"


def _sql() -> str:
    return " ".join(MIGRATION.read_text(encoding="utf-8").lower().split())


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
    assert "calendar date is required for this xp action" in sql
    for action in (
        "full_training_week_completed",
        "readiness_checkin_completed",
        "injury_update_completed",
        "stop_decision_followed",
    ):
        assert f"'{action}'" in sql


def test_session_awards_require_real_terminal_completions_and_have_a_daily_cap():
    sql = _sql()
    assert "from public.session_completions" in sql
    assert "id = v_completion_id" in sql
    assert "athlete_id = p_athlete_id" in sql
    assert "training_day = p_calendar_date" in sql
    assert "status in ('done', 'modified')" in sql
    assert "v_daily_count < 2" in sql


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


def test_regenerated_fight_camps_share_phase_and_camp_reward_scope():
    sql = _sql()
    assert "v_plan_type = 'fight_camp'" in sql
    assert "camp milestone requires a dated fight camp" in sql
    assert "'phase-completed:' || p_athlete_id::text || ':' || v_fight_date::text" in sql
    assert "'camp-completed:' || p_athlete_id::text || ':' || v_fight_date::text" in sql
    assert "plan is not eligible for progress xp" in sql


def test_all_xp_mutation_rpcs_are_service_role_only():
    sql = _sql()
    for signature in (
        "public.award_athlete_xp(uuid, text, text, date)",
        "public.reconcile_feedback_xp(uuid, uuid, integer)",
        "public.record_plan_milestone(uuid, uuid, text, text, text, jsonb)",
    ):
        assert f"revoke all on function {signature} from public, anon, authenticated" in sql
        assert f"grant execute on function {signature} to service_role" in sql


def test_today_route_gates_plan_rewards_and_does_not_loop_injury_awards():
    source = TODAY_ROUTE.read_text(encoding="utf-8")
    assert "if plan_completion_xp_eligible(" in source
    assert "updated_injuries=request_body.injuries" in source
    assert "for injury in result.get(\"open_injuries\"" not in source
