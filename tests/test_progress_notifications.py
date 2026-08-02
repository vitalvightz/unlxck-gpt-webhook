from __future__ import annotations

from datetime import datetime, timezone

from api.services import push_notifications
from api.services.notification_foundation import update_notification_preferences
from api.services import progress_notifications
from api.services.progress_notifications import (
    award_session_progress,
    build_level_up_candidate,
    dispatch_progress_award_notification,
    resolve_xp_level,
    send_coach_message_notification,
)
from support import FakeStore


class ProgressStore:
    def __init__(self) -> None:
        self.total = 80
        self.calls: list[tuple[str, str]] = []

    def award_xp(self, athlete_id, *, action, idempotency_key, calendar_date=None):
        self.calls.append((action, idempotency_key))
        amount = 25 if action == "training_logged" else 50
        previous = self.total
        self.total += amount
        return {
            "awarded": True,
            "previous_total_xp": previous,
            "state": {"total_xp": self.total},
            "award": {"action": action, "amount": amount},
        }


def test_level_resolution_matches_product_thresholds():
    assert resolve_xp_level(0)[:2] == (1, "Rookie")
    assert resolve_xp_level(99)[:2] == (1, "Rookie")
    assert resolve_xp_level(100)[:2] == (2, "Prospect")
    assert resolve_xp_level(450)[:2] == (4, "Challenger")
    assert resolve_xp_level(1700)[:2] == (8, "Champion")


def test_level_candidate_only_exists_when_a_threshold_is_crossed():
    now = datetime(2026, 8, 2, 12, 0, tzinfo=timezone.utc)
    assert build_level_up_candidate(
        athlete_id="athlete-1",
        previous_total_xp=100,
        total_xp=149,
        source_key="session-1",
        now_utc=now,
    ) is None

    candidate = build_level_up_candidate(
        athlete_id="athlete-1",
        previous_total_xp=99,
        total_xp=124,
        source_key="session-1",
        now_utc=now,
    )
    assert candidate is not None
    assert candidate.title == "Level 2: Prospect"
    assert candidate.category == "progress_milestones"
    assert candidate.url == "/#progress"


def test_daily_login_never_sends_a_progress_push(monkeypatch):
    monkeypatch.setattr(
        progress_notifications,
        "dispatch_push_candidate",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must stay silent")),
    )
    assert dispatch_progress_award_notification(
        ProgressStore(),
        athlete_id="athlete-1",
        action="daily_login",
        award_result={
            "awarded": True,
            "previous_total_xp": 90,
            "state": {"total_xp": 100},
        },
        source_key="2026-08-02",
    ) == 0


def test_completed_session_awards_training_and_planned_session_xp(monkeypatch):
    store = ProgressStore()
    dispatched: list[str] = []
    monkeypatch.setattr(
        progress_notifications,
        "dispatch_push_candidate",
        lambda _store, candidate, **_kwargs: dispatched.append(candidate.notification_type) or 1,
    )

    results = award_session_progress(
        store,
        athlete_id="athlete-1",
        athlete_timezone="Europe/London",
        completion={
            "id": "completion-1",
            "session_id": "session-1",
            "training_day": "2026-08-02",
            "status": "done",
        },
    )

    assert len(results) == 2
    assert [call[0] for call in store.calls] == [
        "training_logged",
        "planned_session_completed",
    ]
    assert store.calls[0][1] == "training_logged:completion-1"
    # 80 + 25 crosses Level 2 once; the second award does not send it again.
    assert dispatched == ["xp_level_up"]


def test_skipped_or_started_session_does_not_award_xp():
    for status in ("skipped", "started", "not_started"):
        store = ProgressStore()
        assert award_session_progress(
            store,
            athlete_id="athlete-1",
            athlete_timezone="UTC",
            completion={"id": "completion-1", "status": status},
        ) == []
        assert store.calls == []


def test_full_week_award_prefers_level_up_when_both_happen(monkeypatch):
    captured: list[str] = []
    monkeypatch.setattr(
        progress_notifications,
        "dispatch_push_candidate",
        lambda _store, candidate, **_kwargs: captured.append(candidate.notification_type) or 1,
    )
    delivered = dispatch_progress_award_notification(
        ProgressStore(),
        athlete_id="athlete-1",
        action="full_training_week_completed",
        award_result={
            "awarded": True,
            "previous_total_xp": 240,
            "state": {"total_xp": 340},
        },
        source_key="plan-1:week-2",
    )
    assert delivered == 1
    assert captured == ["xp_level_up"]


def test_coach_message_uses_explicit_copy_and_dedupe_key(monkeypatch):
    captured = []
    monkeypatch.setattr(
        progress_notifications,
        "dispatch_push_candidate",
        lambda _store, candidate, **_kwargs: captured.append(candidate) or 1,
    )
    assert send_coach_message_notification(
        ProgressStore(),
        athlete_id="athlete-1",
        message_id="message-9",
        title="One change for today",
        body="Keep the final round technical. Open Today before training.",
        url="/today#today-session",
    ) == 1
    candidate = captured[0]
    assert candidate.category == "coach_messages"
    assert candidate.dedupe_key == "coach-message:message-9"
    assert candidate.respect_quiet_hours is True


def test_coach_message_respects_athlete_local_quiet_hours(monkeypatch):
    monkeypatch.setenv("UNLXCK_VAPID_PRIVATE_KEY", "test-private-key")
    monkeypatch.setenv("UNLXCK_VAPID_PUBLIC_KEY", "test-public-key")
    store = FakeStore()
    store.upsert_push_subscription(
        "athlete-1",
        {
            "endpoint": "https://push.example/athlete-1",
            "p256dh": "p256dh-key",
            "auth": "auth-key",
            "timezone": "Europe/London",
        },
    )
    update_notification_preferences(
        store,
        "athlete-1",
        {"quiet_hours_enabled": True, "quiet_hours_start": "22:00", "quiet_hours_end": "07:00"},
    )
    sent: list[str] = []
    monkeypatch.setattr(
        push_notifications,
        "send_push_to_subscription",
        lambda _subscription, payload, **_kwargs: sent.append(payload) or True,
    )

    assert send_coach_message_notification(
        store,
        athlete_id="athlete-1",
        message_id="quiet-hours-message",
        title="One change for today",
        body="Keep the final round technical. Open Today before training.",
        timezone_name="Europe/London",
        now_utc=datetime(2026, 8, 2, 22, 30, tzinfo=timezone.utc),
    ) == 0
    assert sent == []

    assert send_coach_message_notification(
        store,
        athlete_id="athlete-1",
        message_id="daytime-message",
        title="One change for today",
        body="Keep the final round technical. Open Today before training.",
        timezone_name="Europe/London",
        now_utc=datetime(2026, 8, 2, 8, 30, tzinfo=timezone.utc),
    ) == 1
    assert len(sent) == 1
