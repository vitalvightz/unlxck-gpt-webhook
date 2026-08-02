from __future__ import annotations

from api.routes import push as push_routes
from support import _build_client

ATHLETE_HEADERS = {"Authorization": "Bearer athlete-token"}
ADMIN_HEADERS = {"Authorization": "Bearer admin-token"}


def _payload() -> dict:
    return {
        "athlete_id": "athlete-1",
        "message_id": "coach-note-1",
        "title": "One change for today",
        "body": "Keep the final round technical. Open Today before training.",
        "url": "/today#today-session",
        "urgent": False,
    }


def test_coach_message_requires_effective_admin(monkeypatch):
    client, store, _ = _build_client()
    captured: list[dict] = []
    monkeypatch.setattr(
        push_routes,
        "send_coach_message_notification",
        lambda *_args, **kwargs: captured.append(kwargs) or 1,
    )

    denied = client.post(
        "/api/admin/notifications/coach-message",
        headers=ATHLETE_HEADERS,
        json=_payload(),
    )
    assert denied.status_code == 403

    malformed = client.post(
        "/api/admin/notifications/coach-message",
        headers=ATHLETE_HEADERS,
        json={},
    )
    assert malformed.status_code == 403

    store.profiles["athlete-1"]["athlete_timezone"] = "Europe/London"

    allowed = client.post(
        "/api/admin/notifications/coach-message",
        headers=ADMIN_HEADERS,
        json=_payload(),
    )
    assert allowed.status_code == 200
    assert allowed.json() == {"ok": True, "delivered_count": 1}
    assert captured == [{**_payload(), "timezone_name": "Europe/London"}]


def test_coach_message_rejects_external_or_oversized_copy():
    client, _store, _ = _build_client()
    external = client.post(
        "/api/admin/notifications/coach-message",
        headers=ADMIN_HEADERS,
        json={**_payload(), "url": "https://example.com"},
    )
    assert external.status_code == 422

    oversized = client.post(
        "/api/admin/notifications/coach-message",
        headers=ADMIN_HEADERS,
        json={**_payload(), "title": "x" * 41},
    )
    assert oversized.status_code == 422
