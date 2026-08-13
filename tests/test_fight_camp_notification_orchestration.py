from __future__ import annotations

from datetime import datetime, timedelta, timezone

from api.contracts.command_view import CommandView
from api.services import fight_camp_notifications
from api.services.fight_camp_notifications import (
    _deferred_event_candidates,
    build_fight_camp_candidates,
    dispatch_fight_camp_notifications,
)
from api.services.notification_foundation import (
    NotificationCandidate,
    finalize_notification_delivery,
    invalidate_notification_action,
    list_notification_evaluations,
    prepare_notification_delivery,
    update_notification_preferences,
)
from api.services.notification_templates import BUNDLED_TEMPLATES, select_notification_template


class OrchestrationStore:
    def __init__(self) -> None:
        self.completions: list[dict] = []
        self.current_completion: dict | None = None

    def list_session_completions(self, _profile_id: str, *, limit: int = 60) -> list[dict]:
        return [dict(row) for row in self.completions[:limit]]

    def get_session_completion(self, *_args) -> dict | None:
        return dict(self.current_completion) if self.current_completion else None

    def get_plan(self, _plan_id: str) -> dict | None:
        return None


def _view(
    *,
    recommendation_state: str = "train_as_planned",
    decision_tier: str = "green",
    completion_status: str = "not_started",
    session_scope: str = "today",
    injuries: list[dict] | None = None,
) -> CommandView:
    return CommandView.model_validate(
        {
            "active_plan": {"id": "plan-1", "fight_date": "2026-08-16"},
            "today": {
                "training_day": "2026-08-09",
                "recommendation_state": recommendation_state,
                "decision_tier": decision_tier,
                "session_scope": session_scope,
                "completion_status": completion_status,
                "next_session": {
                    "session_id": "session-1",
                    "session_type": "strength",
                    "title": "Power and strength",
                }
                if session_scope == "today"
                else {},
            },
            "open_injuries": injuries or [],
        }
    )


def _types(store: OrchestrationStore, view: CommandView, at: datetime) -> set[str]:
    return {
        candidate.intent
        for candidate in build_fight_camp_candidates(
            store,
            view,
            profile_id="athlete-1",
            timezone_name="UTC",
            now_utc=at,
        )
    }


def test_stop_replaces_normal_session_and_briefing_notifications() -> None:
    store = OrchestrationStore()
    types = _types(
        store,
        _view(decision_tier="stop", recommendation_state="pull_back"),
        datetime(2026, 8, 9, 12, 0, tzinfo=timezone.utc),
    )
    assert "session_stop" in types
    assert not ({"daily_camp_briefing", "session_preparation", "session_near", "session_ready"} & types)
    evaluations = list_notification_evaluations(
        store,
        profile_id="athlete-1",
        training_day="2026-08-09",
        intent="session_ready",
    )
    assert evaluations[0]["decision"] == "replaced_by_session_stop"


def test_modified_replaces_generic_session_ready() -> None:
    store = OrchestrationStore()
    types = _types(
        store,
        _view(decision_tier="modify", recommendation_state="modify"),
        datetime(2026, 8, 9, 18, 0, tzinfo=timezone.utc),
    )
    assert "session_modified" in types
    assert "session_ready" not in types


def test_injury_followup_works_after_checkin_and_on_rest_day() -> None:
    store = OrchestrationStore()
    injury = {
        "id": "injury-1",
        "body_area": "left knee",
        "status": "open",
        "severity": "severe",
        "updated_at": "2026-08-08T08:00:00+00:00",
    }
    types = _types(
        store,
        _view(session_scope="none", injuries=[injury]),
        datetime(2026, 8, 9, 14, 0, tzinfo=timezone.utc),
    )
    assert "injury_recheck" in types


def test_disabled_injury_followup_falls_back_to_morning_readiness() -> None:
    store = OrchestrationStore()
    update_notification_preferences(
        store,
        "athlete-1",
        {"injury_followups": False, "quiet_hours_enabled": False},
    )
    injury = {
        "id": "injury-1",
        "body_area": "left knee",
        "status": "open",
        "severity": "severe",
        "updated_at": "2026-08-08T08:00:00+00:00",
    }
    now = datetime(2026, 8, 9, 8, 0, tzinfo=timezone.utc)
    candidates = build_fight_camp_candidates(
        store,
        _view(recommendation_state="not_checked_in", injuries=[injury]),
        profile_id="athlete-1",
        timezone_name="UTC",
        now_utc=now,
    )

    assert {candidate.intent for candidate in candidates} >= {
        "injury_recheck",
        "morning_readiness",
    }
    selected = prepare_notification_delivery(store, candidates, now_utc=now)
    assert selected is not None
    assert selected[0].intent == "morning_readiness"


