from __future__ import annotations

from datetime import datetime, timezone

from api.contracts.command_view import CommandView
from api.notification_models import NotificationPreferences, NotificationPreferencesUpdate
from api.services.session_timing_notifications import build_session_timing_candidates_from_view


def _view(
    *,
    recommendation_state: str = "train_as_planned",
    decision_tier: str = "green",
    completion_status: str = "not_started",
    session_scope: str = "today",
) -> CommandView:
    return CommandView.model_validate(
        {
            "active_plan": {"id": "plan-1"},
            "today": {
                "training_day": "2026-08-02",
                "recommendation_state": recommendation_state,
                "decision_tier": decision_tier,
                "session_scope": session_scope,
                "completion_status": completion_status,
                "next_session": {
                    "session_id": "session-1",
                    "title": "Power and strength",
                }
                if session_scope == "today"
                else {},
            },
            "open_injuries": [],
            "risk_watch": [],
        }
    )


def _candidates(
    view: CommandView,
    *,
    at: datetime,
    training_time: str | None = "20:00",
    quiet_start: str = "22:00",
) -> list:
    preferences = NotificationPreferences(
        preferred_training_time=training_time,
        quiet_hours_start=quiet_start,
    )
    return build_session_timing_candidates_from_view(
        view,
        preferences,
        profile_id="athlete-1",
        timezone_name="UTC",
        now_utc=at,
    )


def test_no_preferred_time_means_no_timed_session_reminder():
    assert _candidates(
        _view(),
        at=datetime(2026, 8, 2, 19, 40, tzinfo=timezone.utc),
        training_time=None,
    ) == []


def test_green_session_reminder_exists_only_in_saved_time_window():
    view = _view()
    assert _candidates(
        view,
        at=datetime(2026, 8, 2, 19, 29, tzinfo=timezone.utc),
    ) == []

    candidates = _candidates(
        view,
        at=datetime(2026, 8, 2, 19, 30, tzinfo=timezone.utc),
    )
    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.notification_type == "session_ready"
    assert candidate.title == "Today's work is set"
    assert candidate.url == "/today#today-session"
    assert candidate.expires_at == datetime(2026, 8, 2, 20, 15, tzinfo=timezone.utc)

    assert _candidates(
        view,
        at=datetime(2026, 8, 2, 20, 15, tzinfo=timezone.utc),
    ) == []


def test_modified_and_pull_back_decisions_use_adjusted_copy():
    for state, tier in (("modify", "modify"), ("pull_back", "pull_back")):
        candidates = _candidates(
            _view(recommendation_state=state, decision_tier=tier),
            at=datetime(2026, 8, 2, 19, 45, tzinfo=timezone.utc),
        )
        assert len(candidates) == 1
        assert candidates[0].notification_type == "session_modified"
        assert candidates[0].title == "I've adjusted today's work"


def test_stop_decision_does_not_require_a_preferred_training_time():
    candidates = _candidates(
        _view(recommendation_state="pull_back", decision_tier="stop"),
        at=datetime(2026, 8, 2, 9, 0, tzinfo=timezone.utc),
        training_time=None,
    )
    assert len(candidates) == 1
    assert candidates[0].notification_type == "session_stop"
    assert candidates[0].title == "No training today"
    assert candidates[0].url == "/today#today-command"


def test_not_checked_in_or_resolved_session_stays_silent():
    at = datetime(2026, 8, 2, 19, 45, tzinfo=timezone.utc)
    assert _candidates(
        _view(recommendation_state="not_checked_in", decision_tier="not_checked_in"),
        at=at,
    ) == []
    for status in ("done", "modified", "skipped", "started"):
        assert _candidates(_view(completion_status=status), at=at) == []
    assert _candidates(_view(session_scope="next"), at=at) == []


def test_preferred_training_time_validation_and_clear_semantics():
    assert NotificationPreferences(preferred_training_time="20:30:00").preferred_training_time == "20:30"
    assert NotificationPreferencesUpdate(preferred_training_time=None).model_dump(
        exclude_unset=True
    ) == {"preferred_training_time": None}
