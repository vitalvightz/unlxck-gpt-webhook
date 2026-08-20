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
    NOTIFICATION_MAX_ATTEMPTS,
    NotificationCandidate,
    finalize_notification_delivery,
    invalidate_notification_action,
    list_notification_evaluations,
    list_recent_notification_deliveries,
    prepare_notification_delivery,
    record_notification_evaluation,
    simulate_notification_delivery_decision,
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
        active_plan_id="plan-1",
    )
    assert len(rehydrated) == 1
    assert rehydrated[0].intent == "plan_ready"
    assert rehydrated[0].expires_at == expires_at
    assert rehydrated[0].training_day == "2026-08-10"


def test_selected_deferred_event_is_not_rebuilt_on_later_sweeps() -> None:
    store = OrchestrationStore()
    quiet_time = datetime(2026, 8, 9, 23, 0, tzinfo=timezone.utc)
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
            "expires_at": quiet_time + timedelta(days=7),
            "source_event_metadata": {"plan_id": "plan-1"},
        }
    )
    assert prepare_notification_delivery(store, [candidate], now_utc=quiet_time) is None
    due_time = datetime(2026, 8, 10, 7, 1, tzinfo=timezone.utc)
    rehydrated = _deferred_event_candidates(
        store,
        profile_id="athlete-1",
        training_day="2026-08-10",
        timezone_name="UTC",
        now_utc=due_time,
        active_plan_id="plan-1",
    )
    assert (
        simulate_notification_delivery_decision(store, rehydrated, now_utc=due_time)
        == rehydrated[0]
    )

    for sweep in range(1, 21):
        assert (
            _deferred_event_candidates(
                store,
                profile_id="athlete-1",
                training_day="2026-08-10",
                timezone_name="UTC",
                now_utc=due_time + timedelta(minutes=10 * sweep),
                observe_mode=True,
                active_plan_id="plan-1",
            )
            == []
        )

    # Observe owns only a shadow lifecycle. Switching to send must expose the
    # original deferred source for one real claim.
    send_candidates = _deferred_event_candidates(
        store,
        profile_id="athlete-1",
        training_day="2026-08-10",
        timezone_name="UTC",
        now_utc=due_time + timedelta(hours=4),
        observe_mode=False,
        active_plan_id="plan-1",
    )
    assert [candidate.dedupe_key for candidate in send_candidates] == [
        "plan-ready:plan-1"
    ]

    rows = list_notification_evaluations(
        store,
        profile_id="athlete-1",
        training_day="2026-08-10",
        intent="plan_ready",
    )
    assert sum(int(row["evaluation_count"]) for row in rows) == 1
    assert list_recent_notification_deliveries(store, profile_id="athlete-1") == []


def test_successful_deferred_send_and_superseded_plan_are_terminal() -> None:
    store = OrchestrationStore()
    quiet_time = datetime(2026, 8, 9, 23, 0, tzinfo=timezone.utc)
    candidate = NotificationCandidate(
        **{
            **_foundation_candidate(
                key="plan-ready:plan-1", at=quiet_time, notification_class="event"
            ).__dict__,
            "notification_type": "plan_ready",
            "intent": "plan_ready",
            "category": "plan_update_alerts",
            "expires_at": quiet_time + timedelta(days=7),
            "source_event_metadata": {"plan_id": "plan-1"},
        }
    )
    assert prepare_notification_delivery(store, [candidate], now_utc=quiet_time) is None
    due_time = datetime(2026, 8, 10, 7, 1, tzinfo=timezone.utc)
    assert _deferred_event_candidates(
        store,
        profile_id="athlete-1",
        training_day="2026-08-10",
        timezone_name="UTC",
        now_utc=due_time,
        active_plan_id="plan-2",
    ) == []
    assert _deferred_event_candidates(
        store,
        profile_id="athlete-1",
        training_day="2026-08-10",
        timezone_name="UTC",
        now_utc=due_time,
        active_plan_id="",
    ) == []

    eligible = _deferred_event_candidates(
        store,
        profile_id="athlete-1",
        training_day="2026-08-10",
        timezone_name="UTC",
        now_utc=due_time,
        active_plan_id="plan-1",
    )
    selected = prepare_notification_delivery(store, eligible, now_utc=due_time)
    assert selected is not None
    finalize_notification_delivery(store, selected[1], status="sent", delivered_count=1)
    assert _deferred_event_candidates(
        store,
        profile_id="athlete-1",
        training_day="2026-08-10",
        timezone_name="UTC",
        now_utc=due_time + timedelta(minutes=10),
        active_plan_id="plan-1",
    ) == []