def test_enabled_injury_followup_replaces_morning_readiness() -> None:
    store = OrchestrationStore()
    injury = {
        "id": "injury-1",
        "body_area": "left knee",
        "status": "open",
        "severity": "severe",
        "updated_at": "2026-08-08T08:00:00+00:00",
    }
    candidates = build_fight_camp_candidates(
        store,
        _view(recommendation_state="not_checked_in", injuries=[injury]),
        profile_id="athlete-1",
        timezone_name="UTC",
        now_utc=datetime(2026, 8, 9, 8, 0, tzinfo=timezone.utc),
    )

    assert "injury_recheck" in {candidate.intent for candidate in candidates}
    assert "morning_readiness" not in {candidate.intent for candidate in candidates}


def test_disabled_high_pain_followup_falls_back_to_morning_readiness() -> None:
    store = OrchestrationStore()
    store.completions = [
        {
            "id": "completion-1",
            "training_day": "2026-08-08",
            "pain_after": 8,
            "completed_at": "2026-08-08T18:00:00+00:00",
        }
    ]
    update_notification_preferences(
        store,
        "athlete-1",
        {"injury_followups": False, "quiet_hours_enabled": False},
    )
    now = datetime(2026, 8, 9, 8, 0, tzinfo=timezone.utc)
    candidates = build_fight_camp_candidates(
        store,
        _view(recommendation_state="not_checked_in"),
        profile_id="athlete-1",
        timezone_name="UTC",
        now_utc=now,
    )

    assert {candidate.intent for candidate in candidates} >= {
        "high_pain_followup",
        "morning_readiness",
    }
    selected = prepare_notification_delivery(store, candidates, now_utc=now)
    assert selected is not None
    assert selected[0].intent == "morning_readiness"


def test_active_camp_rest_day_has_morning_and_afternoon_recovery_touches() -> None:
    morning_types = _types(
        OrchestrationStore(),
        _view(recommendation_state="not_checked_in", session_scope="none"),
        datetime(2026, 8, 9, 8, 0, tzinfo=timezone.utc),
    )
    afternoon_types = _types(
        OrchestrationStore(),
        _view(recommendation_state="not_checked_in", session_scope="none"),
        datetime(2026, 8, 9, 14, 0, tzinfo=timezone.utc),
    )

    assert "recovery_checkin" in morning_types
    assert "recovery_nudge" in afternoon_types


def test_post_session_reminder_does_not_require_started_state(monkeypatch) -> None:
    monkeypatch.setenv("UNLXCK_NOTIFICATION_FALLBACK_TRAINING_TIME", "18:00")
    store = OrchestrationStore()
    candidates = build_fight_camp_candidates(
        store,
        _view(),
        profile_id="athlete-1",
        timezone_name="UTC",
        now_utc=datetime(2026, 8, 9, 19, 50, tzinfo=timezone.utc),
    )
    post_session = next(
        candidate for candidate in candidates if candidate.intent == "post_session_log"
    )
    assert post_session.timing_confidence == "low"
    assert post_session.title == "TRAINED YET?"
    assert "When you're done" in post_session.body or "If training is finished" in post_session.body


def test_real_session_start_allows_completed_session_copy_with_fallback_schedule(monkeypatch) -> None:
    monkeypatch.setenv("UNLXCK_NOTIFICATION_FALLBACK_TRAINING_TIME", "18:00")
    store = OrchestrationStore()
    store.current_completion = {
        "status": "started",
        "started_at": "2026-08-09T18:15:00+00:00",
    }
    candidates = build_fight_camp_candidates(
        store,
        _view(),
        profile_id="athlete-1",
        timezone_name="UTC",
        now_utc=datetime(2026, 8, 9, 19, 50, tzinfo=timezone.utc),
    )

    post_session = next(
        candidate for candidate in candidates if candidate.intent == "post_session_log"
    )
    assert post_session.timing_confidence == "low"
    assert post_session.title != "TRAINED YET?"


