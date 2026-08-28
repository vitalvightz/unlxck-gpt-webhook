from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from api.services import streak_notifications
from api.services.notification_timing import ResolvedTrainingTime
from api.services.streak_notifications import build_streak_at_risk_candidates


def _view():
    return SimpleNamespace(
        active_plan={"id": "plan-1", "fight_date": "2026-09-12"},
        today=SimpleNamespace(
            training_day="2026-08-26",
            next_session={"session_id": "session-1"},
            session_scope="today",
            completion_status="not_started",
            decision_tier="train",
        ),
    )


def test_2030_session_becomes_eligible_after_90_minutes(monkeypatch) -> None:
    store = object()
    monkeypatch.setattr(
        streak_notifications,
        "get_streak_state",
        lambda *args, **kwargs: {
            "login": {"current": 6, "last_active_date": "2026-08-25"},
            "adherence": {"current": 5},
        },
    )
    monkeypatch.setattr(
        streak_notifications,
        "_authoritative_training_current",
        lambda *args, **kwargs: 5,
    )
    monkeypatch.setattr(
        streak_notifications,
        "get_notification_preferences",
        lambda *args, **kwargs: object(),
    )
    monkeypatch.setattr(
        streak_notifications,
        "resolve_training_time",
        lambda *args, **kwargs: ResolvedTrainingTime(
            resolved_training_time=datetime(2026, 8, 26, 20, 30, tzinfo=timezone.utc),
            timing_source="preferred_training_time",
            timing_confidence="high",
        ),
    )

    before = build_streak_at_risk_candidates(
        store,
        _view(),
        profile_id="athlete-1",
        timezone_name="UTC",
        now_utc=datetime(2026, 8, 26, 21, 59, tzinfo=timezone.utc),
    )
    due = build_streak_at_risk_candidates(
        store,
        _view(),
        profile_id="athlete-1",
        timezone_name="UTC",
        now_utc=datetime(2026, 8, 26, 22, 5, tzinfo=timezone.utc),
    )

    assert before == []
    assert len(due) == 1
    assert due[0].intent == "training_streak_at_risk"
    assert due[0].expires_at == datetime(2026, 8, 26, 23, 30, tzinfo=timezone.utc)