def test_unchanged_diagnostics_are_throttled_but_state_changes_persist() -> None:
    store = OrchestrationStore()
    view = _view(injuries=[])
    start = datetime(2026, 8, 9, 9, 0, tzinfo=timezone.utc)
    build_fight_camp_candidates(
        store, view, profile_id="athlete-1", timezone_name="UTC", now_utc=start
    )
    build_fight_camp_candidates(
        store,
        view,
        profile_id="athlete-1",
        timezone_name="UTC",
        now_utc=start + timedelta(minutes=10),
    )
    rows = list_notification_evaluations(
        store,
        profile_id="athlete-1",
        training_day="2026-08-09",
        intent="injury_recheck",
    )
    assert rows[0]["evaluation_count"] == 1

    actionable = _view(
        injuries=[{
            "id": "injury-new",
            "status": "open",
            "severity": "severe",
            "updated_at": "2026-08-08T12:00:00+00:00",
        }]
    )
    candidates = build_fight_camp_candidates(
        store,
        actionable,
        profile_id="athlete-1",
        timezone_name="UTC",
        now_utc=start + timedelta(minutes=20),
    )
    assert any(candidate.intent == "injury_recheck" for candidate in candidates)


def test_deferred_event_keeps_failed_and_stale_pending_retries() -> None:
    store = OrchestrationStore()
    quiet_time = datetime(2026, 8, 9, 23, 0, tzinfo=timezone.utc)
    candidate = NotificationCandidate(
        **{
            **_foundation_candidate(
                key="plan-ready:retryable",
                at=quiet_time,
                notification_class="event",
            ).__dict__,
            "notification_type": "plan_ready",
            "intent": "plan_ready",
            "category": "plan_update_alerts",
            "expires_at": quiet_time + timedelta(days=7),
        }
    )
    assert prepare_notification_delivery(store, [candidate], now_utc=quiet_time) is None
    claim = prepare_notification_delivery(
        store,
        [candidate],
        now_utc=datetime(2026, 8, 10, 7, 0, tzinfo=timezone.utc),
    )
    assert claim is not None
    finalize_notification_delivery(store, claim[1], status="failed", delivered_count=0)

    retry_time = datetime(2026, 8, 10, 7, 1, tzinfo=timezone.utc)
    assert (
        len(
            _deferred_event_candidates(
                store,
                profile_id="athlete-1",
                training_day="2026-08-10",
                timezone_name="UTC",
                now_utc=retry_time,
            )
        )
        == 1
    )
    retry_claim = prepare_notification_delivery(store, [candidate], now_utc=retry_time)
    assert retry_claim is not None
    assert (
        _deferred_event_candidates(
            store,
            profile_id="athlete-1",
            training_day="2026-08-10",
            timezone_name="UTC",
            now_utc=retry_time + timedelta(minutes=14),
        )
        == []
    )
    assert (
        len(
            _deferred_event_candidates(
                store,
                profile_id="athlete-1",
                training_day="2026-08-10",
                timezone_name="UTC",
                now_utc=retry_time + timedelta(minutes=15),
            )
        )
        == 1
    )


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
    assert rows[0]["decision"] == "would_select"


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
    assert rows[0]["decision"] == "would_select"


def test_observe_simulation_applies_dedupe_and_falls_through_without_claiming() -> None:
    store = OrchestrationStore()
    now = datetime(2026, 8, 9, 8, 0, tzinfo=timezone.utc)
    duplicate = _foundation_candidate(key="duplicate", at=now, priority=10)
    lower = _foundation_candidate(key="lower", at=now, priority=20)
    prepared = prepare_notification_delivery(store, [duplicate], now_utc=now - timedelta(minutes=31))
    assert prepared is not None
    finalize_notification_delivery(store, prepared[1], status="sent", delivered_count=1)
    before = list_recent_notification_deliveries(store, profile_id="athlete-1")

    result = simulate_notification_delivery_decision(store, [duplicate, lower], now_utc=now)

    assert result == lower
    assert list_recent_notification_deliveries(store, profile_id="athlete-1") == before
    duplicate_rows = list_notification_evaluations(
        store, profile_id="athlete-1", training_day="2026-08-09", intent="duplicate"
    )
    lower_rows = list_notification_evaluations(
        store, profile_id="athlete-1", training_day="2026-08-09", intent="lower"
    )
    assert duplicate_rows[0]["decision"] == "would_reject"
    assert duplicate_rows[0]["rejection_reasons"] == ["duplicate_dedupe_key"]
    assert lower_rows[0]["decision"] == "would_select"


