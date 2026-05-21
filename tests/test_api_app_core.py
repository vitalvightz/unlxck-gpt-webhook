from __future__ import annotations

import importlib

import pytest
from postgrest.exceptions import APIError as PostgrestAPIError
from fastapi.testclient import TestClient

import api.app as app_module
import api.auth as auth_module
import api.store as store_module
from api.app import create_app
from support import FakeAuthService, FakeStage2Automator, FakeStore, _build_client, _planner, _now, finalized_result
from conftest import RENDER_BACKEND_URL


def test_create_app_primes_plan_banks_on_startup(monkeypatch):
    calls: list[object] = []

    def _fake_prime_plan_banks(*, logger=None):
        calls.append(logger)

    monkeypatch.setattr(app_module, "prime_plan_banks", _fake_prime_plan_banks)

    app = create_app(
        store=FakeStore(),
        auth_service=FakeAuthService({}),
        stage2_automator=FakeStage2Automator(),
    )

    with TestClient(app):
        pass

    assert len(calls) == 1
    assert calls[0] is app_module.logger


def test_root_and_health_return_ok_for_render_probes():
    app = create_app(
        store=FakeStore(),
        auth_service=FakeAuthService({}),
        stage2_automator=FakeStage2Automator(),
        mode_label="test",
    )

    with TestClient(app) as client:
        head_response = client.head("/")
        root_response = client.get("/")
        health_response = client.get("/health")

    assert head_response.status_code == 200
    assert root_response.status_code == 200
    assert root_response.json() == {
        "ok": True,
        "app": "unlxck-fight-camp-api",
        "mode": "test",
    }
    assert health_response.status_code == 200
    assert health_response.json() == root_response.json()


def test_auth_is_required_for_me_route():
    client, _, _ = _build_client()

    response = client.get("/api/me")

    assert response.status_code == 401


def test_request_id_header_is_attached_to_error_responses():
    client, _, _ = _build_client()

    response = client.get("/api/me")

    assert response.status_code == 401
    assert response.json()["request_id"] == response.headers["x-request-id"]
    assert len(response.headers["x-request-id"]) == 8


def test_request_middleware_returns_json_request_id_for_unhandled_exceptions():
    app = create_app(
        store=FakeStore(),
        auth_service=FakeAuthService({}),
        planner=_planner,
        stage2_automator=FakeStage2Automator(result=finalized_result()),
    )

    @app.get("/boom")
    def boom():
        raise RuntimeError("boom")

    client = TestClient(app, raise_server_exceptions=False)

    response = client.get("/boom")

    assert response.status_code == 500
    assert response.json()["detail"] == "Internal server error"
    assert response.json()["request_id"] == response.headers["x-request-id"]
    assert len(response.json()["request_id"]) == 8


def test_job_response_falls_back_to_created_at_when_updated_at_is_missing():
    created_at = _now()
    response = app_module._job_response(
        {
            "id": "job_legacy123",
            "athlete_id": "athlete-1",
            "client_request_id": "client-1",
            "status": "queued",
            "created_at": created_at,
            "updated_at": None,
            "started_at": None,
            "completed_at": None,
            "error": None,
            "plan_id": None,
        }
    )

    assert response.created_at == created_at
    assert response.updated_at == created_at


def test_is_stale_job_does_not_flag_new_running_job_without_heartbeat():
    started_at = _now()

    assert (
        app_module._is_stale_job(
            {
                "status": "running",
                "started_at": started_at,
                "heartbeat_at": None,
            },
            stale_after_seconds=90,
        )
        is False
    )


def test_is_stale_job_uses_started_at_when_heartbeat_is_missing_for_old_running_job():
    assert (
        app_module._is_stale_job(
            {
                "status": "running",
                "started_at": "2026-01-01T00:00:00+00:00",
                "heartbeat_at": None,
            },
            stale_after_seconds=90,
        )
        is True
    )


