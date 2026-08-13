from __future__ import annotations

from datetime import datetime, timezone

from api.contracts.command_view import CommandView
from api.notification_models import NotificationPreferences
from api.services.notification_timing import resolve_training_time
from api.services.session_timing_notifications import build_session_timing_candidates_from_view


class TimingStore:
    def __init__(self, completions: list[dict] | None = None) -> None:
        self.completions = completions or []
        self.plans: dict[str, dict] = {}

    def list_session_completions(self, _profile_id: str, *, limit: int = 60) -> list[dict]:
        return [dict(row) for row in self.completions[:limit]]

    def get_plan(self, plan_id: str) -> dict | None:
        return self.plans.get(plan_id)


def _view(training_day: str = "2026-08-09") -> CommandView:
    return CommandView.model_validate(
        {
            "active_plan": {"id": "plan-1"},
            "today": {
                "training_day": training_day,
                "recommendation_state": "train_as_planned",
                "decision_tier": "green",
                "session_scope": "today",
                "completion_status": "not_started",
                "next_session": {
                    "session_id": "session-current",
                    "session_type": "strength",
                    "title": "Power and strength",
                },
            },
        }
    )


def test_explicit_training_time_overrides_history() -> None:
    store = TimingStore(
        [{"training_day": "2026-08-02", "started_at": "2026-08-02T18:00:00+00:00"}]
    )
    result = resolve_training_time(
        store,
        _view(),
        NotificationPreferences(preferred_training_time="20:15"),
        profile_id="athlete-1",
        timezone_name="UTC",
    )
    assert result.resolved_training_time.hour == 20
    assert result.resolved_training_time.minute == 15
    assert result.timing_source == "preferred_training_time"
    assert result.timing_confidence == "high"


def test_same_weekday_history_produces_high_confidence_median() -> None:
    store = TimingStore(
        [
            {"training_day": "2026-08-02", "started_at": "2026-08-02T18:55:00+00:00"},
            {"training_day": "2026-07-26", "started_at": "2026-07-26T19:05:00+00:00"},
            {"training_day": "2026-07-19", "started_at": "2026-07-19T19:00:00+00:00"},
        ]
    )
    result = resolve_training_time(
        store,
        _view("2026-08-09"),
        NotificationPreferences(preferred_training_time=None),
        profile_id="athlete-1",
        timezone_name="UTC",
    )
    assert result.resolved_training_time.strftime("%H:%M") == "19:00"
    assert result.timing_source == "same_weekday_history"
    assert result.timing_confidence == "high"
    assert result.sample_count == 3
    assert result.median_absolute_deviation_minutes == 5


def test_same_weekday_history_with_moderate_dispersion_is_medium_confidence() -> None:
    store = TimingStore(
        [
            {"training_day": "2026-08-02", "started_at": "2026-08-02T18:00:00+00:00"},
            {"training_day": "2026-07-26", "started_at": "2026-07-26T19:00:00+00:00"},
            {"training_day": "2026-07-19", "started_at": "2026-07-19T20:00:00+00:00"},
        ]
    )

    result = resolve_training_time(
        store,
        _view("2026-08-09"),
        NotificationPreferences(),
        profile_id="athlete-1",
        timezone_name="UTC",
    )

    assert result.resolved_training_time.strftime("%H:%M") == "19:00"
    assert result.timing_confidence == "medium"
    assert result.median_absolute_deviation_minutes == 60


def test_same_weekday_history_with_wild_dispersion_is_low_confidence() -> None:
    store = TimingStore(
        [
            {"training_day": "2026-08-02", "started_at": "2026-08-02T18:00:00+00:00"},
            {"training_day": "2026-07-26", "started_at": "2026-07-26T20:00:00+00:00"},
            {"training_day": "2026-07-19", "started_at": "2026-07-19T22:30:00+00:00"},
        ]
    )

    result = resolve_training_time(
        store,
        _view("2026-08-09"),
        NotificationPreferences(),
        profile_id="athlete-1",
        timezone_name="UTC",
    )

    assert result.resolved_training_time.strftime("%H:%M") == "20:00"
    assert result.timing_confidence == "low"
    assert result.median_absolute_deviation_minutes == 120


def test_missing_time_uses_low_confidence_fallback_and_non_exact_copy(monkeypatch) -> None:
    monkeypatch.setenv("UNLXCK_NOTIFICATION_FALLBACK_TRAINING_TIME", "18:00")
    store = TimingStore()
    view = _view("2026-08-09")
    timing = resolve_training_time(
        store,
        view,
        NotificationPreferences(preferred_training_time=None),
        profile_id="athlete-1",
        timezone_name="UTC",
    )
    assert timing.timing_source == "configurable_fallback"
    assert timing.timing_confidence == "low"

    candidates = build_session_timing_candidates_from_view(
        view,
        NotificationPreferences(preferred_training_time=None, quiet_hours_enabled=False),
        profile_id="athlete-1",
        timezone_name="UTC",
        now_utc=datetime(2026, 8, 9, 17, 30, tzinfo=timezone.utc),
        store=store,
    )
    assert len(candidates) == 1
    assert candidates[0].timing_confidence == "low"
    assert "Training is later" in candidates[0].body
    assert "30 minutes" not in candidates[0].body.lower()


def test_after_midnight_history_and_fallback_preserve_0300_rollover(monkeypatch) -> None:
    monkeypatch.setenv("UNLXCK_NOTIFICATION_FALLBACK_TRAINING_TIME", "01:30")
    result = resolve_training_time(
        TimingStore(),
        _view("2026-08-09"),
        NotificationPreferences(),
        profile_id="athlete-1",
        timezone_name="Europe/London",
    )
    assert result.resolved_training_time.date().isoformat() == "2026-08-10"
    assert result.resolved_training_time.strftime("%H:%M") == "01:30"


def test_authoritative_iso_schedule_is_converted_to_athlete_local_time() -> None:
    view = _view("2026-08-09")
    view.today.next_session["scheduled_start"] = "2026-08-09T18:00:00+00:00"
    result = resolve_training_time(
        TimingStore(),
        view,
        NotificationPreferences(),
        profile_id="athlete-1",
        timezone_name="Europe/London",
    )
    assert result.resolved_training_time.strftime("%H:%M") == "19:00"
    assert result.timing_source == "session_schedule"
    assert result.timing_confidence == "high"