def test_observe_simulation_records_lower_candidate_arbitration() -> None:
    store = OrchestrationStore()
    now = datetime(2026, 8, 9, 8, 0, tzinfo=timezone.utc)
    highest = _foundation_candidate(key="highest", at=now, priority=10)
    lower = _foundation_candidate(key="lower-arbitrated", at=now, priority=20)

    result = simulate_notification_delivery_decision(store, [lower, highest], now_utc=now)

    assert result == highest
    rows = list_notification_evaluations(
        store, profile_id="athlete-1", training_day="2026-08-09", intent="lower-arbitrated"
    )
    assert rows[0]["decision"] == "would_not_select"
    assert rows[0]["rejection_reasons"] == ["higher_priority_selected"]


def test_repeated_observe_sweep_uses_shadow_dedupe_without_real_delivery() -> None:
    store = OrchestrationStore()
    now = datetime(2026, 8, 9, 8, 0, tzinfo=timezone.utc)
    candidate = _foundation_candidate(key="repeat-event", at=now)

    first = simulate_notification_delivery_decision(store, [candidate], now_utc=now)
    second = simulate_notification_delivery_decision(
        store, [candidate], now_utc=now + timedelta(minutes=1)
    )

    assert first == candidate
    assert second is None
    assert list_recent_notification_deliveries(store, profile_id="athlete-1") == []
    rows = list_notification_evaluations(
        store, profile_id="athlete-1", training_day="2026-08-09", intent="repeat-event"
    )
    assert {row["decision"] for row in rows} == {"would_select", "would_reject"}
    rejected = next(row for row in rows if row["decision"] == "would_reject")
    assert rejected["rejection_reasons"] == ["duplicate_dedupe_key"]


def test_observe_shadow_claim_retries_when_stale_without_assuming_delivery_success() -> None:
    store = OrchestrationStore()
    now = datetime(2026, 8, 9, 8, 0, tzinfo=timezone.utc)
    candidate = _foundation_candidate(key="retry-shadow", at=now)

    first = simulate_notification_delivery_decision(store, [candidate], now_utc=now)
    retry = simulate_notification_delivery_decision(
        store, [candidate], now_utc=now + timedelta(minutes=16)
    )

    assert first == candidate
    assert retry == candidate
    assert list_recent_notification_deliveries(store, profile_id="athlete-1") == []
    rows = list_notification_evaluations(
        store, profile_id="athlete-1", training_day="2026-08-09", intent="retry-shadow"
    )
    selected = next(row for row in rows if row["decision"] == "would_select")
    assert selected["evaluation_count"] == 2


def test_observe_simulation_allows_retryable_failed_real_delivery() -> None:
    store = OrchestrationStore()
    now = datetime(2026, 8, 9, 8, 0, tzinfo=timezone.utc)
    candidate = _foundation_candidate(key="failed-real-delivery", at=now)
    prepared = prepare_notification_delivery(store, [candidate], now_utc=now - timedelta(minutes=1))
    assert prepared is not None
    finalize_notification_delivery(store, prepared[1], status="failed", delivered_count=0)

    result = simulate_notification_delivery_decision(store, [candidate], now_utc=now)

    assert result == candidate
    deliveries = list_recent_notification_deliveries(store, profile_id="athlete-1")
    assert len(deliveries) == 1
    assert deliveries[0]["status"] == "failed"
    assert deliveries[0]["attempt_count"] == 1


def test_observe_simulation_respects_completed_action_without_mutation() -> None:
    store = OrchestrationStore()
    now = datetime(2026, 8, 9, 8, 0, tzinfo=timezone.utc)
    candidate = NotificationCandidate(
        **{
            **_foundation_candidate(key="done-action", at=now).__dict__,
            "action_key": "morning-checkin",
        }
    )
    invalidate_notification_action(
        store,
        profile_id="athlete-1",
        action_key="morning-checkin",
        training_day="2026-08-09",
        completed_at=now,
    )

    result = simulate_notification_delivery_decision(store, [candidate], now_utc=now)

    assert result is None
    assert list_recent_notification_deliveries(store, profile_id="athlete-1") == []
    rows = list_notification_evaluations(
        store, profile_id="athlete-1", training_day="2026-08-09", intent="done-action"
    )
    assert rows[0]["rejection_reasons"] == ["user_action_already_done"]


