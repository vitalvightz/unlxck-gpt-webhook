from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from api.services.notification_timing import ResolvedTrainingTime
from api.services import streak_notifications
from api.services.streak_notifications import build_streak_at_risk_candidates


class FakeStore:
    def __init__(
        self,
        *,
        login_current: int = 0,
        login_last_active_date: str | None = None,
        training_current: int = 0,
        training_last_qualifying_day: str | None = None,
    ) -> None:
        self.row = {
            "athlete_id": "athlete-1",
            "login_current": login_current,
            "login_best": login_current,
            "login_last_active_date": login_last_active_date,
            "training_current": training_current,
            "training_best": training_current,
            "training_last_qualifying_day": training_last_qualifying_day,
            "adherence_current": 0,
            "adherence_best": 0,
            "adherence_last_qualifying_day": None,
        }

    def get_athlete_streaks(self, athlete_id: str):
        assert athlete_id == "athlete-1"
        return dict(self.row)


def make_view(
    *,
    training_day: str = "2026-08-26",
    today_session: bool = True,
    completion_status: str = "not_started",
    decision_tier: str = "train",
    fight_date: str = "2026-09-12",
):
    return SimpleNamespace(
        active_plan={"id": "plan-1", "fight_date": fight_date},
        today=SimpleNamespace(
            training_day=training_day,
            next_session={"session_id": "session-1"} if today_session else {},
            session_scope="today" if today_session else "future",
            completion_status=completion_status,
            decision_tier=decision_tier,
        ),
    )


def _patch_low_timing(monkeypatch) -> None:
    monkeypatch.setattr(
        streak_notifications,
        "_authoritative_training_current",
        lambda store, profile_id, training_day: int(store.row.get("training_current") or 0),
    )
    monkeypatch.setattr(
        streak_notifications,
        "get_notification_preferences",
        lambda store, profile_id: object(),
    )
    monkeypatch.setattr(
        streak_notifications,
        "resolve_training_time",
        lambda *args, **kwargs: ResolvedTrainingTime(
            resolved_training_time=datetime(2026, 8, 26, 18, 0, tzinfo=timezone.utc),
            timing_source="fallback",
            timing_confidence="low",
        ),
    )


def test_training_streak_risk_uses_concise_coach_copy(monkeypatch) -> None:
    _patch_low_timing(monkeypatch)
    store = FakeStore(
        login_current=6,
        login_last_active_date="2026-08-25",
        training_current=5,
        training_last_qualifying_day="2026-08-25",
    )

    candidates = build_streak_at_risk_candidates(
        store,
        make_view(),
        profile_id="athlete-1",
        timezone_name="UTC",
        now_utc=datetime(2026, 8, 26, 21, 15, tzinfo=timezone.utc),
    )

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.intent == "training_streak_at_risk"
    assert candidate.title == "KEEP THE RUN GOING."
    assert candidate.body == "Today's session is still open."
    assert candidate.category == "session_reminders"
    assert candidate.action_key == "complete-session:session-1"
    assert candidate.merged_intents == ("app_streak_at_risk",)


def test_training_streak_risk_never_pushes_on_stop(monkeypatch) -> None:
    _patch_low_timing(monkeypatch)
    store = FakeStore(
        login_current=6,
        login_last_active_date="2026-08-25",
        training_current=5,
        training_last_qualifying_day="2026-08-25",
    )

    candidates = build_streak_at_risk_candidates(
        store,
        make_view(decision_tier="stop"),
        profile_id="athlete-1",
        timezone_name="UTC",
        now_utc=datetime(2026, 8, 26, 21, 15, tzinfo=timezone.utc),
    )

    assert candidates == []


def test_training_streak_risk_never_pushes_for_completed_session(monkeypatch) -> None:
    _patch_low_timing(monkeypatch)
    store = FakeStore(training_current=5, training_last_qualifying_day="2026-08-25")

    candidates = build_streak_at_risk_candidates(
        store,
        make_view(completion_status="done"),
        profile_id="athlete-1",
        timezone_name="UTC",
        now_utc=datetime(2026, 8, 26, 21, 15, tzinfo=timezone.utc),
    )

    assert candidates == []


