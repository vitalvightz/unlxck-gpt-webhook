from __future__ import annotations

from datetime import datetime, timezone

import pytest

from api.services import push_notifications
from api.services.intelligent_notifications import CoachingDispatchResult
from api.services.morning_push import is_morning_push_due, run_morning_push_sweep
from api.services.notification_foundation import update_notification_preferences
from api.services.push_notifications import (
    MORNING_CHECKIN_TAG,
    PLAN_READY_TAG,
    build_push_payload,
    push_notifications_configured,
    send_plan_ready_push,
    send_push_to_profile,
)
from support import FakeStore


@pytest.fixture()
def vapid_env(monkeypatch):
    monkeypatch.setenv("UNLXCK_VAPID_PRIVATE_KEY", "test-private-key")
    monkeypatch.setenv("UNLXCK_VAPID_PUBLIC_KEY", "test-public-key")


def _subscription(store: FakeStore, profile_id: str = "athlete-1", **overrides) -> dict:
    fields = {
        "endpoint": overrides.pop("endpoint", "https://push.example/sub-1"),
        "p256dh": "p256dh-key",
        "auth": "auth-key",
        "timezone": overrides.pop("timezone", "UTC"),
    }
    row = store.upsert_push_subscription(profile_id, fields)
    for key, value in overrides.items():
        store.push_subscriptions[row["endpoint"]][key] = value
    return store.push_subscriptions[row["endpoint"]]


def test_push_disabled_without_vapid_keys(monkeypatch):
    monkeypatch.delenv("UNLXCK_VAPID_PRIVATE_KEY", raising=False)
    monkeypatch.delenv("UNLXCK_VAPID_PUBLIC_KEY", raising=False)
    assert push_notifications_configured() is False
    assert send_push_to_profile(
        FakeStore(), "athlete-1", title="t", body="b", url="/", tag="t"
    ) == 0


def test_send_push_to_profile_sends_and_prunes_dead_endpoints(vapid_env, monkeypatch):
    store = FakeStore()
    _subscription(store, endpoint="https://push.example/alive")
    _subscription(store, endpoint="https://push.example/dead")

    def fake_send(subscription, payload):
        return subscription["endpoint"].endswith("alive")

    monkeypatch.setattr(push_notifications, "send_push_to_subscription", fake_send)

    sent = send_push_to_profile(
        store, "athlete-1", title="t", body="b", url="/plans/p1", tag="tag"
    )
    assert sent == 1
    assert list(store.push_subscriptions) == ["https://push.example/alive"]


def test_plan_ready_push_targets_plan_and_dedupes_per_profile(vapid_env, monkeypatch):
    store = FakeStore()
    _subscription(store)
    captured: list[str] = []

    def fake_send(subscription, payload):
        captured.append(payload)
        return True

    monkeypatch.setattr(push_notifications, "send_push_to_subscription", fake_send)

    assert send_plan_ready_push(store, athlete_id="athlete-1", plan_id="plan-9") == 1
    assert send_plan_ready_push(store, athlete_id="athlete-1", plan_id="plan-9") == 0
    assert len(captured) == 1
    assert "/plans/plan-9" in captured[0]
    assert PLAN_READY_TAG in captured[0]


def test_transient_plan_ready_failure_keeps_device_and_retries(vapid_env, monkeypatch):
    store = FakeStore()
    _subscription(store, endpoint="https://push.example/retryable")
    outcomes = iter([None, True])
    monkeypatch.setattr(
        push_notifications,
        "send_push_to_subscription",
        lambda *_args: next(outcomes),
    )

    assert send_plan_ready_push(store, athlete_id="athlete-1", plan_id="plan-retry") == 0
    assert list(store.push_subscriptions) == ["https://push.example/retryable"]
    assert send_plan_ready_push(store, athlete_id="athlete-1", plan_id="plan-retry") == 1


def test_plan_ready_push_respects_account_preference(vapid_env, monkeypatch):
    store = FakeStore()
    _subscription(store)
    update_notification_preferences(store, "athlete-1", {"plan_update_alerts": False})
    monkeypatch.setattr(
        push_notifications,
        "send_push_to_subscription",
        lambda *_args: pytest.fail("disabled category must not send"),
    )
    assert send_plan_ready_push(store, athlete_id="athlete-1", plan_id="plan-10") == 0


def test_push_payload_is_json_with_expected_fields():
    payload = build_push_payload(title="T", body="B", url="/today", tag="x")
    import json

    decoded = json.loads(payload)
    assert decoded == {"title": "T", "body": "B", "url": "/today", "tag": "x"}


# --- worker coaching sweep ---------------------------------------------------


def _due_check(subscription: dict, *, at: str) -> str | None:
    return is_morning_push_due(
        subscription,
        now_utc=datetime.fromisoformat(at).replace(tzinfo=timezone.utc),
        local_hour=7,
        cutoff_local_hour=11,
    )


def test_morning_push_due_respects_local_window():
    sub = {"timezone": "UTC", "morning_last_sent_day": None}
    assert _due_check(sub, at="2026-07-21T06:59:00") is None
    assert _due_check(sub, at="2026-07-21T07:05:00") == "2026-07-21"
    assert _due_check(sub, at="2026-07-21T10:59:00") == "2026-07-21"
    assert _due_check(sub, at="2026-07-21T11:00:00") is None


def test_morning_push_due_uses_device_timezone():
    sub = {"timezone": "America/Los_Angeles", "morning_last_sent_day": None}
    assert _due_check(sub, at="2026-07-21T13:00:00") is None
    assert _due_check(sub, at="2026-07-21T14:30:00") == "2026-07-21"
    tokyo = {"timezone": "Asia/Tokyo", "morning_last_sent_day": None}
    assert _due_check(tokyo, at="2026-07-20T22:30:00") == "2026-07-21"