# --- Deferred plan-ready lifecycle -------------------------------------------
# Regression coverage for the live failure on
# plan-ready:113de307-84fa-451d-a907-4ed7029c89c1, where an observe selection
# from 2026-08-16 stayed invisible to a two-day evaluation lookup while the
# deferred source kept renewing itself into every later training day.

PLAN_READY_DEDUPE = "plan-ready:plan-1"


def _plan_ready_candidate(
    at: datetime,
    *,
    plan_id: str = "plan-1",
    training_day: str = "2026-08-09",
    expires_at: datetime | None = None,
) -> NotificationCandidate:
    return NotificationCandidate(
        profile_id="athlete-1",
        notification_type="plan_ready",
        intent="plan_ready",
        category="plan_update_alerts",
        priority=40,
        title="YOUR CAMP IS LXCKED IN.",
        body="Your final camp is live. Open it and see the full build.",
        url=f"/plans/{plan_id}",
        tag="plan-ready",
        dedupe_key=f"plan-ready:{plan_id}",
        expires_at=expires_at or (at + timedelta(days=7)),
        timezone_name="UTC",
        respect_quiet_hours=True,
        training_day=training_day,
        notification_class="event",
        daily_cap=3,
        min_spacing_minutes=30,
        action_key=f"view-plan:{plan_id}",
        source_event_metadata={"plan_id": plan_id, "event": "plan_published"},
    )


def _record_deferred_source(
    store: OrchestrationStore,
    candidate: NotificationCandidate,
    *,
    training_day: str,
    at: datetime,
) -> None:
    """Persist a quiet-hour deferral exactly as the send path records one."""

    record_notification_evaluation(
        store,
        profile_id=candidate.profile_id,
        training_day=training_day,
        intent=candidate.intent,
        now_utc=at,
        decision="deferred_until_quiet_end",
        rejection_reasons=("quiet_hours",),
        eligible=False,
        candidate=candidate,
    )


def test_observe_selection_older_than_the_evaluation_window_still_blocks_rehydration() -> None:
    store = OrchestrationStore()
    published = datetime(2026, 8, 9, 23, 0, tzinfo=timezone.utc)
    candidate = _plan_ready_candidate(published)
    assert prepare_notification_delivery(store, [candidate], now_utc=published) is None

    selected_at = datetime(2026, 8, 10, 7, 1, tzinfo=timezone.utc)
    rehydrated = _deferred_event_candidates(
        store,
        profile_id="athlete-1",
        training_day="2026-08-10",
        timezone_name="UTC",
        now_utc=selected_at,
        observe_mode=True,
        active_plan_id="plan-1",
    )
    assert simulate_notification_delivery_decision(
        store, rehydrated, now_utc=selected_at
    ) == rehydrated[0]

    # A live deferred source inside the two-day window four days later. The
    # only thing that can stop it is a durable lookup of the 08-10 selection.
    later = datetime(2026, 8, 14, 23, 30, tzinfo=timezone.utc)
    _record_deferred_source(
        store, candidate, training_day="2026-08-13", at=later - timedelta(hours=2)
    )
    assert (
        _deferred_event_candidates(
            store,
            profile_id="athlete-1",
            training_day="2026-08-14",
            timezone_name="UTC",
            now_utc=later,
            observe_mode=True,
            active_plan_id="plan-1",
        )
        == []
    )


def test_stale_observe_selection_never_consumes_real_send_eligibility() -> None:
    store = OrchestrationStore()
    published = datetime(2026, 8, 9, 23, 0, tzinfo=timezone.utc)
    candidate = _plan_ready_candidate(published)
    assert prepare_notification_delivery(store, [candidate], now_utc=published) is None

    selected_at = datetime(2026, 8, 10, 7, 1, tzinfo=timezone.utc)
    observed = _deferred_event_candidates(
        store,
        profile_id="athlete-1",
        training_day="2026-08-10",
        timezone_name="UTC",
        now_utc=selected_at,
        observe_mode=True,
        active_plan_id="plan-1",
    )
    assert simulate_notification_delivery_decision(store, observed, now_utc=selected_at)
    assert list_recent_notification_deliveries(store, profile_id="athlete-1") == []

    send_at = datetime(2026, 8, 14, 8, 0, tzinfo=timezone.utc)
    _record_deferred_source(
        store, candidate, training_day="2026-08-13", at=send_at - timedelta(hours=8)
    )
    sendable = _deferred_event_candidates(
        store,
        profile_id="athlete-1",
        training_day="2026-08-14",
        timezone_name="UTC",
        now_utc=send_at,
        observe_mode=False,
        active_plan_id="plan-1",
    )
    assert [item.dedupe_key for item in sendable] == [PLAN_READY_DEDUPE]
    claim = prepare_notification_delivery(store, sendable, now_utc=send_at)
    assert claim is not None
    finalize_notification_delivery(store, claim[1], status="sent", delivered_count=1)

    assert (
        _deferred_event_candidates(
            store,
            profile_id="athlete-1",
            training_day="2026-08-14",
            timezone_name="UTC",
            now_utc=send_at + timedelta(minutes=10),
            observe_mode=False,
            active_plan_id="plan-1",
        )
        == []
    )