def test_generation_job_stale_after_seconds_defaults_when_env_invalid(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("APP_GENERATION_JOB_STALE_AFTER_SECONDS", "invalid")
    assert app_module._generation_job_stale_after_seconds() == 1400


def test_generation_job_stale_after_seconds_defaults_when_unset(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("APP_GENERATION_JOB_STALE_AFTER_SECONDS", raising=False)
    assert app_module._generation_job_stale_after_seconds() == 1400


def test_generation_job_stale_after_seconds_enforces_minimum(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("APP_GENERATION_JOB_STALE_AFTER_SECONDS", "30")
    assert app_module._generation_job_stale_after_seconds() == 60


def test_plan_generate_daily_limit_defaults_when_unset(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("APP_PLAN_GENERATE_DAILY_LIMIT_PER_USER", raising=False)
    assert app_module._plan_generate_daily_limit_per_user() == 5


def test_plan_generate_daily_limit_defaults_when_invalid(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("APP_PLAN_GENERATE_DAILY_LIMIT_PER_USER", "not-a-number")
    assert app_module._plan_generate_daily_limit_per_user() == 5


def test_plan_generate_daily_limit_zero_disables_cap(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("APP_PLAN_GENERATE_DAILY_LIMIT_PER_USER", "0")
    assert app_module._plan_generate_daily_limit_per_user() == 0


def test_runtime_app_falls_back_to_health_endpoint_when_supabase_config_missing(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("UNLXCK_ENV", raising=False)
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    monkeypatch.delenv("SUPABASE_ANON_KEY", raising=False)

    reloaded = importlib.reload(app_module)

    client = TestClient(reloaded.app)
    response = client.get("/health")

    assert response.status_code == 503
    assert response.json() == {
        "ok": False,
        "app": "unlxck-fight-camp-api",
        "detail": "missing supabase configuration",
    }


def test_runtime_app_uses_supabase_store_and_auth(monkeypatch: pytest.MonkeyPatch):
    calls: list[str] = []

    class RuntimeStore(FakeStore):
        def validate_runtime_schema(self) -> None:
            calls.append("validate_runtime_schema")

    def fake_store_from_env(cls):
        calls.append("store_from_env")
        return RuntimeStore()

    def fake_auth_from_env(cls):
        calls.append("auth_from_env")
        return FakeAuthService({})

    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
    monkeypatch.setattr(store_module.SupabaseAppStore, "from_env", classmethod(fake_store_from_env))
    monkeypatch.setattr(auth_module.SupabaseAuthService, "from_env", classmethod(fake_auth_from_env))

    reloaded = importlib.reload(app_module)
    client = TestClient(reloaded.app)
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "app": "unlxck-fight-camp-api",
        "mode": "supabase-authenticated",
    }
    assert calls == ["store_from_env", "validate_runtime_schema", "auth_from_env"]


@pytest.mark.parametrize(
    ("env_value",),
    [("://bad-origin",), ("http:///missing-host",)],
)
def test_runtime_app_falls_back_to_health_endpoint_when_runtime_config_is_invalid(
    monkeypatch: pytest.MonkeyPatch,
    env_value: str,
):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
    monkeypatch.setattr(store_module.SupabaseAppStore, "from_env", classmethod(lambda cls: FakeStore()))
    monkeypatch.setattr(auth_module.SupabaseAuthService, "from_env", classmethod(lambda cls: FakeAuthService({})))

    monkeypatch.setenv("APP_CORS_ORIGINS", env_value)

    reloaded = importlib.reload(app_module)

    client = TestClient(reloaded.app)
    response = client.get("/health")

    assert response.status_code == 503
    assert response.json() == {
        "ok": False,
        "app": "unlxck-fight-camp-api",
        "detail": "application startup failed",
    }


def test_runtime_app_fails_loudly_when_plan_schema_is_invalid_and_fallback_disabled(
    monkeypatch: pytest.MonkeyPatch,
):
    class SchemaCheckingStore(FakeStore):
        def validate_runtime_schema(self) -> None:
            if app_module.os.getenv("UNLXCK_ALLOW_LEGACY_PLAN_SCHEMA_FALLBACK") == "1":
                return
            raise RuntimeError(store_module.PLAN_RUNTIME_SCHEMA_ERROR_DETAIL)

        monkeypatch.delenv("UNLXCK_ALLOW_LEGACY_PLAN_SCHEMA_FALLBACK", raising=False)
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
    monkeypatch.setattr(store_module.SupabaseAppStore, "from_env", classmethod(lambda cls: SchemaCheckingStore()))
    monkeypatch.setattr(auth_module.SupabaseAuthService, "from_env", classmethod(lambda cls: FakeAuthService({})))

    reloaded = importlib.reload(app_module)
    client = TestClient(reloaded.app)
    response = client.get("/health")

    assert response.status_code == 503
    assert response.json() == {
        "ok": False,
        "app": "unlxck-fight-camp-api",
        "detail": store_module.PLAN_RUNTIME_SCHEMA_ERROR_DETAIL,
    }
def test_runtime_app_returns_startup_failure_when_store_is_restricted(
    monkeypatch: pytest.MonkeyPatch,
):
    class RestrictedStore(FakeStore):
        def validate_runtime_schema(self) -> None:
            raise PostgrestAPIError(
                {
                    "message": "JSON could not be generated",
                    "code": "402",
                    "details": "project restricted due to exceed_egress_quota",
                }
            )

        monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
    monkeypatch.setattr(store_module.SupabaseAppStore, "from_env", classmethod(lambda cls: RestrictedStore()))
    monkeypatch.setattr(auth_module.SupabaseAuthService, "from_env", classmethod(lambda cls: FakeAuthService({})))

    reloaded = importlib.reload(app_module)
    client = TestClient(reloaded.app)
    response = client.get("/health")

    assert response.status_code == 503
    assert response.json()["ok"] is False
    assert response.json()["app"] == "unlxck-fight-camp-api"
    assert "JSON could not be generated" in response.json()["detail"]
def test_runtime_app_does_not_fail_schema_check_when_legacy_fallback_enabled(
    monkeypatch: pytest.MonkeyPatch,
):
    class SchemaCheckingStore(FakeStore):
        def validate_runtime_schema(self) -> None:
            if app_module.os.getenv("UNLXCK_ALLOW_LEGACY_PLAN_SCHEMA_FALLBACK") == "1":
                return
            raise RuntimeError(store_module.PLAN_RUNTIME_SCHEMA_ERROR_DETAIL)

        monkeypatch.setenv("UNLXCK_ALLOW_LEGACY_PLAN_SCHEMA_FALLBACK", "1")
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
    monkeypatch.setattr(store_module.SupabaseAppStore, "from_env", classmethod(lambda cls: SchemaCheckingStore()))
    monkeypatch.setattr(auth_module.SupabaseAuthService, "from_env", classmethod(lambda cls: FakeAuthService({})))

    reloaded = importlib.reload(app_module)
    client = TestClient(reloaded.app)
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "app": "unlxck-fight-camp-api",
        "mode": "supabase-authenticated",
    }


def test_cors_allows_normalized_production_origin(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("APP_CORS_ORIGINS", "https://unlxck-gpt-webhook.vercel.app/onboarding/")
    client, _, _ = _build_client()

    response = client.options(
        "/api/plans/generate",
        headers={
            "Origin": "https://unlxck-gpt-webhook.vercel.app",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://unlxck-gpt-webhook.vercel.app"


def test_cors_allows_regex_configured_preview_origin(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("APP_CORS_ORIGIN_REGEX", r"https://.*\.vercel\.app")
    client, _, _ = _build_client()

    response = client.options(
        "/api/plans/generate",
        headers={
            "Origin": "https://unlxck-gpt-webhook-git-feature-branch.vercel.app",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert response.status_code == 200
    assert (
        response.headers["access-control-allow-origin"]
        == "https://unlxck-gpt-webhook-git-feature-branch.vercel.app"
    )


def test_cors_allows_host_only_origin_configuration(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("APP_CORS_ORIGINS", "unlxck-gpt-webhook.vercel.app")
    client, _, _ = _build_client()

    response = client.options(
        "/api/plans/generate",
        headers={
            "Origin": "https://unlxck-gpt-webhook.vercel.app",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://unlxck-gpt-webhook.vercel.app"


def test_cors_does_not_allow_render_origin_when_only_vercel_origin_is_configured(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("APP_CORS_ORIGINS", "https://unlxck-gpt-webhook.vercel.app")
    client, _, _ = _build_client()

    response = client.options(
        "/api/plans/generate",
        headers={
            "Origin": RENDER_BACKEND_URL,
            "Access-Control-Request-Method": "POST",
        },
    )

    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers
