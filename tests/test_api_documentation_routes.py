from fastapi.testclient import TestClient

import api.app as app_module
from api.app import create_app
from support import FakeAuthService, FakeStore


ENVIRONMENT_MARKERS = ("APP_ENV", "ENVIRONMENT", "UNLXCK_ENV", "NODE_ENV")
DOCUMENTATION_ROUTES = ("/docs", "/redoc", "/openapi.json")


def _clear_environment_markers(monkeypatch) -> None:
    for variable in ENVIRONMENT_MARKERS:
        monkeypatch.delenv(variable, raising=False)


def _build_main_client() -> TestClient:
    app = create_app(
        store=FakeStore(),
        auth_service=FakeAuthService({}),
        mode_label="test",
        enable_in_process_generation=False,
    )
    return TestClient(app)


def test_main_application_disables_documentation_in_production(monkeypatch):
    _clear_environment_markers(monkeypatch)
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("APP_CORS_ORIGINS", "https://app.example.com")
    client = _build_main_client()

    for route in DOCUMENTATION_ROUTES:
        assert client.get(route).status_code == 404

    assert client.get("/health").status_code == 200
    assert client.get("/api/me").status_code == 401


def test_main_application_keeps_documentation_outside_production(monkeypatch):
    _clear_environment_markers(monkeypatch)
    client = _build_main_client()

    for route in DOCUMENTATION_ROUTES:
        assert client.get(route).status_code == 200

    assert client.get("/health").status_code == 200
    assert client.get("/api/me").status_code == 401


def test_startup_failure_application_disables_documentation_in_production(monkeypatch):
    _clear_environment_markers(monkeypatch)
    monkeypatch.setenv("UNLXCK_ENV", "live")
    client = TestClient(app_module._build_startup_failure_app("test failure"))

    for route in DOCUMENTATION_ROUTES:
        assert client.get(route).status_code == 404

    health_response = client.get("/health")
    assert health_response.status_code == 503
    assert health_response.json()["detail"] == "test failure"


def test_documentation_options_delegate_to_existing_environment_helper(monkeypatch):
    calls = 0

    def _production_environment() -> bool:
        nonlocal calls
        calls += 1
        return True

    monkeypatch.setattr(app_module, "is_production_environment", _production_environment)

    assert app_module._fastapi_documentation_options() == {
        "docs_url": None,
        "redoc_url": None,
        "openapi_url": None,
    }
    assert calls == 1
