from __future__ import annotations

import importlib

import pytest
from postgrest.exceptions import APIError as PostgrestAPIError
from fastapi.testclient import TestClient

import api.app as app_module
import api.auth as auth_module
import api.store as store_module
from api.app import create_app
from support import FakeAuthService, FakeStage2Automator, FakeStore, _build_client, _build_request, _planner, _now, finalized_result, seed_default_profiles
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


def test_job_response_surfaces_warning_milestones():
    warning = "Profile refresh failed; plan generated from submitted intake only."
    response = app_module._job_response(
        {
            "id": "job_warning",
            "athlete_id": "athlete-1",
            "client_request_id": "client-1",
            "status": "completed",
            "created_at": _now(),
            "updated_at": _now(),
            "started_at": None,
            "completed_at": None,
            "error": None,
            "plan_id": None,
            "progress_milestones": [
                {"code": "profile_refresh_failed_warning", "detail": warning, "meta": {"warning": True}},
                {"code": "profile_refresh_failed_warning_duplicate", "detail": warning, "meta": {"warning": True}},
            ],
        }
    )

    assert response.warnings == [warning]


def test_admin_generation_job_diagnostic_surfaces_warning_milestones():
    warning = "Profile refresh failed; plan generated from submitted intake only."
    diagnostic = app_module._admin_generation_job_diagnostic(
        {
            "id": "job_warning",
            "athlete_id": "athlete-1",
            "client_request_id": "client-1",
            "status": "completed",
            "created_at": _now(),
            "updated_at": _now(),
            "started_at": None,
            "heartbeat_at": None,
            "completed_at": _now(),
            "error": None,
            "plan_id": None,
            "progress_milestones": [
                {"code": "profile_refresh_failed_warning", "detail": warning, "meta": {"warning": True}},
            ],
        },
        stale_after_seconds=90,
    )

    assert diagnostic.warnings == [warning]


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


def test_job_response_recovers_plan_id_from_terminal_milestone_meta_when_plan_exists():
    store = FakeStore()
    seed_default_profiles(store)
    store.create_intake("athlete-1", _build_request())
    intake = store.get_latest_intake("athlete-1")
    assert intake is not None
    plan = store.create_plan(
        athlete_id="athlete-1",
        intake_id=str(intake["id"]),
        request=_build_request(),
        result=finalized_result(),
    )
    response = app_module._job_response(
        {
            "id": "job_terminal_meta",
            "athlete_id": "athlete-1",
            "client_request_id": "client-1",
            "status": "completed",
            "created_at": _now(),
            "updated_at": _now(),
            "started_at": None,
            "completed_at": None,
            "error": None,
            "plan_id": None,
            "progress_milestones": [
                {"code": "plan_persisted", "meta": {"plan_id": plan["id"]}},
            ],
        },
        store=store,
    )

    assert response.plan_id == plan["id"]
    assert response.latest_plan_id == plan["id"]


def test_job_response_ignores_terminal_milestone_plan_id_when_plan_is_missing():
    store = FakeStore()
    response = app_module._job_response(
        {
            "id": "job_terminal_meta_missing_plan",
            "athlete_id": "athlete-1",
            "client_request_id": "client-1",
            "status": "completed",
            "created_at": _now(),
            "updated_at": _now(),
            "started_at": None,
            "completed_at": None,
            "error": None,
            "plan_id": None,
            "progress_milestones": [
                {"code": "plan_persisted", "meta": {"plan_id": "missing_plan_id"}},
            ],
        },
        store=store,
    )

    assert response.plan_id is None
    assert response.latest_plan_id is None


def test_job_response_recovers_plan_id_from_latest_visible_plan_when_terminal_plan_missing():
    store = FakeStore()
    seed_default_profiles(store)
    store.create_intake("athlete-1", _build_request())
    intake = store.get_latest_intake("athlete-1")
    assert intake is not None
    store.create_plan(
        athlete_id="athlete-1",
        intake_id=str(intake["id"]),
        request=_build_request(),
        result=finalized_result(),
    )
    response = app_module._job_response(
        {
            "id": "job_terminal_lookup",
            "athlete_id": "athlete-1",
            "intake_id": str(intake["id"]),
            "client_request_id": "client-1",
            "status": "completed",
            "created_at": _now(),
            "updated_at": _now(),
            "started_at": None,
            "completed_at": None,
            "error": None,
            "plan_id": None,
            "progress_milestones": [],
        },
        store=store,
    )

    assert response.plan_id is not None


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
    monkeypatch.delenv("UNLXCK_GENERATION_WORKER_STALE_AFTER_SECONDS", raising=False)
    monkeypatch.setenv("APP_GENERATION_JOB_STALE_AFTER_SECONDS", "invalid")
    assert app_module._generation_job_stale_after_seconds() == 300


