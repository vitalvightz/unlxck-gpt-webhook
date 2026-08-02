from __future__ import annotations

from datetime import datetime, timezone

from api.contracts.command_view import CommandView
from api.services.intelligent_notifications import (
    _training_day_of,
    build_coaching_candidates_from_view,
)


class NotificationStateStore:
    def __init__(self) -> None:
        self.completions: list[dict] = []
        self.current_completion: dict | None = None

    def list_session_completions(self, _profile_id: str, *, limit: int = 6) -> list[dict]:
        return [dict(row) for row in self.completions[:limit]]

    def get_session_completion(
        self,
        _profile_id: str,
        _session_id: str,
        _training_day: str,
    ) -> dict | None:
        return dict(self.current_completion) if self.current_completion else None


def _view(
    *,
    active_plan: bool = True,
    recommendation_state: str = "not_checked_in",
    session_scope: str = "today",
    completion_status: str = "not_started",
    training_day: str = "2026-08-02",
    injury_hold_exempt: bool = False,
    open_injuries: list[dict] | None = None,
) -> CommandView:
    return CommandView.model_validate(
        {
            "active_plan": {"id": "plan-1"} if active_plan else {},
            "today": {
                "training_day": training_day,
                "recommendation_state": recommendation_state,
                "session_scope": session_scope,
                "completion_status": completion_status,
                "injury_hold_exempt": injury_hold_exempt,
                "next_session": {"session_id": "session-1", "title": "Sharp work"}
                if session_scope == "today"
                else {},
            },
            "open_injuries": open_injuries or [],
            "risk_watch": [],
        }
    )


def _types(store: NotificationStateStore, view: CommandView, *, at: datetime) -> list[str]:
    return [
        candidate.notification_type
        for candidate in build_coaching_candidates_from_view(
            store,
            view,
            profile_id="athlete-1",
            timezone_name="UTC",
            now_utc=at,
        )
    ]


def test_readiness_only_exists_for_an_actual_today_session():
    store = NotificationStateStore()
    morning = datetime(2026, 8, 2, 8, 0, tzinfo=timezone.utc)

    assert _types(store, _view(session_scope="today"), at=morning) == [
        "readiness_checkin"
    ]
    assert _types(store, _view(session_scope="next"), at=morning) == []
    assert _types(store, _view(session_scope="none"), at=morning) == []
    assert _types(store, _view(active_plan=False), at=morning) == []


def test_completed_checkin_or_session_suppresses_morning_nudges():
    store = NotificationStateStore()
    morning = datetime(2026, 8, 2, 8, 0, tzinfo=timezone.utc)

    assert _types(
        store,
        _view(recommendation_state="train_as_planned"),
        at=morning,
    ) == []
    assert _types(
        store,
        _view(completion_status="done"),
        at=morning,
    ) == []


def test_restricted_injury_outranks_readiness_but_same_day_update_is_silent():
    store = NotificationStateStore()
    morning = datetime(2026, 8, 2, 8, 0, tzinfo=timezone.utc)
    injury = {
        "id": "injury-1",
        "status": "open",
        "severity": "moderate",
        "surface_class": "surface_no_contact",
        "latest_reported_status": "same",
        "updated_at": "2026-08-01T08:00:00+00:00",
    }

    candidates = build_coaching_candidates_from_view(
        store,
        _view(open_injuries=[injury]),
        profile_id="athlete-1",
        timezone_name="UTC",
        now_utc=morning,
    )
    assert [candidate.notification_type for candidate in candidates] == [
        "injury_recheck",
        "readiness_checkin",
    ]
    assert candidates[0].priority < candidates[1].priority
    assert candidates[0].url == "/today#today-injury"

    injury["updated_at"] = "2026-08-02T07:30:00+00:00"
    assert _types(store, _view(open_injuries=[injury]), at=morning) == [
        "readiness_checkin"
    ]


def test_after_midnight_injury_update_uses_the_0300_training_day_boundary():
    store = NotificationStateStore()
    injury = {
        "id": "injury-1",
        "status": "open",
        "severity": "moderate",
        "surface_class": "surface_no_contact",
        "latest_reported_status": "same",
        # 01:00 on Aug 2 still belongs to the Aug 1 training day.
        "updated_at": "2026-08-02T01:00:00+00:00",
    }
    candidates = build_coaching_candidates_from_view(
        store,
        _view(open_injuries=[injury]),
        profile_id="athlete-1",
        timezone_name="UTC",
        now_utc=datetime(2026, 8, 2, 8, 0, tzinfo=timezone.utc),
    )
    assert [candidate.notification_type for candidate in candidates] == [
        "injury_recheck",
        "readiness_checkin",
    ]