def _foundation_candidate(
    *,
    key: str,
    at: datetime,
    priority: int = 20,
    notification_class: str = "routine",
    action_key: str | None = None,
) -> NotificationCandidate:
    return NotificationCandidate(
        profile_id="athlete-1",
        notification_type=key,
        intent=key,
        category="checkin_reminders",
        priority=priority,
        title="Test notification",
        body="A bounded test notification body.",
        url="/today",
        tag=key,
        dedupe_key=key,
        expires_at=at + timedelta(hours=2),
        training_day="2026-08-09",
        notification_class=notification_class,  # type: ignore[arg-type]
        min_spacing_minutes=0,
        action_key=action_key,
    )


def test_deduped_highest_priority_falls_through_to_next_candidate() -> None:
    store = OrchestrationStore()
    now = datetime(2026, 8, 9, 8, 0, tzinfo=timezone.utc)
    highest = _foundation_candidate(key="highest", at=now, priority=5)
    lower = _foundation_candidate(key="lower", at=now, priority=20)
    first = prepare_notification_delivery(store, [highest], now_utc=now)
    assert first is not None
    finalize_notification_delivery(store, first[1], status="sent", delivered_count=1)
    selected = prepare_notification_delivery(store, [highest, lower], now_utc=now + timedelta(minutes=1))
    assert selected is not None
    assert selected[0].intent == "lower"


def test_routine_cap_is_six_and_safety_uses_separate_bound() -> None:
    store = OrchestrationStore()
    start = datetime(2026, 8, 9, 8, 0, tzinfo=timezone.utc)
    for index in range(6):
        prepared = prepare_notification_delivery(
            store,
            [_foundation_candidate(key=f"routine-{index}", at=start + timedelta(hours=index))],
            now_utc=start + timedelta(hours=index),
        )
        assert prepared is not None
        finalize_notification_delivery(store, prepared[1], status="sent", delivered_count=1)
    assert prepare_notification_delivery(
        store,
        [_foundation_candidate(key="routine-7", at=start + timedelta(hours=7))],
        now_utc=start + timedelta(hours=7),
    ) is None
    safety = prepare_notification_delivery(
        store,
        [_foundation_candidate(
            key="safety-1", at=start + timedelta(hours=7), notification_class="safety"
        )],
        now_utc=start + timedelta(hours=7),
    )
    assert safety is not None


def test_action_completion_invalidates_future_reminders_immediately() -> None:
    store = OrchestrationStore()
    now = datetime(2026, 8, 9, 8, 0, tzinfo=timezone.utc)
    action_key = "checkin:2026-08-09"
    invalidate_notification_action(
        store,
        profile_id="athlete-1",
        action_key=action_key,
        training_day="2026-08-09",
        completed_at=now,
    )
    candidate = _foundation_candidate(key="checkin-after-complete", at=now, action_key=action_key)
    assert prepare_notification_delivery(store, [candidate], now_utc=now) is None
    evaluations = list_notification_evaluations(
        store,
        profile_id="athlete-1",
        training_day="2026-08-09",
        intent="checkin-after-complete",
    )
    assert evaluations[0]["rejection_reasons"] == ["user_action_already_done"]


def test_template_variant_never_repeats_consecutively() -> None:
    store = OrchestrationStore()
    now = datetime(2026, 8, 9, 8, 0, tzinfo=timezone.utc)
    first_copy = select_notification_template(
        store,
        profile_id="athlete-1",
        intent="morning_readiness",
        dedupe_key="morning-1",
    )
    candidate = _foundation_candidate(key="morning-1", at=now, notification_class="event")
    candidate = NotificationCandidate(
        **{
            **candidate.__dict__,
            "notification_type": "morning_readiness",
            "intent": "morning_readiness",
            "variant_id": first_copy[2],
        }
    )
    prepared = prepare_notification_delivery(store, [candidate], now_utc=now)
    assert prepared is not None
    finalize_notification_delivery(store, prepared[1], status="sent", delivered_count=1)
    second_copy = select_notification_template(
        store,
        profile_id="athlete-1",
        intent="morning_readiness",
        dedupe_key="morning-2",
    )
    assert second_copy[2] != first_copy[2]


def test_bundled_templates_fit_delivery_limits_with_maximum_context() -> None:
    context = {
        "session": "S" * 42,
        "body_area": "B" * 24,
        "countdown": "D-14",
        "title": "T" * 40,
        "body": "C" * 90,
    }

    for template in BUNDLED_TEMPLATES:
        assert len(template.title_template.format_map(context)) <= 40, template.variant_id
        assert len(template.body_template.format_map(context)) <= 90, template.variant_id


