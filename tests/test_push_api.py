from __future__ import annotations

from support import _build_client

ATHLETE_HEADERS = {"Authorization": "Bearer athlete-token"}


def _subscribe_payload(endpoint: str = "https://push.example/browser-1") -> dict:
    return {
        "endpoint": endpoint,
        "keys": {"p256dh": "p256dh-key", "auth": "auth-key"},
        "timezone": "Europe/London",
    }


def test_push_settings_reports_server_configuration(monkeypatch):
    client, _store, _ = _build_client()

    monkeypatch.delenv("UNLXCK_VAPID_PRIVATE_KEY", raising=False)
    monkeypatch.delenv("UNLXCK_VAPID_PUBLIC_KEY", raising=False)
    disabled = client.get("/api/push/settings", headers=ATHLETE_HEADERS)
    assert disabled.status_code == 200
    assert disabled.json() == {"enabled": False, "public_key": ""}

    monkeypatch.setenv("UNLXCK_VAPID_PRIVATE_KEY", "private")
    monkeypatch.setenv("UNLXCK_VAPID_PUBLIC_KEY", "public-key")
    enabled = client.get("/api/push/settings", headers=ATHLETE_HEADERS)
    assert enabled.status_code == 200
    assert enabled.json() == {"enabled": True, "public_key": "public-key"}


def test_push_settings_requires_auth():
    client, _store, _ = _build_client()
    assert client.get("/api/push/settings").status_code in (401, 403)


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
    # A shared-device endpoint follows its current owner: the previous account
    # must never keep receiving pushes on this browser install.
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
