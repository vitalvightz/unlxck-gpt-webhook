from __future__ import annotations

from support import _build_client

ATHLETE_HEADERS = {"Authorization": "Bearer athlete-token"}

DEFAULT_PREFERENCES = {
    "push_enabled": True,
    "session_reminders": True,
    "checkin_reminders": True,
    "injury_followups": True,
    "plan_update_alerts": True,
    "progress_milestones": True,
    "coach_messages": True,
    "quiet_hours_enabled": True,
    "quiet_hours_start": "22:00",
    "quiet_hours_end": "07:00",
    "preferred_training_time": None,
}


def _subscribe_payload(endpoint: str = "https://push.example/browser-1") -> dict:
    return {
        "endpoint": endpoint,
        "keys": {"p256dh": "p256dh-key", "auth": "auth-key"},
        "timezone": "Europe/London",
    }


def test_push_settings_reports_server_configuration_and_preferences(monkeypatch):
    client, _store, _ = _build_client()

    monkeypatch.delenv("UNLXCK_VAPID_PRIVATE_KEY", raising=False)
    monkeypatch.delenv("UNLXCK_VAPID_PUBLIC_KEY", raising=False)
    disabled = client.get("/api/push/settings", headers=ATHLETE_HEADERS)
    assert disabled.status_code == 200
    assert disabled.json() == {
        "enabled": False,
        "public_key": "",
        "preferences": DEFAULT_PREFERENCES,
    }

    monkeypatch.setenv("UNLXCK_VAPID_PRIVATE_KEY", "private")
    monkeypatch.setenv("UNLXCK_VAPID_PUBLIC_KEY", "public-key")
    enabled = client.get("/api/push/settings", headers=ATHLETE_HEADERS)
    assert enabled.status_code == 200
    assert enabled.json() == {
        "enabled": True,
        "public_key": "public-key",
        "preferences": DEFAULT_PREFERENCES,
    }


def test_push_settings_requires_auth():
    client, _store, _ = _build_client()
    assert client.get("/api/push/settings").status_code in (401, 403)
    assert client.put("/api/push/preferences", json={"checkin_reminders": False}).status_code in (401, 403)


def test_notification_preferences_round_trip_is_account_scoped():
    client, _store, _ = _build_client()

    updated = client.put(
        "/api/push/preferences",
        headers=ATHLETE_HEADERS,
        json={
            "checkin_reminders": False,
            "progress_milestones": False,
            "quiet_hours_start": "23:15",
            "quiet_hours_end": "06:30",
            "preferred_training_time": "20:30",
        },
    )
    assert updated.status_code == 200
    payload = updated.json()
    assert payload["checkin_reminders"] is False
    assert payload["progress_milestones"] is False
    assert payload["plan_update_alerts"] is True
    assert payload["quiet_hours_start"] == "23:15"
    assert payload["quiet_hours_end"] == "06:30"
    assert payload["preferred_training_time"] == "20:30"

    settings = client.get("/api/push/settings", headers=ATHLETE_HEADERS)
    assert settings.status_code == 200
    assert settings.json()["preferences"] == payload

    admin_settings = client.get(
        "/api/push/settings",
        headers={"Authorization": "Bearer admin-token"},
    )
    assert admin_settings.status_code == 200
    assert admin_settings.json()["preferences"] == DEFAULT_PREFERENCES


def test_preferred_training_time_can_be_explicitly_cleared():
    client, _store, _ = _build_client()
    saved = client.put(
        "/api/push/preferences",
        headers=ATHLETE_HEADERS,
        json={"preferred_training_time": "06:00"},
    )
    assert saved.status_code == 200
    assert saved.json()["preferred_training_time"] == "06:00"

    cleared = client.put(
        "/api/push/preferences",
        headers=ATHLETE_HEADERS,
        json={"preferred_training_time": None},
    )
    assert cleared.status_code == 200
    assert cleared.json()["preferred_training_time"] is None


def test_null_boolean_and_quiet_time_are_ignored_without_server_error():
    client, _store, _ = _build_client()

    response = client.put(
        "/api/push/preferences",
        headers=ATHLETE_HEADERS,
        json={"session_reminders": None, "quiet_hours_start": None},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["session_reminders"] is True
    assert payload["quiet_hours_start"] == "22:00"
    assert payload["preferred_training_time"] is None


def test_notification_preferences_validate_quiet_hour_format():
    client, _store, _ = _build_client()
    response = client.put(
        "/api/push/preferences",
        headers=ATHLETE_HEADERS,
        json={"quiet_hours_start": "25:00"},
    )
    assert response.status_code == 422


def test_subscribe_and_unsubscribe_round_trip():
    client, store, _ = _build_client()

    response = client.post(
        "/api/push/subscriptions", headers=ATHLETE_HEADERS, json=_subscribe_payload()
    )
    assert response.status_code == 200
    rows = store.list_push_subscriptions("athlete-1")
    assert len(rows) == 1
    assert rows[0]["endpoint"] == "https://push.example/browser-1"
    assert rows[0]["p256dh"] == "p256dh-key"
    assert rows[0]["timezone"] == "Europe/London"

    removed = client.request(
        "DELETE",
        "/api/push/subscriptions",
        headers=ATHLETE_HEADERS,
        json={"endpoint": "https://push.example/browser-1"},
    )
    assert removed.status_code == 200
    assert store.list_push_subscriptions("athlete-1") == []


def test_resubscribing_same_endpoint_replaces_owner():
    client, store, _ = _build_client()

    first = client.post(
        "/api/push/subscriptions", headers=ATHLETE_HEADERS, json=_subscribe_payload()
    )
    assert first.status_code == 200

    second = client.post(
        "/api/push/subscriptions",
        headers={"Authorization": "Bearer admin-token"},
        json=_subscribe_payload(),
    )
    assert second.status_code == 200
    assert store.list_push_subscriptions("athlete-1") == []
    assert len(store.list_push_subscriptions("admin-1")) == 1


def test_subscribe_rejects_non_https_endpoint():
    client, _store, _ = _build_client()
    response = client.post(
        "/api/push/subscriptions",
        headers=ATHLETE_HEADERS,
        json=_subscribe_payload(endpoint="http://insecure.example/sub"),
    )
    assert response.status_code == 422
