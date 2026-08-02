from __future__ import annotations

from datetime import datetime, timezone

from api.services.session_timing_notifications import SessionTimingDispatchResult
from support import FakeStore


def _subscription(store: FakeStore, *, timezone_name: str = "UTC") -> None:
    store.upsert_push_subscription(
        "athlete-1",
        {
            "endpoint": "https://push.example/device",
            "p256dh": "p256dh-key",
            "auth": "auth-key",
            "timezone": timezone_name,
        },
    )


def test_worker_evaluates_early_saved_session_time(monkeypatch):
    from api.services import morning_push

    store = FakeStore()
    _subscription(store)
    monkeypatch.setenv("UNLXCK_VAPID_PRIVATE_KEY", "private")
    monkeypatch.setenv("UNLXCK_VAPID_PUBLIC_KEY", "public")
    calls: list[datetime] = []

    def fake_timed(_store, *, now_utc, **_kwargs):
        calls.append(now_utc)
        return SessionTimingDispatchResult("session_ready", 1)

    monkeypatch.setattr(morning_push, "dispatch_session_timing_notification", fake_timed)
    monkeypatch.setattr(
        morning_push,
        "dispatch_coaching_notification",
        lambda *_args, **_kwargs: None,
    )

    at = datetime(2026, 8, 2, 5, 30, tzinfo=timezone.utc)
    assert morning_push.run_morning_push_sweep(store, now_utc=at) == 1
    assert calls == [at]


def test_worker_evaluates_late_saved_session_time(monkeypatch):
    from api.services import morning_push

    store = FakeStore()
    _subscription(store)
    monkeypatch.setenv("UNLXCK_VAPID_PRIVATE_KEY", "private")
    monkeypatch.setenv("UNLXCK_VAPID_PUBLIC_KEY", "public")
    calls: list[datetime] = []

    def fake_timed(_store, *, now_utc, **_kwargs):
        calls.append(now_utc)
        return SessionTimingDispatchResult("session_ready", 1)

    monkeypatch.setattr(morning_push, "dispatch_session_timing_notification", fake_timed)
    monkeypatch.setattr(
        morning_push,
        "dispatch_coaching_notification",
        lambda *_args, **_kwargs: None,
    )

    at = datetime(2026, 8, 2, 22, 0, tzinfo=timezone.utc)
    assert morning_push.run_morning_push_sweep(store, now_utc=at) == 1
    assert calls == [at]
