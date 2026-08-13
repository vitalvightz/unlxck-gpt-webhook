from __future__ import annotations

from datetime import datetime, timezone

from api.routes import push as push_routes
from api.services.notification_foundation import record_notification_evaluation
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


def test_notification_diagnostics_is_admin_only_and_filterable():
    client, store, _ = _build_client()
    record_notification_evaluation(
        store,
        profile_id="athlete-1",
        training_day="2026-08-12",
        intent="session_preparation",
        now_utc=datetime(2026, 8, 12, 15, 0, tzinfo=timezone.utc),
        decision="not_applicable",
        rejection_reasons=("low_timing_confidence",),
    )
    path = (
        "/api/admin/notifications/diagnostics?athlete_id=athlete-1"
        "&training_day=2026-08-12&intent=session_preparation"
    )
    assert client.get(path, headers=ATHLETE_HEADERS).status_code == 403
    response = client.get(path, headers=ADMIN_HEADERS)
    assert response.status_code == 200
    payload = response.json()
    assert payload["intent"] == "session_preparation"
    assert payload["evaluations"][0]["rejection_reasons"] == ["low_timing_confidence"]