def test_repeated_quiet_hour_sweeps_never_mint_a_new_deferred_source() -> None:
    store = OrchestrationStore()
    published = datetime(2026, 8, 9, 23, 0, tzinfo=timezone.utc)
    original_expiry = published + timedelta(days=7)
    candidate = _plan_ready_candidate(published, expires_at=original_expiry)
    assert prepare_notification_delivery(store, [candidate], now_utc=published) is None

    identities: set[tuple[tuple[str, str], ...]] = set()
    expiries: set[datetime] = set()
    at = published + timedelta(minutes=10)
    while at < original_expiry:
        if at.hour >= 22 or at.hour < 7:  # quiet hours: always re-deferred
            rehydrated = _deferred_event_candidates(
                store,
                profile_id="athlete-1",
                training_day=at.date().isoformat(),
                timezone_name="UTC",
                now_utc=at,
                observe_mode=False,
                active_plan_id="plan-1",
            )
            assert len(rehydrated) <= 1, "a deferred copy became a second source"
            for item in rehydrated:
                source = item.source_event_metadata["_deferred_source"]
                identities.add(tuple(sorted(source.items())))
                expiries.add(item.expires_at)
            if rehydrated:
                assert prepare_notification_delivery(store, rehydrated, now_utc=at) is None
        at += timedelta(minutes=10)

    assert len(identities) == 1, f"deferred source identity advanced: {identities}"
    assert dict(next(iter(identities)))["training_day"] == "2026-08-09"
    assert expiries == {original_expiry}, "rehydration must not extend the original TTL"

    day = published.date()
    while day <= original_expiry.date():
        rows = [
            row
            for row in list_notification_evaluations(
                store,
                profile_id="athlete-1",
                training_day=day.isoformat(),
                intent="plan_ready",
            )
            if row["decision"] == "deferred_until_quiet_end"
        ]
        # The origin day also holds the authoritative source row itself.
        assert len(rows) <= (2 if day == published.date() else 1), (day, rows)
        day += timedelta(days=1)

    assert (
        _deferred_event_candidates(
            store,
            profile_id="athlete-1",
            training_day=original_expiry.date().isoformat(),
            timezone_name="UTC",
            now_utc=original_expiry + timedelta(minutes=1),
            observe_mode=False,
            active_plan_id="plan-1",
        )
        == []
    ), "an expired lifecycle must not survive"


def test_exhausted_delivery_retries_end_the_deferred_lifecycle() -> None:
    store = OrchestrationStore()
    published = datetime(2026, 8, 9, 23, 0, tzinfo=timezone.utc)
    candidate = _plan_ready_candidate(published)
    assert prepare_notification_delivery(store, [candidate], now_utc=published) is None

    at = datetime(2026, 8, 10, 7, 1, tzinfo=timezone.utc)
    for attempt in range(NOTIFICATION_MAX_ATTEMPTS):
        pending = _deferred_event_candidates(
            store,
            profile_id="athlete-1",
            training_day="2026-08-10",
            timezone_name="UTC",
            now_utc=at,
            active_plan_id="plan-1",
        )
        assert len(pending) == 1, f"attempt {attempt} lost its retry"
        claim = prepare_notification_delivery(store, pending, now_utc=at)
        assert claim is not None
        finalize_notification_delivery(store, claim[1], status="failed", delivered_count=0)
        at += timedelta(minutes=20)

    assert (
        _deferred_event_candidates(
            store,
            profile_id="athlete-1",
            training_day="2026-08-10",
            timezone_name="UTC",
            now_utc=at,
            active_plan_id="plan-1",
        )
        == []
    )


