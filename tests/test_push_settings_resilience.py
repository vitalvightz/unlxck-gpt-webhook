from __future__ import annotations

from support import _build_client

ATHLETE_HEADERS = {"Authorization": "Bearer athlete-token"}


def test_push_settings_preserves_unknown_state_when_subscription_lookup_fails(monkeypatch):
    client, store, _ = _build_client()
    monkeypatch.setenv("UNLXCK_VAPID_PRIVATE_KEY", "private")
    monkeypatch.setenv("UNLXCK_VAPID_PUBLIC_KEY", "public-key")

    def fail_subscription_lookup(_profile_id: str):
        raise RuntimeError("temporary push subscription store failure")

    monkeypatch.setattr(store, "list_push_subscriptions", fail_subscription_lookup)

    response = client.get("/api/push/settings", headers=ATHLETE_HEADERS)

    assert response.status_code == 200
    payload = response.json()
    assert payload["enabled"] is True
    assert payload["public_key"] == "public-key"
    assert payload["subscription_endpoints"] is None