def test_training_streak_risk_waits_for_late_known_session(monkeypatch) -> None:
    monkeypatch.setattr(
        streak_notifications,
        "_authoritative_training_current",
        lambda store, profile_id, training_day: 5,
    )
    monkeypatch.setattr(
        streak_notifications,
        "get_notification_preferences",
        lambda store, profile_id: object(),
    )
    monkeypatch.setattr(
        streak_notifications,
        "resolve_training_time",
        lambda *args, **kwargs: ResolvedTrainingTime(
            resolved_training_time=datetime(2026, 8, 26, 21, 0, tzinfo=timezone.utc),
            timing_source="preferred_training_time",
            timing_confidence="high",
        ),
    )
    store = FakeStore(training_current=5, training_last_qualifying_day="2026-08-25")

    candidates = build_streak_at_risk_candidates(
        store,
        make_view(),
        profile_id="athlete-1",
        timezone_name="UTC",
        now_utc=datetime(2026, 8, 26, 21, 30, tzinfo=timezone.utc),
    )

    assert candidates == []


def test_stale_persisted_training_streak_does_not_create_false_risk_push(monkeypatch) -> None:
    monkeypatch.setattr(
        streak_notifications,
        "_authoritative_training_current",
        lambda store, profile_id, training_day: 0,
    )
    store = FakeStore(
        login_current=6,
        login_last_active_date="2026-08-25",
        training_current=5,
        training_last_qualifying_day="2026-08-24",
    )

    candidates = build_streak_at_risk_candidates(
        store,
        make_view(),
        profile_id="athlete-1",
        timezone_name="UTC",
        now_utc=datetime(2026, 8, 26, 21, 15, tzinfo=timezone.utc),
    )

    assert candidates == []


def test_app_streak_risk_uses_concise_coach_copy() -> None:
    store = FakeStore(
        login_current=6,
        login_last_active_date="2026-08-25",
        training_current=1,
    )

    candidates = build_streak_at_risk_candidates(
        store,
        make_view(today_session=False),
        profile_id="athlete-1",
        timezone_name="UTC",
        now_utc=datetime(2026, 8, 26, 19, 20, tzinfo=timezone.utc),
    )

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.intent == "app_streak_at_risk"
    assert candidate.title == "LXCK IN."
    assert candidate.body == "Keep your streak alive."
    assert candidate.category == "progress_milestones"
    assert candidate.url == "/today"


def test_app_streak_risk_requires_three_day_run() -> None:
    store = FakeStore(login_current=2, login_last_active_date="2026-08-25")

    candidates = build_streak_at_risk_candidates(
        store,
        make_view(today_session=False),
        profile_id="athlete-1",
        timezone_name="UTC",
        now_utc=datetime(2026, 8, 26, 19, 20, tzinfo=timezone.utc),
    )

    assert candidates == []


def test_app_streak_risk_disappears_after_activity_today() -> None:
    store = FakeStore(login_current=7, login_last_active_date="2026-08-26")

    candidates = build_streak_at_risk_candidates(
        store,
        make_view(today_session=False),
        profile_id="athlete-1",
        timezone_name="UTC",
        now_utc=datetime(2026, 8, 26, 19, 20, tzinfo=timezone.utc),
    )

    assert candidates == []


def test_training_streak_reserves_evening_and_suppresses_app_nudge(monkeypatch) -> None:
    _patch_low_timing(monkeypatch)
    store = FakeStore(
        login_current=6,
        login_last_active_date="2026-08-25",
        training_current=5,
        training_last_qualifying_day="2026-08-25",
    )

    candidates = build_streak_at_risk_candidates(
        store,
        make_view(),
        profile_id="athlete-1",
        timezone_name="UTC",
        now_utc=datetime(2026, 8, 26, 19, 20, tzinfo=timezone.utc),
    )

    assert candidates == []


def test_fight_day_suppresses_streak_gamification() -> None:
    store = FakeStore(login_current=8, login_last_active_date="2026-08-25")

    candidates = build_streak_at_risk_candidates(
        store,
        make_view(today_session=False, fight_date="2026-08-26"),
        profile_id="athlete-1",
        timezone_name="UTC",
        now_utc=datetime(2026, 8, 26, 19, 20, tzinfo=timezone.utc),
    )

    assert candidates == []