def test_repeated_duplicate_arbitration_is_throttled_until_the_decision_changes() -> None:
    store = OrchestrationStore()
    sent_at = datetime(2026, 8, 10, 8, 0, tzinfo=timezone.utc)
    candidate = _plan_ready_candidate(sent_at, training_day="2026-08-10")
    claim = prepare_notification_delivery(store, [candidate], now_utc=sent_at)
    assert claim is not None
    finalize_notification_delivery(store, claim[1], status="sent", delivered_count=1)

    def duplicate_rows() -> list[dict]:
        return [
            row
            for row in list_notification_evaluations(
                store,
                profile_id="athlete-1",
                training_day="2026-08-10",
                intent="plan_ready",
            )
            if row["rejection_reasons"] == ["duplicate_dedupe_key"]
        ]

    for minutes in (10, 20, 60, 5 * 60):
        assert (
            simulate_notification_delivery_decision(
                store, [candidate], now_utc=sent_at + timedelta(minutes=minutes)
            )
            is None
        )
    assert [row["evaluation_count"] for row in duplicate_rows()] == [1]

    # Six hours after the row was last written, not after the send.
    simulate_notification_delivery_decision(
        store, [candidate], now_utc=sent_at + timedelta(minutes=10 + 361)
    )
    assert [row["evaluation_count"] for row in duplicate_rows()] == [2]

    # A changed arbitration outcome is a different fact and is never throttled.
    changed_at = sent_at + timedelta(minutes=10 + 371)
    winner = _foundation_candidate(
        key="session-stop:2026-08-10", at=changed_at, priority=5, notification_class="safety"
    )
    assert (
        simulate_notification_delivery_decision(
            store, [candidate, winner], now_utc=changed_at
        )
        == winner
    )
    losing = [
        row
        for row in list_notification_evaluations(
            store,
            profile_id="athlete-1",
            training_day="2026-08-10",
            intent="plan_ready",
        )
        if row["rejection_reasons"] == ["higher_priority_selected"]
    ]
    assert [row["evaluation_count"] for row in losing] == [1]
    assert [row["evaluation_count"] for row in duplicate_rows()] == [2]


def test_safety_intents_keep_evaluating_on_every_sweep() -> None:
    store = OrchestrationStore()
    start = datetime(2026, 8, 9, 12, 0, tzinfo=timezone.utc)
    stop_view = _view(decision_tier="stop", recommendation_state="pull_back")
    for sweep in range(4):
        intents = {
            candidate.intent
            for candidate in build_fight_camp_candidates(
                store,
                stop_view,
                profile_id="athlete-1",
                timezone_name="UTC",
                now_utc=start + timedelta(minutes=10 * sweep),
            )
        }
        assert "session_stop" in intents, f"sweep {sweep} stopped evaluating safety"

    modified = {
        candidate.intent
        for candidate in build_fight_camp_candidates(
            store,
            _view(recommendation_state="modify", decision_tier="modify"),
            profile_id="athlete-1",
            timezone_name="UTC",
            now_utc=start + timedelta(minutes=50),
        )
    }
    assert "session_modified" in modified

    injured = {
        candidate.intent
        for candidate in build_fight_camp_candidates(
            store,
            _view(injuries=[{
                "id": "injury-1",
                "status": "open",
                "severity": "severe",
                "updated_at": "2026-08-08T12:00:00+00:00",
            }]),
            profile_id="athlete-1",
            timezone_name="UTC",
            now_utc=start + timedelta(minutes=60),
        )
    }
    assert "injury_recheck" in injured


def test_current_active_plan_matching_the_source_never_suppresses_by_itself() -> None:
    store = OrchestrationStore()
    published = datetime(2026, 8, 9, 23, 0, tzinfo=timezone.utc)
    candidate = _plan_ready_candidate(published)
    assert prepare_notification_delivery(store, [candidate], now_utc=published) is None

    rehydrated = _deferred_event_candidates(
        store,
        profile_id="athlete-1",
        training_day="2026-08-10",
        timezone_name="UTC",
        now_utc=datetime(2026, 8, 10, 7, 1, tzinfo=timezone.utc),
        observe_mode=True,
        active_plan_id="plan-1",
    )
    assert [item.dedupe_key for item in rehydrated] == [PLAN_READY_DEDUPE]
    assert rehydrated[0].source_event_metadata["plan_id"] == "plan-1"
