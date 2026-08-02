from __future__ import annotations

from datetime import datetime, timezone

import pytest

from api.services import push_notifications
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


# --- morning sweep -----------------------------------------------------------


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
    # 13:00 UTC is 06:00 in Los Angeles (UTC-7 in July): not yet due there.
    sub = {"timezone": "America/Los_Angeles", "morning_last_sent_day": None}
    assert _due_check(sub, at="2026-07-21T13:00:00") is None
    # 14:30 UTC is 07:30 local: due, stamped with the LOCAL date.
    assert _due_check(sub, at="2026-07-21T14:30:00") == "2026-07-21"
    # Tokyo (UTC+9): 22:30 UTC on the 20th is 07:30 on the 21st locally.
    tokyo = {"timezone": "Asia/Tokyo", "morning_last_sent_day": None}
    assert _due_check(tokyo, at="2026-07-20T22:30:00") == "2026-07-21"


def test_morning_push_due_dedupes_per_local_day_and_tolerates_bad_timezone():
    sent = {"timezone": "UTC", "morning_last_sent_day": "2026-07-21"}
    assert _due_check(sent, at="2026-07-21T08:00:00") is None
    assert _due_check(sent, at="2026-07-22T08:00:00") == "2026-07-22"
    unknown = {"timezone": "Not/AZone", "morning_last_sent_day": None}
    assert _due_check(unknown, at="2026-07-21T08:00:00") == "2026-07-21"


def test_morning_sweep_sends_once_and_stamps(vapid_env, monkeypatch):
    from api.services import morning_push

    store = FakeStore()
    _subscription(store, profile_id="athlete-1", endpoint="https://push.example/utc", timezone="UTC")
    # Different profile: not yet morning in Los Angeles at 08:00 UTC.
    _subscription(
        store,
        profile_id="athlete-2",
        endpoint="https://push.example/la",
        timezone="America/Los_Angeles",
    )

    sends: list[str] = []

    def fake_send(inner_store, subscription, **_kwargs):
        sends.append(subscription["endpoint"])
        return 1

    monkeypatch.setattr(morning_push, "send_morning_checkin_push", fake_send)
    now = datetime(2026, 7, 21, 8, 0, tzinfo=timezone.utc)

    assert run_morning_push_sweep(store, now_utc=now) == 1
    assert sends == ["https://push.example/utc"]
    assert (
        store.push_subscriptions["https://push.example/utc"]["morning_last_sent_day"]
        == "2026-07-21"
    )
    assert run_morning_push_sweep(store, now_utc=now) == 0
    assert sends == ["https://push.example/utc"]


def test_morning_sweep_prunes_dead_endpoints(vapid_env, monkeypatch):
    store = FakeStore()
    _subscription(store, endpoint="https://push.example/dead", timezone="UTC")
    monkeypatch.setattr(push_notifications, "send_push_to_subscription", lambda *_args: False)
    now = datetime(2026, 7, 21, 8, 0, tzinfo=timezone.utc)

    assert run_morning_push_sweep(store, now_utc=now) == 0
    assert store.push_subscriptions == {}


def test_morning_sweep_pages_past_one_batch(vapid_env, monkeypatch):
    from api.services import morning_push

    store = FakeStore()
    for index in range(5):
        _subscription(
            store,
            profile_id=f"athlete-{index}",
            endpoint=f"https://push.example/device-{index}",
            timezone="UTC",
        )

    sends: list[str] = []
    monkeypatch.setattr(morning_push, "MORNING_SWEEP_BATCH_SIZE", 2)
    monkeypatch.setattr(
        morning_push,
        "send_morning_checkin_push",
        lambda _store, subscription, **_kwargs: sends.append(subscription["endpoint"]) or 1,
    )
    now = datetime(2026, 7, 21, 8, 0, tzinfo=timezone.utc)

    assert run_morning_push_sweep(store, now_utc=now) == 5
    assert len(sends) == 5


def test_morning_sweep_one_profile_fans_out_one_decision_to_all_devices(vapid_env, monkeypatch):
    store = FakeStore()
    _subscription(store, endpoint="https://push.example/phone", timezone="UTC")
    _subscription(store, endpoint="https://push.example/laptop", timezone="UTC")
    sends: list[str] = []
    monkeypatch.setattr(
        push_notifications,
        "send_push_to_subscription",
        lambda subscription, _payload: sends.append(subscription["endpoint"]) or True,
    )
    now = datetime(2026, 7, 21, 8, 0, tzinfo=timezone.utc)

    assert run_morning_push_sweep(store, now_utc=now) == 2
    assert sorted(sends) == ["https://push.example/laptop", "https://push.example/phone"]
    assert run_morning_push_sweep(store, now_utc=now) == 0
    assert len(sends) == 2


def test_morning_sweep_respects_checkin_preference(vapid_env, monkeypatch):
    store = FakeStore()
    _subscription(store, timezone="UTC")
    update_notification_preferences(store, "athlete-1", {"checkin_reminders": False})
    monkeypatch.setattr(
        push_notifications,
        "send_push_to_subscription",
        lambda *_args: pytest.fail("disabled category must not send"),
    )
    now = datetime(2026, 7, 21, 8, 0, tzinfo=timezone.utc)
    assert run_morning_push_sweep(store, now_utc=now) == 0


def test_morning_sweep_disabled_without_keys(monkeypatch):
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