def test_morning_push_due_dedupes_per_local_day_and_tolerates_bad_timezone():
    sent = {"timezone": "UTC", "morning_last_sent_day": "2026-07-21"}
    assert _due_check(sent, at="2026-07-21T08:00:00") is None
    assert _due_check(sent, at="2026-07-22T08:00:00") == "2026-07-22"
    unknown = {"timezone": "Not/AZone", "morning_last_sent_day": None}
    assert _due_check(unknown, at="2026-07-21T08:00:00") == "2026-07-21"


def test_coaching_sweep_sends_one_profile_decision_and_stamps_morning(vapid_env, monkeypatch):
    from api.services import morning_push

    store = FakeStore()
    _subscription(store, profile_id="athlete-1", endpoint="https://push.example/utc", timezone="UTC")
    _subscription(
        store,
        profile_id="athlete-2",
        endpoint="https://push.example/la",
        timezone="America/Los_Angeles",
    )
    calls: list[str] = []

    def fake_dispatch(inner_store, *, profile_id, timezone_name, now_utc):
        calls.append(profile_id)
        row = inner_store.list_push_subscriptions(profile_id)[0]
        if row.get("morning_last_sent_day"):
            return None
        return CoachingDispatchResult("readiness_checkin", 1)

    monkeypatch.setattr(morning_push, "dispatch_coaching_notification", fake_dispatch)
    now = datetime(2026, 7, 21, 8, 0, tzinfo=timezone.utc)

    assert run_morning_push_sweep(store, now_utc=now) == 1
    # Los Angeles is 01:00 local and is skipped before Today state is loaded.
    assert calls == ["athlete-1"]
    assert (
        store.push_subscriptions["https://push.example/utc"]["morning_last_sent_day"]
        == "2026-07-21"
    )
    assert run_morning_push_sweep(store, now_utc=now) == 0


def test_coaching_sweep_pages_every_profile(vapid_env, monkeypatch):
    from api.services import morning_push

    store = FakeStore()
    for index in range(5):
        _subscription(
            store,
            profile_id=f"athlete-{index}",
            endpoint=f"https://push.example/device-{index}",
            timezone="UTC",
        )

    calls: list[str] = []
    monkeypatch.setattr(morning_push, "MORNING_SWEEP_BATCH_SIZE", 2)
    monkeypatch.setattr(
        morning_push,
        "dispatch_coaching_notification",
        lambda _store, *, profile_id, **_kwargs: calls.append(profile_id)
        or CoachingDispatchResult("readiness_checkin", 1),
    )
    now = datetime(2026, 7, 21, 8, 0, tzinfo=timezone.utc)

    assert run_morning_push_sweep(store, now_utc=now) == 5
    assert len(calls) == 5


def test_coaching_sweep_uses_one_canonical_timezone_hint_per_profile(vapid_env, monkeypatch):
    from api.services import morning_push

    store = FakeStore()
    _subscription(store, endpoint="https://push.example/phone", timezone="UTC")
    _subscription(store, endpoint="https://push.example/laptop", timezone="Europe/London")
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(
        morning_push,
        "dispatch_coaching_notification",
        lambda _store, *, profile_id, timezone_name, **_kwargs: calls.append(
            (profile_id, timezone_name)
        )
        or None,
    )

    run_morning_push_sweep(
        store,
        now_utc=datetime(2026, 7, 21, 8, 0, tzinfo=timezone.utc),
    )
    assert len(calls) == 1
    assert calls[0][0] == "athlete-1"


def test_sweep_skips_today_state_reads_outside_action_windows(vapid_env, monkeypatch):
    from api.services import morning_push

    store = FakeStore()
    _subscription(store, timezone="UTC")
    monkeypatch.setattr(
        morning_push,
        "dispatch_coaching_notification",
        lambda *_args, **_kwargs: pytest.fail("outside-window state must not load"),
    )

    assert run_morning_push_sweep(
        store,
        now_utc=datetime(2026, 7, 21, 3, 0, tzinfo=timezone.utc),
    ) == 0
    assert run_morning_push_sweep(
        store,
        now_utc=datetime(2026, 7, 21, 23, 0, tzinfo=timezone.utc),
    ) == 0


def test_session_log_result_does_not_write_morning_stamp(vapid_env, monkeypatch):
    from api.services import morning_push

    store = FakeStore()
    _subscription(store, timezone="UTC")
    monkeypatch.setattr(
        morning_push,
        "dispatch_coaching_notification",
        lambda *_args, **_kwargs: CoachingDispatchResult("session_log_due", 1),
    )
    now = datetime(2026, 7, 21, 19, 0, tzinfo=timezone.utc)

    assert run_morning_push_sweep(store, now_utc=now) == 1
    assert store.list_push_subscriptions("athlete-1")[0]["morning_last_sent_day"] is None


def test_coaching_sweep_disabled_without_keys(monkeypatch):
    monkeypatch.delenv("UNLXCK_VAPID_PRIVATE_KEY", raising=False)
    monkeypatch.delenv("UNLXCK_VAPID_PUBLIC_KEY", raising=False)
    store = FakeStore()
    _subscription(store, timezone="UTC")
    assert run_morning_push_sweep(store) == 0


def test_morning_checkin_payload_targets_today(vapid_env, monkeypatch):
    captured: list[str] = []
    monkeypatch.setattr(
        push_notifications,
        "send_push_to_subscription",
        lambda _sub, payload: captured.append(payload) or True,
    )
    from api.services.push_notifications import send_morning_checkin_push

    assert send_morning_checkin_push(FakeStore(), {"endpoint": "https://push.example/x"}) == 1
    assert "/today" in captured[0]
    assert MORNING_CHECKIN_TAG in captured[0]