def test_generation_job_stale_after_seconds_defaults_when_unset(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("APP_GENERATION_JOB_STALE_AFTER_SECONDS", raising=False)
    monkeypatch.delenv("UNLXCK_GENERATION_WORKER_STALE_AFTER_SECONDS", raising=False)
    assert app_module._generation_job_stale_after_seconds() == 300


def test_generation_job_stale_after_seconds_falls_back_to_worker_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("APP_GENERATION_JOB_STALE_AFTER_SECONDS", raising=False)
    monkeypatch.setenv("UNLXCK_GENERATION_WORKER_STALE_AFTER_SECONDS", "420")
    assert app_module._generation_job_stale_after_seconds() == 420


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


def test_default_planner_forwards_progress_callback_to_runtime_planner(monkeypatch: pytest.MonkeyPatch):
    seen: dict[str, object] = {}

    def fake_runtime_default_planner(payload, *, progress_callback=None):
        seen["payload"] = payload
        seen["progress_callback"] = progress_callback
        return {"ok": True}

    monkeypatch.setattr(app_module, "runtime_default_planner", fake_runtime_default_planner)

    def callback(code, label, detail, meta):
        return None

    result = app_module._default_planner({"athlete": "x"}, progress_callback=callback)

    assert result == {"ok": True}
    assert seen["payload"] == {"athlete": "x"}
    assert seen["progress_callback"] is callback


def test_runtime_app_falls_back_to_health_endpoint_when_supabase_config_missing(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("UNLXCK_ENV", raising=False)
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    monkeypatch.delenv("SUPABASE_ANON_KEY", raising=False)

    reloaded = importlib.reload(app_module)

    client = TestClient(reloaded.app)
    expected_body = {
        "ok": False,
        "app": "unlxck-fight-camp-api",
        "detail": "missing supabase configuration",
    }

    health_response = client.get("/health")
    assert health_response.status_code == 503
    assert health_response.json() == expected_body

    root_response = client.get("/")
    assert root_response.status_code == 503
    assert root_response.json() == expected_body

    head_response = client.head("/")
    assert head_response.status_code == 503


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
        "detail": "service temporarily unavailable",
    }


def test_runtime_app_returns_startup_failure_when_schema_check_times_out(
    monkeypatch: pytest.MonkeyPatch,
):
    class TimeoutStore(FakeStore):
        def validate_runtime_schema(self) -> None:
            raise RuntimeError("store service temporarily unavailable")

    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
    monkeypatch.setattr(store_module.SupabaseAppStore, "from_env", classmethod(lambda cls: TimeoutStore()))
    monkeypatch.setattr(
        auth_module.SupabaseAuthService,
        "from_env",
        classmethod(lambda cls: FakeAuthService({})),
    )

    reloaded = importlib.reload(app_module)
    client = TestClient(reloaded.app)
    response = client.get("/health")

    assert response.status_code == 503
    assert response.json() == {
        "ok": False,
        "app": "unlxck-fight-camp-api",
        "detail": "service temporarily unavailable",
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
    assert response.json()["detail"] == "service temporarily unavailable"
def test_runtime_app_does_not_fail_schema_check_when_legacy_fallback_enabled(
    monkeypatch: pytest.MonkeyPatch,
):
    class SchemaCheckingStore(FakeStore):
        def validate_runtime_schema(self) -> None:
            if store_module._is_production_environment():
                raise RuntimeError(store_module.PLAN_RUNTIME_SCHEMA_ERROR_DETAIL)
            if app_module.os.getenv("UNLXCK_ALLOW_LEGACY_PLAN_SCHEMA_FALLBACK") == "1":
                return
            raise RuntimeError(store_module.PLAN_RUNTIME_SCHEMA_ERROR_DETAIL)

    for var in ("APP_ENV", "ENVIRONMENT", "UNLXCK_ENV", "NODE_ENV"):
        monkeypatch.delenv(var, raising=False)
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


def test_runtime_app_fails_in_production_even_when_legacy_fallback_flag_set(
    monkeypatch: pytest.MonkeyPatch,
):
    class SchemaCheckingStore(FakeStore):
        def validate_runtime_schema(self) -> None:
            # Mirror real SupabaseAppStore: production blocks fallback.
            if store_module._is_production_environment():
                raise RuntimeError(store_module.PLAN_RUNTIME_SCHEMA_ERROR_DETAIL)
            if app_module.os.getenv("UNLXCK_ALLOW_LEGACY_PLAN_SCHEMA_FALLBACK") == "1":
                return
            raise RuntimeError(store_module.PLAN_RUNTIME_SCHEMA_ERROR_DETAIL)

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("UNLXCK_ALLOW_LEGACY_PLAN_SCHEMA_FALLBACK", "1")
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
        "detail": "service temporarily unavailable",
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


def _clear_env_detection_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ("APP_ENV", "ENVIRONMENT", "UNLXCK_ENV", "NODE_ENV"):
        monkeypatch.delenv(var, raising=False)


def test_production_cors_allows_safe_https_origin(monkeypatch: pytest.MonkeyPatch):
    _clear_env_detection_vars(monkeypatch)
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("APP_CORS_ORIGINS", "https://app.example.com")
    # Should not raise
    create_app(
        store=FakeStore(),
        auth_service=FakeAuthService({}),
        stage2_automator=FakeStage2Automator(),
    )


def test_production_cors_fails_fast_on_unsafe_origin_by_default(
    monkeypatch: pytest.MonkeyPatch,
):
    _clear_env_detection_vars(monkeypatch)
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("APP_CORS_ORIGINS", "*")

    with pytest.raises(ValueError, match="Refusing to boot with unsafe production CORS"):
        create_app(
            store=FakeStore(),
            auth_service=FakeAuthService({}),
            stage2_automator=FakeStage2Automator(),
        )


def test_production_cors_rejects_empty_origins(monkeypatch: pytest.MonkeyPatch):
    _clear_env_detection_vars(monkeypatch)
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("APP_CORS_ORIGINS", "")
    monkeypatch.delenv("APP_CORS_ORIGIN_REGEX", raising=False)

    with pytest.raises(ValueError, match="at least one origin"):
        create_app(
            store=FakeStore(),
            auth_service=FakeAuthService({}),
            stage2_automator=FakeStage2Automator(),
        )


def test_production_cors_rejects_localhost_origins(monkeypatch: pytest.MonkeyPatch):
    _clear_env_detection_vars(monkeypatch)
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("APP_CORS_ORIGINS", "http://localhost:3000")

    with pytest.raises(ValueError, match="localhost"):
        create_app(
            store=FakeStore(),
            auth_service=FakeAuthService({}),
            stage2_automator=FakeStage2Automator(),
        )


@pytest.mark.parametrize(
    "regex",
    [
        ".*",
        "^.*$",
        ".+",
        "^.+$",
        "https://.*",
        "^https://.*$",
        "https://.+",
        "^https://.+$",
        "http://.*",
        "^http://.*$",
        "http://.+",
        "^http://.+$",
    ],
)
def test_production_cors_strict_mode_rejects_broad_regex(monkeypatch: pytest.MonkeyPatch, regex: str):
    _clear_env_detection_vars(monkeypatch)
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("APP_CORS_ORIGINS", "https://app.example.com")
    monkeypatch.setenv("APP_CORS_ORIGIN_REGEX", regex)

    with pytest.raises(ValueError, match="too broad"):
        create_app(
            store=FakeStore(),
            auth_service=FakeAuthService({}),
            stage2_automator=FakeStage2Automator(),
        )


def test_production_cors_allows_narrow_subdomain_regex(monkeypatch: pytest.MonkeyPatch):
    """Narrow regex constrained to a specific domain should still work in production."""
    _clear_env_detection_vars(monkeypatch)
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("APP_CORS_ORIGINS", "https://app.example.com")
    monkeypatch.setenv("APP_CORS_ORIGIN_REGEX", r"https://.*\.vercel\.app")
    # Should not raise
    create_app(
        store=FakeStore(),
        auth_service=FakeAuthService({}),
        stage2_automator=FakeStage2Automator(),
    )


def test_non_production_cors_allows_localhost(monkeypatch: pytest.MonkeyPatch):
    _clear_env_detection_vars(monkeypatch)
    monkeypatch.setenv("APP_CORS_ORIGINS", "http://localhost:3000")
    # Should not raise
    create_app(
        store=FakeStore(),
        auth_service=FakeAuthService({}),
        stage2_automator=FakeStage2Automator(),
    )


def test_auth_success_log_uses_safe_identifiers(caplog):
    client, _, _ = _build_client()

    with caplog.at_level("INFO", logger="api.app"):
        response = client.get("/api/me", headers={"Authorization": "Bearer athlete-token"})

    assert response.status_code == 200
    messages = [record.getMessage() for record in caplog.records]
    assert any("token_resolved" in message for message in messages)
    assert "ari@example.com" not in caplog.text
    assert "email=" not in caplog.text
    token_record = next(record for record in caplog.records if "token_resolved" in record.getMessage())
    assert token_record.athlete_id == "athlete-1"
    assert token_record.auth_event == "token_resolved"
    assert token_record.status == "success"


def test_request_logs_omit_personal_request_body_fields(caplog):
    client, _, _ = _build_client()

    with caplog.at_level("INFO", logger="api.app"):
        response = client.post(
            "/api/plans/generate",
            json={"email": "private@example.com", "full_name": "Private User"},
        )

    assert response.status_code == 401
    assert "private@example.com" not in caplog.text
    assert "full_name" not in caplog.text
    assert "authentication_required" in caplog.text
