from __future__ import annotations

import asyncio
import importlib
import threading

import pytest
from fastapi.testclient import TestClient

import api.app as app_module
import api.auth as auth_module
import api.store as store_module
from api.app import create_app
from api_test_support import FakeAuthService, FakeStage2Automator, FakeStore, _build_client, _planner, _now, finalized_result
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


def test_run_stage1_planner_uses_worker_thread():
    main_thread_id = threading.get_ident()
    seen_thread_ids: list[int] = []

    async def planner(payload: dict) -> dict:
        seen_thread_ids.append(threading.get_ident())
        return {"payload": payload}

    result = asyncio.run(app_module._run_stage1_planner(planner, {"athlete": "demo"}))

    assert result == {"payload": {"athlete": "demo"}}
    assert seen_thread_ids
    assert seen_thread_ids[0] != main_thread_id


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


def test_request_middleware_rejects_oversized_request_bodies(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("APP_MAX_REQUEST_BODY_BYTES", "16")
    app = create_app(
        store=FakeStore(),
        auth_service=FakeAuthService({}),
        planner=_planner,
        stage2_automator=FakeStage2Automator(result=finalized_result()),
    )

    @app.post("/echo")
    async def echo(request):
        return {"size": len(await request.body())}

    client = TestClient(app, raise_server_exceptions=False)

    response = client.post("/echo", content=b"x" * 32)

    assert response.status_code == 413
    assert response.json()["detail"] == "Request body too large"
    assert response.json()["request_id"] == response.headers["x-request-id"]


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


def test_runtime_app_falls_back_to_health_endpoint_when_supabase_config_missing(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("UNLXCK_DEMO_MODE", raising=False)
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    monkeypatch.delenv("SUPABASE_ANON_KEY", raising=False)

    reloaded = importlib.reload(app_module)

    client = TestClient(reloaded.app)
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "ok": False,
        "app": "unlxck-fight-camp-api",
        "detail": "missing supabase configuration",
    }


@pytest.mark.parametrize(
    ("use_demo_mode", "env_value"),
    [
        (True, "://bad-origin"),
        (False, "http:///missing-host"),
    ],
)
def test_runtime_app_falls_back_to_health_endpoint_when_runtime_config_is_invalid(
    monkeypatch: pytest.MonkeyPatch,
    use_demo_mode: bool,
    env_value: str,
):
    if use_demo_mode:
        monkeypatch.setenv("UNLXCK_DEMO_MODE", "1")
    else:
        monkeypatch.delenv("UNLXCK_DEMO_MODE", raising=False)
        monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
        monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
        monkeypatch.setattr(store_module.SupabaseAppStore, "from_env", classmethod(lambda cls: FakeStore()))
        monkeypatch.setattr(auth_module.SupabaseAuthService, "from_env", classmethod(lambda cls: FakeAuthService({})))

    monkeypatch.setenv("APP_CORS_ORIGINS", env_value)

    reloaded = importlib.reload(app_module)

    client = TestClient(reloaded.app)
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "ok": False,
        "app": "unlxck-fight-camp-api",
        "detail": "application startup failed",
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
    monkeypatch.setenv("APP_CORS_ORIGIN_REGEX", r"https://unlxck-gpt-webhook(?:-git-[^.]+)?\.vercel\.app")
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


def test_cors_origin_regex_rejects_broad_wildcards(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("APP_CORS_ORIGIN_REGEX", r"https://.*\.vercel\.app")

    with pytest.raises(ValueError, match="APP_CORS_ORIGIN_REGEX"):
        app_module._cors_origin_regex()


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
