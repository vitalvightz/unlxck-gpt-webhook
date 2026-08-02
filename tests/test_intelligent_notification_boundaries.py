from __future__ import annotations

from datetime import datetime, timezone

from api.contracts.command_view import CommandView
from api.notification_models import NotificationPreferences
from api.services.intelligent_notifications import (
    _bound_to_quiet_hours,
    build_coaching_candidates_from_view,
)


class BoundaryStore:
    def __init__(self) -> None:
        self.current_completion: dict | None = None

    def list_session_completions(self, _profile_id: str, *, limit: int = 6) -> list[dict]:
        return []

    def get_session_completion(
        self,
        _profile_id: str,
        _session_id: str,
        _training_day: str,
    ) -> dict | None:
        return dict(self.current_completion) if self.current_completion else None


def _view(
    *,
    completion_status: str = "not_started",
    recommendation_state: str = "not_checked_in",
    injuries: list[dict] | None = None,
) -> CommandView:
    return CommandView.model_validate(
        {
            "active_plan": {"id": "plan-1"},
            "today": {
                "training_day": "2026-08-02",
                "recommendation_state": recommendation_state,
                "session_scope": "today",
                "completion_status": completion_status,
                "next_session": {"session_id": "session-1", "title": "Sharp work"},
            },
            "open_injuries": injuries or [],
            "risk_watch": [],
        }
    )


def test_morning_candidate_expires_at_morning_cutoff(monkeypatch):
    monkeypatch.setenv("UNLXCK_MORNING_PUSH_CUTOFF_LOCAL_HOUR", "11")
    store = BoundaryStore()
    candidates = build_coaching_candidates_from_view(
        store,
        _view(),
        profile_id="athlete-1",
        timezone_name="UTC",
        now_utc=datetime(2026, 8, 2, 10, 55, tzinfo=timezone.utc),
    )

    readiness = next(
        candidate for candidate in candidates if candidate.notification_type == "readiness_checkin"
    )
    assert readiness.expires_at == datetime(2026, 8, 2, 11, 0, tzinfo=timezone.utc)


def test_session_log_candidate_expires_at_session_window_cutoff():
    store = BoundaryStore()
    store.current_completion = {
        "id": "completion-1",
        "session_id": "session-1",
        "training_day": "2026-08-02",
        "status": "started",
        "started_at": "2026-08-02T19:00:00+00:00",
    }
    candidates = build_coaching_candidates_from_view(
        store,
        _view(completion_status="started", recommendation_state="train_as_planned"),
        profile_id="athlete-1",
        timezone_name="UTC",
        now_utc=datetime(2026, 8, 2, 21, 55, tzinfo=timezone.utc),
    )

    assert len(candidates) == 1
    assert candidates[0].notification_type == "session_log_due"
    assert candidates[0].expires_at == datetime(2026, 8, 2, 22, 0, tzinfo=timezone.utc)


def test_custom_quiet_hours_shorten_transport_expiry():
    store = BoundaryStore()
    candidate = build_coaching_candidates_from_view(
        store,
        _view(),
        profile_id="athlete-1",
        timezone_name="UTC",
        now_utc=datetime(2026, 8, 2, 8, 0, tzinfo=timezone.utc),
    )[0]
    preferences = NotificationPreferences.model_validate(
        {
            "quiet_hours_enabled": True,
            "quiet_hours_start": "08:15",
            "quiet_hours_end": "09:00",
        }
    )

    bounded = _bound_to_quiet_hours(
        candidate,
        preferences,
        now_utc=datetime(2026, 8, 2, 8, 0, tzinfo=timezone.utc),
    )
    assert bounded.expires_at == datetime(2026, 8, 2, 8, 15, tzinfo=timezone.utc)


def test_severe_load_injury_outranks_local_skin_restriction():
    store = BoundaryStore()
    injuries = [
        {
            "id": "skin-local",
            "status": "open",
            "severity": "moderate",
            "surface_class": "surface_local_restriction",
            "latest_reported_status": "same",
            "updated_at": "2026-08-01T08:00:00+00:00",
        },
        {
            "id": "load-severe",
            "status": "open",
            "severity": "severe",
            "surface_class": "non_surface",
            "latest_reported_status": "same",
            "updated_at": "2026-08-01T08:00:00+00:00",
        },
    ]
    candidates = build_coaching_candidates_from_view(
        store,
        _view(injuries=injuries),
        profile_id="athlete-1",
        timezone_name="UTC",
        now_utc=datetime(2026, 8, 2, 8, 0, tzinfo=timezone.utc),
    )

    injury = next(
        candidate for candidate in candidates if candidate.notification_type == "injury_recheck"
    )
    assert injury.tag == "injury-recheck-load-severe"
    assert injury.title == "Update the injury first"


def test_medical_review_remains_highest_in_multi_injury_ranking():
    store = BoundaryStore()
    injuries = [
        {
            "id": "load-worse",
            "status": "open",
            "severity": "severe",
            "surface_class": "non_surface",
            "latest_reported_status": "worse",
            "updated_at": "2026-08-01T08:00:00+00:00",
        },
        {
            "id": "medical",
            "status": "open",
            "severity": "moderate",
            "surface_class": "surface_medical_review",
            "latest_reported_status": "same",
            "updated_at": "2026-08-01T08:00:00+00:00",
        },
    ]
    candidates = build_coaching_candidates_from_view(
        store,
        _view(injuries=injuries),
        profile_id="athlete-1",
        timezone_name="UTC",
        now_utc=datetime(2026, 8, 2, 8, 0, tzinfo=timezone.utc),
    )

    injury = next(
        candidate for candidate in candidates if candidate.notification_type == "injury_recheck"
    )
    assert injury.tag == "injury-recheck-medical"
    assert injury.title == "Get the injury checked"