def test_fight_countdown_uses_unique_copy_for_each_milestone() -> None:
    store = OrchestrationStore()
    expected = {
        "D-14": ("fc-d14", "D-14. TWO WEEKS."),
        "D-7": ("fc-d07", "D-7. FIGHT WEEK."),
        "D-3": ("fc-d03", "D-3. STAY SHARP."),
        "D-1": ("fc-d01", "D-1. READY."),
    }

    for countdown, (variant_id, title) in expected.items():
        selected = select_notification_template(
            store,
            profile_id="athlete-1",
            intent="fight_countdown",
            dedupe_key=f"countdown:{countdown}",
            context={"countdown": countdown},
        )
        assert selected[2] == variant_id
        assert selected[0] == title


def test_quiet_hour_event_rehydrates_with_original_expiry() -> None:
    store = OrchestrationStore()
    quiet_time = datetime(2026, 8, 9, 23, 0, tzinfo=timezone.utc)
    expires_at = quiet_time + timedelta(hours=12)
    candidate = NotificationCandidate(
        **{
            **_foundation_candidate(
                key="plan-ready:plan-1",
                at=quiet_time,
                notification_class="event",
            ).__dict__,
            "notification_type": "plan_ready",
            "intent": "plan_ready",
            "category": "plan_update_alerts",
            "expires_at": expires_at,
            "timezone_name": "UTC",
            "source_event_metadata": {"plan_id": "plan-1"},
        }
    )
    assert prepare_notification_delivery(store, [candidate], now_utc=quiet_time) is None

    rehydrated = _deferred_event_candidates(
        store,
        profile_id="athlete-1",
        training_day="2026-08-10",
        timezone_name="UTC",
        now_utc=datetime(2026, 8, 10, 7, 1, tzinfo=timezone.utc),
    )
    assert len(rehydrated) == 1
    assert rehydrated[0].intent == "plan_ready"
    assert rehydrated[0].expires_at == expires_at
    assert rehydrated[0].training_day == "2026-08-10"


def test_observe_rollout_records_candidates_and_preserves_legacy_path(monkeypatch) -> None:
    store = OrchestrationStore()
    now = datetime(2026, 8, 9, 8, 0, tzinfo=timezone.utc)
    candidate = _foundation_candidate(key="observed-intent", at=now)
    monkeypatch.setenv("UNLXCK_FIGHT_CAMP_NOTIFICATIONS_MODE", "observe")
    monkeypatch.setattr(fight_camp_notifications, "build_today_command_view", lambda *_args, **_kwargs: _view())
    monkeypatch.setattr(
        fight_camp_notifications,
        "build_fight_camp_candidates",
        lambda *_args, **_kwargs: [candidate],
    )
    monkeypatch.setattr(
        fight_camp_notifications,
        "dispatch_push_candidates",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("observe must not send")),
    )

    result = dispatch_fight_camp_notifications(
        store,
        profile_id="athlete-1",
        timezone_name="UTC",
        now_utc=now,
    )
    assert result.candidate_count == 0
    rows = list_notification_evaluations(
        store,
        profile_id="athlete-1",
        training_day="2026-08-09",
        intent="observed-intent",
    )
    assert rows[0]["decision"] == "rollout_observe_only"


def test_missing_rollout_mode_defaults_to_observe_and_never_sends(monkeypatch) -> None:
    store = OrchestrationStore()
    now = datetime(2026, 8, 9, 8, 0, tzinfo=timezone.utc)
    candidate = _foundation_candidate(key="default-observed-intent", at=now)
    monkeypatch.delenv("UNLXCK_FIGHT_CAMP_NOTIFICATIONS_MODE", raising=False)
    monkeypatch.setattr(
        fight_camp_notifications,
        "build_today_command_view",
        lambda *_args, **_kwargs: _view(),
    )
    monkeypatch.setattr(
        fight_camp_notifications,
        "build_fight_camp_candidates",
        lambda *_args, **_kwargs: [candidate],
    )
    monkeypatch.setattr(
        fight_camp_notifications,
        "dispatch_push_candidates",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("default observe mode must not send")
        ),
    )

    result = dispatch_fight_camp_notifications(
        store,
        profile_id="athlete-1",
        timezone_name="UTC",
        now_utc=now,
    )

    assert result.candidate_count == 0
    rows = list_notification_evaluations(
        store,
        profile_id="athlete-1",
        training_day="2026-08-09",
        intent="default-observed-intent",
    )
    assert rows[0]["decision"] == "rollout_observe_only"
