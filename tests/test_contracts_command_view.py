"""Tests for the normalized command-view builder + risk watch (Block 4 §6, §7)."""

from api.contracts.command_view import (
    build_command_view,
    make_risk,
    sort_risk_watch,
    visible_risk_watch,
)

TODAY = "2026-06-18"
PLAN = {"id": "plan-1", "name": "Camp A", "phase": "SPP"}
READINESS_REASON = "\n".join(
    [
        "Session reduced.",
        "Poor sleep means your body has less room to recover today.",
        "Cut 1 round and do not add extra conditioning.",
    ]
)


def _rec(training_day=TODAY, decision="modify", reason=READINESS_REASON):
    return {"training_day": training_day, "decision": decision, "reason": reason}


class TestEmptyState:
    def test_no_active_plan_yields_empty_state_with_intake_cta(self):
        view = build_command_view(current_training_day=TODAY, plan=None)
        assert view.active_plan == {}
        assert view.today.recommendation_state == "not_checked_in"
        assert view.today.completion_status == "not_started"
        assert [a.id for a in view.quick_actions] == ["complete_intake"]
        assert view.quick_actions[0].route == "/intake"

    def test_empty_plan_mapping_is_treated_as_no_plan(self):
        view = build_command_view(current_training_day=TODAY, plan={})
        assert view.active_plan == {}
        assert [a.id for a in view.quick_actions] == ["complete_intake"]


class TestRecommendationMirror:
    def test_active_plan_no_checkin_is_not_checked_in(self):
        view = build_command_view(current_training_day=TODAY, plan=PLAN, recommendation=None)
        assert view.active_plan.get("id") == "plan-1"
        assert view.today.recommendation_state == "not_checked_in"
        assert view.today.recommendation_reason is None
        assert {a.id for a in view.quick_actions} == {"open_today", "view_plan"}

    def test_active_plan_accepts_persisted_plan_field_names(self):
        view = build_command_view(
            current_training_day=TODAY,
            plan={"plan_id": "plan-2", "plan_name": "Fight camp", "status": "ready"},
            recommendation=None,
        )
        assert view.active_plan.get("id") == "plan-2"
        assert view.active_plan.get("name") == "Fight camp"
        assert {a.id for a in view.quick_actions} == {"open_today", "view_plan"}
        assert any(a.route == "/plans/plan-2" for a in view.quick_actions)

    def test_valid_recommendation_is_mirrored(self):
        view = build_command_view(
            current_training_day=TODAY, plan=PLAN, recommendation=_rec(decision="pull_back")
        )
        assert view.today.recommendation_state == "pull_back"
        assert view.today.recommendation_reason == READINESS_REASON

    def test_expired_recommendation_returns_not_checked_in(self):
        view = build_command_view(
            current_training_day=TODAY, plan=PLAN, recommendation=_rec(training_day="2026-06-17")
        )
        assert view.today.recommendation_state == "not_checked_in"
        assert view.today.recommendation_reason is None


class TestCompletionStatus:
    def test_started_completion_surfaces_started(self):
        view = build_command_view(
            current_training_day=TODAY, plan=PLAN, completion={"status": "started"}
        )
        assert view.today.completion_status == "started"

    def test_terminal_completions_surface_status(self):
        for status in ("done", "modified", "skipped"):
            view = build_command_view(
                current_training_day=TODAY, plan=PLAN, completion={"status": status}
            )
            assert view.today.completion_status == status


class TestGracefulDegradation:
    def test_missing_structured_plan_session_does_not_crash(self):
        view = build_command_view(
            current_training_day=TODAY, plan=PLAN, next_session=None, week_summary=None
        )
        assert view.today.next_session == {}
        assert view.week_summary == {}

    def test_next_session_passthrough(self):
        view = build_command_view(
            current_training_day=TODAY, plan=PLAN, next_session={"weekday": "Thu", "load": "hard"}
        )
        assert view.today.next_session == {"weekday": "Thu", "load": "hard"}
        assert view.today.session_scope == "next"
        assert view.today.session_label == "Next session"

    def test_today_session_label_when_scoped_to_today(self):
        view = build_command_view(
            current_training_day=TODAY,
            plan=PLAN,
            next_session={"weekday": "Thu", "load": "hard"},
            session_scope="today",
        )
        assert view.today.session_scope == "today"
        assert view.today.session_label == "Today's session"


class TestRiskWatch:
    def test_risk_watch_is_sorted_by_priority(self):
        risks = [
            make_risk("fatigue", text="Poor sleep streak"),
            make_risk("stop_red_flag", text="Stop"),
            make_risk("high_pain", text="High pain"),
        ]
        view = build_command_view(current_training_day=TODAY, plan=PLAN, risks=risks)
        categories = [item.category for item in view.risk_watch]
        assert categories == ["stop_red_flag", "high_pain", "fatigue"]

    def test_visible_risk_watch_limits_to_two_plus_overflow(self):
        ordered = sort_risk_watch(
            [
                make_risk("stop_red_flag"),
                make_risk("active_injury_worse"),
                make_risk("high_pain"),
                make_risk("fatigue"),
            ]
        )
        visible, overflow = visible_risk_watch(ordered)
        assert [v.category for v in visible] == ["stop_red_flag", "active_injury_worse"]
        assert overflow == 2

    def test_risk_items_carry_icon_label_text_and_tone(self):
        item = make_risk("high_pain", text="Pain is high")
        assert item.icon and item.label and item.tone
        assert item.text == "Pain is high"

    def test_mapping_risks_are_coerced(self):
        view = build_command_view(
            current_training_day=TODAY,
            plan=PLAN,
            risks=[{"category": "weight_cut", "text": "5% to cut"}],
        )
        assert view.risk_watch[0].category == "weight_cut"
        assert view.risk_watch[0].text == "5% to cut"


class TestShape:
    def test_view_serializes_to_documented_shape(self):
        view = build_command_view(current_training_day=TODAY, plan=PLAN)
        dumped = view.model_dump()
        assert set(dumped) == {
            "active_plan",
            "today",
            "risk_watch",
            "open_injuries",
            "week_summary",
            "quick_actions",
        }
        assert set(dumped["today"]) == {
            "training_day",
            "recommendation_state",
            "recommendation_reason",
            "warnings",
            "next_session",
            "session_scope",
            "session_label",
            "completion_status",
        }
        assert dumped["today"]["training_day"] == TODAY
