from __future__ import annotations

from fastapi.testclient import TestClient

from api.app import create_app
from api.sentry_config import scrub_sentry_event
from support import FakeAuthService, FakeStage2Automator, FakeStore


def test_scrub_sentry_event_removes_sensitive_request_data():
    event = {
        "request": {
            "headers": {
                "authorization": "Bearer secret-token",
                "cookie": "session=secret",
                "x-request-id": "request-1",
            },
            "data": {
                "athlete": {
                    "name": "Athlete Name",
                    "email": "athlete@example.com",
                    "injuries": "shoulder pain",
                },
                "prompt": "raw planner prompt",
            },
        },
        "extra": {
            "programme": "generated programme contents",
            "safe_value": "kept",
        },
    }

    scrubbed = scrub_sentry_event(event)

    assert scrubbed["request"]["headers"]["authorization"] == "[Filtered]"
    assert scrubbed["request"]["headers"]["cookie"] == "[Filtered]"
    assert scrubbed["request"]["headers"]["x-request-id"] == "request-1"
    assert "data" not in scrubbed["request"]
    assert scrubbed["extra"]["programme"] == "[Filtered]"
    assert scrubbed["extra"]["safe_value"] == "kept"


def test_sentry_debug_route_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv("ENABLE_SENTRY_DEBUG_ROUTE", raising=False)
    app = create_app(
        store=FakeStore(),
        auth_service=FakeAuthService({}),
        stage2_automator=FakeStage2Automator(),
    )
    client = TestClient(app, raise_server_exceptions=False)

    response = client.get("/sentry-debug")

    assert response.status_code == 404


def test_sentry_debug_route_can_be_enabled(monkeypatch):
    monkeypatch.setenv("ENABLE_SENTRY_DEBUG_ROUTE", "true")
    app = create_app(
        store=FakeStore(),
        auth_service=FakeAuthService({}),
        stage2_automator=FakeStage2Automator(),
    )
    client = TestClient(app, raise_server_exceptions=False)

    response = client.get("/sentry-debug")

    assert response.status_code == 500
    assert response.json()["detail"] == "Internal server error"