def test_support_session_suppresses_load_restriction_but_not_medical_review():
    store = NotificationStateStore()
    morning = datetime(2026, 8, 2, 8, 0, tzinfo=timezone.utc)
    restricted = {
        "id": "injury-1",
        "status": "open",
        "severity": "moderate",
        "surface_class": "surface_no_contact",
        "updated_at": "2026-08-01T08:00:00+00:00",
    }
    assert _types(
        store,
        _view(injury_hold_exempt=True, open_injuries=[restricted]),
        at=morning,
    ) == ["readiness_checkin"]

    restricted["surface_class"] = "surface_medical_review"
    assert _types(
        store,
        _view(injury_hold_exempt=True, open_injuries=[restricted]),
        at=morning,
    ) == ["injury_recheck", "readiness_checkin"]


def test_stable_injury_does_not_create_a_notification():
    store = NotificationStateStore()
    morning = datetime(2026, 8, 2, 8, 0, tzinfo=timezone.utc)
    injury = {
        "id": "injury-1",
        "status": "open",
        "severity": "mild",
        "surface_class": "stable_surface",
        "latest_reported_status": "same",
        "updated_at": "2026-08-01T08:00:00+00:00",
    }
    assert _types(store, _view(open_injuries=[injury]), at=morning) == [
        "readiness_checkin"
    ]


def test_high_pain_followup_is_generic_and_does_not_infer_an_injury():
    store = NotificationStateStore()
    store.completions = [
        {
            "id": "completion-1",
            "session_id": "session-old",
            "training_day": "2026-08-01",
            "status": "done",
            "pain_after": 8,
            "completed_at": "2026-08-01T21:00:00+00:00",
        }
    ]
    morning = datetime(2026, 8, 2, 8, 0, tzinfo=timezone.utc)
    candidates = build_coaching_candidates_from_view(
        store,
        _view(),
        profile_id="athlete-1",
        timezone_name="UTC",
        now_utc=morning,
    )

    assert [candidate.notification_type for candidate in candidates] == [
        "high_pain_followup",
        "readiness_checkin",
    ]
    followup = candidates[0]
    assert followup.title == "How did your body settle?"
    assert followup.url == "/today#today-checkin"
    assert "injury" not in followup.body.lower()
    assert "shoulder" not in followup.body.lower()


def test_after_midnight_high_pain_completion_still_triggers_next_training_day():
    store = NotificationStateStore()
    store.completions = [
        {
            "id": "completion-late",
            "session_id": "session-old",
            "training_day": "2026-08-01",
            "status": "done",
            "pain_after": 8,
            # Late finish: still the Aug 1 training day under the 03:00 rollover.
            "completed_at": "2026-08-02T01:00:00+00:00",
        }
    ]
    assert _types(
        store,
        _view(training_day="2026-08-02"),
        at=datetime(2026, 8, 2, 8, 0, tzinfo=timezone.utc),
    ) == ["high_pain_followup", "readiness_checkin"]


def test_old_or_current_day_high_pain_does_not_trigger_next_morning_followup():
    store = NotificationStateStore()
    morning = datetime(2026, 8, 2, 8, 0, tzinfo=timezone.utc)
    store.completions = [
        {
            "id": "current",
            "training_day": "2026-08-02",
            "status": "done",
            "pain_after": 9,
            "completed_at": "2026-08-02T07:00:00+00:00",
        },
        {
            "id": "old",
            "training_day": "2026-07-30",
            "status": "done",
            "pain_after": 9,
            "completed_at": "2026-07-30T18:00:00+00:00",
        },
    ]
    assert _types(store, _view(), at=morning) == ["readiness_checkin"]


def test_session_log_only_fires_for_an_aged_unfinished_started_session():
    store = NotificationStateStore()
    view = _view(
        recommendation_state="train_as_planned",
        completion_status="started",
    )
    store.current_completion = {
        "id": "completion-1",
        "session_id": "session-1",
        "training_day": "2026-08-02",
        "status": "started",
        "started_at": "2026-08-02T17:00:00+00:00",
    }

    assert _types(
        store,
        view,
        at=datetime(2026, 8, 2, 18, 0, tzinfo=timezone.utc),
    ) == []
    assert _types(
        store,
        view,
        at=datetime(2026, 8, 2, 19, 0, tzinfo=timezone.utc),
    ) == ["session_log_due"]

    store.current_completion["status"] = "done"
    assert _types(
        store,
        _view(recommendation_state="train_as_planned", completion_status="done"),
        at=datetime(2026, 8, 2, 19, 0, tzinfo=timezone.utc),
    ) == []


def test_training_day_helper_keeps_after_midnight_work_on_previous_day():
    assert _training_day_of("2026-08-02T01:00:00+00:00", "UTC") == "2026-08-01"
    assert _training_day_of("2026-08-02T03:00:00+00:00", "UTC") == "2026-08-02"


def test_candidates_stay_silent_outside_their_action_windows():
    store = NotificationStateStore()
    assert _types(
        store,
        _view(),
        at=datetime(2026, 8, 2, 6, 59, tzinfo=timezone.utc),
    ) == []
    assert _types(
        store,
        _view(),
        at=datetime(2026, 8, 2, 11, 0, tzinfo=timezone.utc),
    ) == []
