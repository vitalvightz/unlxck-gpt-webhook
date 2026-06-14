"""Tests for SupabaseAppStore profile bootstrap role assignment and retry logic."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import httpx
import pytest
from fastapi import HTTPException, status
from postgrest.exceptions import APIError

import api.store as store_module
from support import _build_request
from api.auth import AuthenticatedUser
from api.generation_config import generation_worker_id
from api.store import SupabaseAppStore


def _make_store(admin_emails: set[str] | None = None) -> SupabaseAppStore:
    """Create a SupabaseAppStore with a mock Supabase client."""
    return SupabaseAppStore(client=MagicMock(), admin_emails=admin_emails or set())


def _user(email: str, user_id: str = "uid-1") -> AuthenticatedUser:
    return AuthenticatedUser(
        user_id=user_id,
        email=email,
        full_name="Test User",
        metadata={},
    )


def _configure_profile_reads(store: SupabaseAppStore, *rows: dict | None) -> None:
    responses = []
    for row in rows:
        response = MagicMock()
        response.data = [row] if row else []
        responses.append(response)
    (
        store.client.table.return_value.select.return_value.eq.return_value.limit.return_value.execute
    ).side_effect = responses


# ---------------------------------------------------------------------------
# _default_role_for tests
# ---------------------------------------------------------------------------


def test_default_role_is_athlete_for_unknown_email():
    store = _make_store(admin_emails={"boss@example.com"})
    user = _user("regular@example.com")
    assert store._default_role_for(user) == "athlete"



def test_default_role_is_admin_for_configured_admin_email():
    store = _make_store(admin_emails={"boss@example.com"})
    user = _user("boss@example.com")
    assert store._default_role_for(user) == "admin"



def test_default_role_admin_email_check_is_case_insensitive():
    store = _make_store(admin_emails={"boss@example.com"})
    user = _user("BOSS@EXAMPLE.COM")
    assert store._default_role_for(user) == "admin"


def test_default_role_admin_email_check_trims_whitespace():
    store = _make_store(admin_emails={"boss@example.com"})
    user = _user("  boss@example.com  ")
    assert store._default_role_for(user) == "admin"



def test_default_role_athlete_when_no_admin_emails_configured():
    store = _make_store(admin_emails=set())
    user = _user("anyone@example.com")
    assert store._default_role_for(user) == "athlete"


# ---------------------------------------------------------------------------
# ensure_profile role assignment via mocked Supabase client
# ---------------------------------------------------------------------------


def test_ensure_profile_new_user_gets_athlete_role():
    store = _make_store(admin_emails=set())
    user = _user("newbie@example.com")

    expected_profile = {
        "id": user.user_id,
        "email": user.email,
        "role": "athlete",
        "full_name": user.full_name,
    }
    _configure_profile_reads(store, None, expected_profile)
    store.client.table.return_value.upsert.return_value.execute.return_value = MagicMock()

    result = store.ensure_profile(user)

    call_args = store.client.table.return_value.upsert.call_args
    payload = call_args[0][0]
    assert payload["role"] == "athlete"
    assert result["role"] == "athlete"



def test_ensure_profile_new_admin_email_gets_admin_role():
    store = _make_store(admin_emails={"boss@example.com"})
    user = _user("boss@example.com")

    expected_profile = {
        "id": user.user_id,
        "email": user.email,
        "role": "admin",
        "full_name": user.full_name,
    }
    _configure_profile_reads(store, None, expected_profile)
    store.client.table.return_value.upsert.return_value.execute.return_value = MagicMock()

    store.ensure_profile(user)

    call_args = store.client.table.return_value.upsert.call_args
    payload = call_args[0][0]
    assert payload["role"] == "admin"



def test_ensure_profile_existing_user_returns_without_upsert():
    store = _make_store(admin_emails=set())
    user = _user("promoted@example.com")
    existing = {
        "id": user.user_id,
        "email": user.email,
        "role": "admin",
        "full_name": user.full_name,
    }
    _configure_profile_reads(store, existing)

    result = store.ensure_profile(user)

    assert result == existing
    store.client.table.return_value.upsert.assert_not_called()


def test_ensure_profile_existing_admin_role_is_profile_authoritative():
    store = _make_store(admin_emails=set())
    user = _user("former-admin@example.com")
    existing = {
        "id": user.user_id,
        "email": user.email,
        "role": "admin",
        "full_name": user.full_name,
    }
    _configure_profile_reads(store, existing)

    result = store.ensure_profile(user)

    assert result["role"] == "admin"
    store.client.table.return_value.update.assert_not_called()
    store.client.table.return_value.upsert.assert_not_called()



def test_ensure_profile_existing_athlete_is_not_promoted_when_email_is_configured():
    store = _make_store(admin_emails={"promoted@example.com"})
    user = _user("promoted@example.com")
    existing = {
        "id": user.user_id,
        "email": user.email,
        "role": "athlete",
        "full_name": user.full_name,
    }
    _configure_profile_reads(store, existing)

    result = store.ensure_profile(user)

    store.client.table.return_value.update.assert_not_called()
    assert result["role"] == "athlete"
    store.client.table.return_value.upsert.assert_not_called()


def test_ensure_profile_retries_transient_upsert_errors_then_succeeds():
    store = _make_store(admin_emails=set())
    user = _user("retry@example.com")
    expected_profile = {
        "id": user.user_id,
        "email": user.email,
        "role": "athlete",
        "full_name": user.full_name,
    }
    _configure_profile_reads(store, None, expected_profile)

    upsert_execute = store.client.table.return_value.upsert.return_value.execute
    upsert_execute.side_effect = [
        httpx.RemoteProtocolError("Server disconnected"),
        httpx.ReadTimeout("timed out"),
        MagicMock(),
    ]

    result = store.ensure_profile(user)

    assert result["id"] == user.user_id
    assert upsert_execute.call_count == 3



def test_ensure_profile_falls_back_to_read_after_transient_upsert_failure():
    store = _make_store(admin_emails=set())
    user = _user("fallback@example.com")
    recovered_profile = {
        "id": user.user_id,
        "email": user.email,
        "role": "athlete",
        "full_name": user.full_name,
    }
    _configure_profile_reads(store, None, recovered_profile)
    store.client.table.return_value.upsert.return_value.execute.side_effect = httpx.RemoteProtocolError(
        "Server disconnected"
    )

    result = store.ensure_profile(user)

    assert result == recovered_profile


def test_create_or_get_generation_job_returns_503_when_store_is_transiently_unavailable():
    store = _make_store()
    store._run_with_transient_retry = MagicMock(side_effect=httpx.ConnectError("Server disconnected"))

    with pytest.raises(HTTPException) as exc_info:
        store.create_or_get_generation_job(
            athlete_id="athlete-1",
            client_request_id="client-1",
            source="self_serve",
            request_payload={"fight_date": "2026-04-18"},
        )

    assert exc_info.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert exc_info.value.detail == "generation job service temporarily unavailable"


def test_get_generation_job_returns_503_when_lookup_is_transiently_unavailable():
    store = _make_store()
    store._run_with_transient_retry = MagicMock(side_effect=httpx.ReadTimeout("timed out"))

    with pytest.raises(HTTPException) as exc_info:
        store.get_generation_job("job-1")

    assert exc_info.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert exc_info.value.detail == "generation job service temporarily unavailable"


def test_list_user_plans_returns_503_when_store_is_transiently_unavailable():
    store = _make_store()
    store._run_with_transient_retry = MagicMock(side_effect=httpx.ReadTimeout("timed out"))

    with pytest.raises(HTTPException) as exc_info:
        store.list_user_plans("athlete-1")

    assert exc_info.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert exc_info.value.detail == "store service temporarily unavailable"


def test_get_plan_returns_503_when_store_is_transiently_unavailable():
    store = _make_store()
    store._run_with_transient_retry = MagicMock(side_effect=httpx.ConnectError("server disconnected"))

    with pytest.raises(HTTPException) as exc_info:
        store.get_plan("plan-1")

    assert exc_info.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert exc_info.value.detail == "store service temporarily unavailable"


def test_get_latest_plan_returns_503_when_store_is_transiently_unavailable():
    store = _make_store()
    store._run_with_transient_retry = MagicMock(side_effect=httpx.RemoteProtocolError("connection reset"))

    with pytest.raises(HTTPException) as exc_info:
        store.get_latest_plan("athlete-1")

    assert exc_info.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert exc_info.value.detail == "store service temporarily unavailable"


def test_transient_store_error_detects_postgrest_gateway_failures():
    store = _make_store()
    error = APIError(
        {
            "message": "upstream connect error or disconnect/reset before headers. retried and the latest reset reason: connection timeout",
            "code": "503",
            "hint": None,
            "details": None,
        }
    )

    assert store._is_transient_store_error(error) is True


def test_generation_job_schema_error_detects_missing_generation_jobs_table():
    store = _make_store()
    error = APIError(
        {
            "message": "Could not find the table 'public.generation_jobs' in the schema cache",
            "code": "PGRST205",
            "hint": None,
            "details": None,
        }
    )

    assert store._is_generation_job_schema_error(error) is True


def test_create_or_get_generation_job_returns_schema_detail_when_generation_jobs_table_is_missing():
    store = _make_store()
    store._run_with_transient_retry = MagicMock(
        side_effect=APIError(
            {
                "message": "Could not find the table 'public.generation_jobs' in the schema cache",
                "code": "PGRST205",
                "hint": None,
                "details": None,
            }
        )
    )

    with pytest.raises(HTTPException) as exc_info:
        store.create_or_get_generation_job(
            athlete_id="athlete-1",
            client_request_id="client-1",
            source="self_serve",
            request_payload={"fight_date": "2026-04-18"},
        )

    assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert exc_info.value.detail == "generation job store is not ready; apply the latest Supabase schema and redeploy"


def test_create_or_get_generation_job_returns_existing_row_after_unique_conflict():
    store = _make_store()
    existing_job = {
        "id": "job-1",
        "athlete_id": "athlete-1",
        "client_request_id": "client-1",
        "status": "queued",
        "attempt_count": 0,
    }
    duplicate_error = APIError(
        {
            "message": "duplicate key value violates unique constraint \"generation_jobs_athlete_client_request_key\"",
            "code": "23505",
            "hint": None,
            "details": "Key (athlete_id, client_request_id)=(athlete-1, client-1) already exists.",
        }
    )
    active_response = MagicMock()
    active_response.data = []
    store._run_with_transient_retry = MagicMock(side_effect=[None, active_response, duplicate_error, existing_job])

    result = store.create_or_get_generation_job(
        athlete_id="athlete-1",
        client_request_id="client-1",
        source="self_serve",
        request_payload={"fight_date": "2026-04-18"},
    )

    assert result == existing_job


def test_create_or_get_generation_job_persists_source_in_insert_payload():
    store = _make_store()
    insert_response = MagicMock()
    insert_response.data = [
        {
            "id": "job-1",
            "athlete_id": "athlete-1",
            "client_request_id": "client-1",
            "source": "admin_latest_intake",
            "status": "queued",
        }
    ]
    insert_query = MagicMock()
    insert_query.execute.return_value = insert_response
    table_query = MagicMock()
    table_query.insert.return_value = insert_query
    store.client.table.return_value = table_query
    store._lookup_generation_job_by_client_request_id = MagicMock(return_value=None)
    store._run_with_transient_retry = MagicMock(side_effect=lambda *, fn, **_kwargs: fn())

    result = store.create_or_get_generation_job(
        athlete_id="athlete-1",
        client_request_id="client-1",
        source="admin_latest_intake",
        request_payload={"fight_date": "2026-04-18"},
    )

    insert_payload = table_query.insert.call_args.args[0]
    assert insert_payload["source"] == "admin_latest_intake"
    assert result["source"] == "admin_latest_intake"


def test_create_or_get_generation_job_resets_pre_start_stale_existing_job_without_replacing_plan_links():
    store = _make_store()
    existing_job = {
        "id": "job-1",
        "athlete_id": "athlete-1",
        "client_request_id": "client-1",
        "source": "self_serve",
        "request_payload": {"fight_date": "2026-04-18"},
        "status": "running",
        "attempt_count": 1,
        "heartbeat_at": "2026-04-05T12:00:00+00:00",
        "started_at": "2026-04-05T12:00:00+00:00",
        "completed_at": None,
        "progress_milestones": [],
        "stage1_result": None,
        "final_result": None,
        "plan_id": "plan-1",
        "intake_id": "intake-1",
    }
    reset_job = {
        **existing_job,
        "status": "queued",
        "heartbeat_at": None,
        "started_at": None,
        "progress_milestones": [],
    }
    store._lookup_generation_job_by_client_request_id = MagicMock(return_value=existing_job)
    store.get_generation_job = MagicMock(return_value=reset_job)
    store._run_with_transient_retry = MagicMock(side_effect=lambda *, fn, **_kwargs: fn())

    result = store.create_or_get_generation_job(
        athlete_id="athlete-1",
        client_request_id="client-1",
        source="self_serve",
        request_payload={"fight_date": "2026-05-01"},
    )

    update_payload = store.client.table.return_value.update.call_args.args[0]
    assert update_payload["status"] == "queued"
    assert update_payload["progress_milestones"] == []
    assert "plan_id" not in update_payload
    assert "intake_id" not in update_payload
    assert result["id"] == "job-1"
    assert result["plan_id"] == "plan-1"
    assert result["intake_id"] == "intake-1"


def test_create_or_get_generation_job_raises_500_when_insert_returns_no_rows_and_lookup_is_none():
    store = _make_store()
    insert_response = MagicMock()
    insert_response.data = []
    insert_query = MagicMock()
    insert_query.execute.return_value = insert_response
    table_query = MagicMock()
    table_query.insert.return_value = insert_query
    store.client.table.return_value = table_query
    store._lookup_generation_job_by_client_request_id = MagicMock(return_value=None)
    store._run_with_transient_retry = MagicMock(side_effect=lambda *, fn, **_kwargs: fn())

    with pytest.raises(HTTPException) as exc_info:
        store.create_or_get_generation_job(
            athlete_id="athlete-1",
            client_request_id="client-1",
            source="self_serve",
            request_payload={"fight_date": "2026-04-18"},
        )

    assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert exc_info.value.detail == "failed to persist generation job"


def test_validate_runtime_schema_raises_when_required_plan_columns_missing_by_default():
    store = _make_store()
    schema_error = APIError(
        {
            "message": "Could not find the 'stage2_payload' column of 'plans' in the schema cache",
            "code": "PGRST204",
            "hint": None,
            "details": None,
        }
    )
    store.client.table.return_value.select.return_value.limit.return_value.execute.side_effect = schema_error

    with pytest.raises(RuntimeError) as exc_info:
        store.validate_runtime_schema()

    assert str(exc_info.value) == store_module.PLAN_RUNTIME_SCHEMA_ERROR_DETAIL


def test_validate_runtime_schema_maps_plan_check_timeout_to_startup_runtime_error():
    store = _make_store()
    (
        store.client.table.return_value.select.return_value.limit.return_value.execute.side_effect
    ) = httpx.ReadTimeout("The read operation timed out")

    with pytest.raises(RuntimeError) as exc_info:
        store.validate_runtime_schema()

    assert str(exc_info.value) == "store service temporarily unavailable"
    store.client.rpc.assert_not_called()


def test_validate_runtime_schema_passes_when_generation_job_active_lock_is_valid():
    store = _make_store()
    lock_response = MagicMock()
    lock_response.data = True
    store.client.rpc.return_value.execute.return_value = lock_response

    store.validate_runtime_schema()

    store.client.rpc.assert_called_once_with("validate_generation_job_active_lock")


def test_validate_runtime_schema_calls_active_lock_rpc_after_plan_validation():
    store = _make_store()
    lock_response = MagicMock()
    lock_response.data = True
    store.client.rpc.return_value.execute.return_value = lock_response

    store.validate_runtime_schema()

    store.client.table.return_value.select.return_value.limit.return_value.execute.assert_called_once()
    store.client.rpc.assert_called_once_with("validate_generation_job_active_lock")


def test_validate_runtime_schema_raises_when_generation_job_active_lock_is_missing():
    store = _make_store()
    lock_response = MagicMock()
    lock_response.data = False
    store.client.rpc.return_value.execute.return_value = lock_response

    with pytest.raises(RuntimeError) as exc_info:
        store.validate_runtime_schema()

    assert str(exc_info.value) == store_module.GENERATION_JOB_ACTIVE_LOCK_ERROR_DETAIL


def test_validate_runtime_schema_raises_when_generation_job_active_lock_rpc_errors():
    store = _make_store()
    store.client.rpc.return_value.execute.side_effect = APIError(
        {
            "message": "rpc failed",
            "code": "PGRST001",
            "hint": None,
            "details": None,
        }
    )

    with pytest.raises(RuntimeError) as exc_info:
        store.validate_runtime_schema()

    assert str(exc_info.value) == store_module.GENERATION_JOB_ACTIVE_LOCK_ERROR_DETAIL

def _clear_environment_env_vars(monkeypatch):
    for var in ("APP_ENV", "ENVIRONMENT", "UNLXCK_ENV", "NODE_ENV"):
        monkeypatch.delenv(var, raising=False)


def test_validate_runtime_schema_allows_legacy_missing_columns_when_flag_enabled(monkeypatch):
    _clear_environment_env_vars(monkeypatch)
    monkeypatch.setenv("UNLXCK_ALLOW_LEGACY_PLAN_SCHEMA_FALLBACK", "1")
    store = _make_store()
    schema_error = APIError(
        {
            "message": "Could not find the 'stage2_payload' column of 'plans' in the schema cache",
            "code": "PGRST204",
            "hint": None,
            "details": None,
        }
    )
    store.client.table.return_value.select.return_value.limit.return_value.execute.side_effect = schema_error

    lock_response = MagicMock()
    lock_response.data = True
    store.client.rpc.return_value.execute.return_value = lock_response

    store.validate_runtime_schema()

    store.client.rpc.assert_called_once_with("validate_generation_job_active_lock")


def test_validate_runtime_schema_legacy_fallback_still_raises_when_active_lock_is_missing(monkeypatch):
    _clear_environment_env_vars(monkeypatch)
    monkeypatch.setenv("UNLXCK_ALLOW_LEGACY_PLAN_SCHEMA_FALLBACK", "1")
    store = _make_store()
    schema_error = APIError(
        {
            "message": "Could not find the 'stage2_payload' column of 'plans' in the schema cache",
            "code": "PGRST204",
            "hint": None,
            "details": None,
        }
    )
    store.client.table.return_value.select.return_value.limit.return_value.execute.side_effect = schema_error
    lock_response = MagicMock()
    lock_response.data = False
    store.client.rpc.return_value.execute.return_value = lock_response

    with pytest.raises(RuntimeError) as exc_info:
        store.validate_runtime_schema()

    assert str(exc_info.value) == store_module.GENERATION_JOB_ACTIVE_LOCK_ERROR_DETAIL


@pytest.mark.parametrize(
    "env_var,env_value",
    [
        ("APP_ENV", "production"),
        ("ENVIRONMENT", "production"),
        ("UNLXCK_ENV", "production"),
        ("NODE_ENV", "production"),
        ("APP_ENV", "prod"),
        ("APP_ENV", "PRODUCTION"),
    ],
)
def test_validate_runtime_schema_blocks_legacy_fallback_in_production(
    monkeypatch, env_var, env_value
):
    _clear_environment_env_vars(monkeypatch)
    monkeypatch.setenv(env_var, env_value)
    monkeypatch.setenv("UNLXCK_ALLOW_LEGACY_PLAN_SCHEMA_FALLBACK", "1")
    store = _make_store()
    schema_error = APIError(
        {
            "message": "Could not find the 'stage2_payload' column of 'plans' in the schema cache",
            "code": "PGRST204",
            "hint": None,
            "details": None,
        }
    )
    store.client.table.return_value.select.return_value.limit.return_value.execute.side_effect = schema_error

    with pytest.raises(RuntimeError) as exc_info:
        store.validate_runtime_schema()

    assert str(exc_info.value) == store_module.PLAN_RUNTIME_SCHEMA_ERROR_DETAIL


def test_create_plan_blocks_legacy_fallback_in_production_even_when_flag_set(monkeypatch):
    _clear_environment_env_vars(monkeypatch)
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("UNLXCK_ALLOW_LEGACY_PLAN_SCHEMA_FALLBACK", "1")
    store = _make_store()
    request = _build_request()
    schema_error = APIError(
        {
            "message": "Could not find the 'stage2_payload' column of 'plans' in the schema cache",
            "code": "PGRST204",
            "hint": None,
            "details": None,
        }
    )
    insert_execute = store.client.table.return_value.insert.return_value.execute
    insert_execute.side_effect = schema_error

    with pytest.raises(HTTPException) as exc_info:
        store.create_plan(
            athlete_id="athlete-1",
            intake_id="intake-1",
            request=request,
            result={"plan_text": "# Plan", "stage2_payload": {"ok": True}},
        )

    assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert exc_info.value.detail == store_module.PLAN_RUNTIME_SCHEMA_ERROR_DETAIL
    assert insert_execute.call_count == 1


def test_legacy_plan_schema_fallback_disabled_without_flag(monkeypatch):
    _clear_environment_env_vars(monkeypatch)
    monkeypatch.delenv("UNLXCK_ALLOW_LEGACY_PLAN_SCHEMA_FALLBACK", raising=False)
    store = _make_store()
    assert store._legacy_plan_schema_fallback_enabled() is False


def test_legacy_plan_schema_fallback_enabled_in_development_when_flag_set(monkeypatch):
    _clear_environment_env_vars(monkeypatch)
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("UNLXCK_ALLOW_LEGACY_PLAN_SCHEMA_FALLBACK", "1")
    store = _make_store()
    assert store._legacy_plan_schema_fallback_enabled() is True


def test_legacy_plan_schema_fallback_logs_warning_in_development(monkeypatch, caplog):
    _clear_environment_env_vars(monkeypatch)
    monkeypatch.setenv("UNLXCK_ALLOW_LEGACY_PLAN_SCHEMA_FALLBACK", "1")
    store = _make_store()

    with caplog.at_level("WARNING", logger="api.store"):
        store._legacy_plan_schema_fallback_enabled()

    assert any(
        "Legacy plan schema fallback is enabled" in record.getMessage()
        for record in caplog.records
    )


def test_legacy_plan_schema_fallback_logs_error_when_blocked_in_production(monkeypatch, caplog):
    _clear_environment_env_vars(monkeypatch)
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("UNLXCK_ALLOW_LEGACY_PLAN_SCHEMA_FALLBACK", "1")
    store = _make_store()

    with caplog.at_level("ERROR", logger="api.store"):
        result = store._legacy_plan_schema_fallback_enabled()

    assert result is False
    assert any(
        "blocked_in_production" in record.getMessage()
        for record in caplog.records
    )


def test_create_plan_retries_with_legacy_payload_when_optional_plan_columns_are_missing(monkeypatch):
    _clear_environment_env_vars(monkeypatch)
    monkeypatch.setenv("UNLXCK_ALLOW_LEGACY_PLAN_SCHEMA_FALLBACK", "1")
    store = _make_store()
    request = _build_request()
    schema_error = APIError(
        {
            "message": "Could not find the 'stage2_payload' column of 'plans' in the schema cache",
            "code": "PGRST204",
            "hint": None,
            "details": None,
        }
    )
    insert_execute = store.client.table.return_value.insert.return_value.execute
    success_response = MagicMock()
    success_response.data = [{"id": "plan-1"}]
    insert_execute.side_effect = [schema_error, success_response]

    row = store.create_plan(
        athlete_id="athlete-1",
        intake_id="intake-1",
        request=request,
        result={"plan_text": "# Plan", "stage2_payload": {"ok": True}},
    )

    assert row["id"] == "plan-1"
    assert insert_execute.call_count == 2
    first_payload = store.client.table.return_value.insert.call_args_list[0].args[0]
    second_payload = store.client.table.return_value.insert.call_args_list[1].args[0]
    assert "stage2_payload" in first_payload
    assert "stage2_payload" not in second_payload


@pytest.mark.parametrize("blank_status", [None, ""])
def test_create_plan_defaults_blank_result_status_to_generated(blank_status):
    store = _make_store()
    request = _build_request()
    success_response = MagicMock()
    success_response.data = [{"id": "plan-1", "status": "generated"}]
    store.client.table.return_value.insert.return_value.execute.return_value = success_response

    row = store.create_plan(
        athlete_id="athlete-1",
        intake_id="intake-1",
        request=request,
        result={"status": blank_status, "plan_text": "# Plan"},
    )

    payload = store.client.table.return_value.insert.call_args.args[0]
    assert payload["status"] == "generated"
    assert row["status"] == "generated"


def test_create_plan_raises_clear_schema_error_when_required_columns_missing_by_default():
    store = _make_store()
    request = _build_request()
    insert_execute = store.client.table.return_value.insert.return_value.execute
    insert_execute.side_effect = APIError(
        {
            "message": "Could not find the 'stage2_payload' column of 'plans' in the schema cache",
            "code": "PGRST204",
            "hint": None,
            "details": None,
        }
    )

    with pytest.raises(HTTPException) as exc_info:
        store.create_plan(
            athlete_id="athlete-1",
            intake_id="intake-1",
            request=request,
            result={"plan_text": "# Plan", "stage2_payload": {"ok": True}},
        )

    assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert exc_info.value.detail == store_module.PLAN_RUNTIME_SCHEMA_ERROR_DETAIL
    assert insert_execute.call_count == 1


def test_create_plan_raises_when_non_schema_insert_error_occurs():
    store = _make_store()
    request = _build_request()
    insert_execute = store.client.table.return_value.insert.return_value.execute
    insert_execute.side_effect = APIError(
        {
            "message": "new row violates row-level security policy for table \"plans\"",
            "code": "42501",
            "hint": None,
            "details": None,
        }
    )

    with pytest.raises(HTTPException) as exc_info:
        store.create_plan(
            athlete_id="athlete-1",
            intake_id="intake-1",
            request=request,
            result={"plan_text": "# Plan"},
        )

    assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert exc_info.value.detail == "plan persistence failed"


def test_create_plan_raises_specific_error_for_missing_plans_column():
    store = _make_store()
    request = _build_request()
    insert_execute = store.client.table.return_value.insert.return_value.execute
    insert_execute.side_effect = APIError(
        {
            "message": "Could not find the 'athlete_id' column of 'plans' in the schema cache",
            "code": "PGRST204",
            "hint": None,
            "details": None,
        }
    )

    with pytest.raises(HTTPException) as exc_info:
        store.create_plan(
            athlete_id="athlete-1",
            intake_id="intake-1",
            request=request,
            result={"plan_text": "# Plan"},
        )

    assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert exc_info.value.detail == "missing plans column; apply latest Supabase schema and redeploy"


def test_create_plan_raises_specific_error_for_invalid_payload():
    store = _make_store()
    request = _build_request()
    insert_execute = store.client.table.return_value.insert.return_value.execute
    insert_execute.side_effect = APIError(
        {
            "message": "invalid input syntax for type json",
            "code": "22P02",
            "hint": None,
            "details": "Token \"bad\" is invalid.",
        }
    )

    with pytest.raises(HTTPException) as exc_info:
        store.create_plan(
            athlete_id="athlete-1",
            intake_id="intake-1",
            request=request,
            result={"plan_text": "# Plan"},
        )

    assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert exc_info.value.detail == store_module._PLAN_INVALID_PAYLOAD_DETAIL


@pytest.mark.parametrize("legacy_status", [None, ""])
def test_update_generation_job_defaults_blank_current_status_to_queued(legacy_status):
    store = _make_store()
    updated_job = {"id": "job-1", "status": "running"}
    store._read_generation_job = MagicMock(return_value={"id": "job-1", "status": legacy_status})
    store.get_generation_job = MagicMock(return_value=updated_job)
    store._run_with_transient_retry = lambda *, operation, fn, attempts=3, backoff_seconds=0.25: fn()

    result = store.update_generation_job("job-1", status="running")

    payload = store.client.table.return_value.update.call_args.args[0]
    assert payload["status"] == "running"
    assert result == updated_job


def test_update_generation_job_allows_failed_job_retry_to_queued():
    store = _make_store()
    updated_job = {"id": "job-1", "status": "queued"}
    store._read_generation_job = MagicMock(return_value={"id": "job-1", "status": "failed"})
    store.get_generation_job = MagicMock(return_value=updated_job)
    store._run_with_transient_retry = lambda *, operation, fn, attempts=3, backoff_seconds=0.25: fn()

    result = store.update_generation_job("job-1", status="queued")

    payload = store.client.table.return_value.update.call_args.args[0]
    assert payload["status"] == "queued"
    assert result == updated_job


def test_update_generation_job_rejects_invalid_transition_with_409():
    store = _make_store()
    store._read_generation_job = MagicMock(return_value={"id": "job-1", "status": "completed"})

    with pytest.raises(HTTPException) as exc_info:
        store.update_generation_job("job-1", status="failed")

    assert exc_info.value.status_code == status.HTTP_409_CONFLICT
    assert "invalid generation job status transition" in str(exc_info.value.detail)
    store.client.table.return_value.update.assert_not_called()


@pytest.mark.parametrize("legacy_status", [None, ""])
def test_archive_plan_defaults_blank_current_status_to_generated(legacy_status):
    store = _make_store()
    archived_plan = {"id": "plan-1", "status": "archived"}
    store.get_plan = MagicMock(
        side_effect=[
            {"id": "plan-1", "status": legacy_status},
            archived_plan,
        ]
    )

    result = store.archive_plan("plan-1")

    payload = store.client.table.return_value.update.call_args.args[0]
    assert payload["status"] == "archived"
    assert result == archived_plan


def test_update_plan_stage2_allows_triage_blocked_to_ready():
    store = _make_store()
    ready_plan = {"id": "plan-1", "status": "ready"}
    store.get_plan = MagicMock(
        side_effect=[
            {"id": "plan-1", "status": "triage_blocked"},
            ready_plan,
        ]
    )

    result = store.update_plan_stage2("plan-1", {"status": "ready", "plan_text": "# Plan"})

    payload = store.client.table.return_value.update.call_args.args[0]
    assert payload["status"] == "ready"
    assert result == ready_plan


@pytest.mark.parametrize("legacy_status", [None, ""])
def test_update_plan_stage2_defaults_blank_current_status_to_generated(legacy_status):
    store = _make_store()
    ready_plan = {"id": "plan-1", "status": "ready"}
    store.get_plan = MagicMock(
        side_effect=[
            {"id": "plan-1", "status": legacy_status},
            ready_plan,
        ]
    )

    result = store.update_plan_stage2("plan-1", {"status": "ready", "plan_text": "# Plan"})

    payload = store.client.table.return_value.update.call_args.args[0]
    assert payload["status"] == "ready"
    assert result == ready_plan


def test_update_plan_stage2_preserves_existing_status_when_result_status_missing():
    store = _make_store()
    updated_plan = {"id": "plan-1", "status": "review_required"}
    store.get_plan = MagicMock(
        side_effect=[
            {"id": "plan-1", "status": "review_required"},
            updated_plan,
        ]
    )

    result = store.update_plan_stage2("plan-1", {"plan_text": "# Manual review text"})

    payload = store.client.table.return_value.update.call_args.args[0]
    assert payload["status"] == "review_required"
    assert result == updated_plan


def test_update_plan_stage2_rejects_invalid_transition_with_409():
    store = _make_store()
    store.get_plan = MagicMock(return_value={"id": "plan-1", "status": "archived"})

    with pytest.raises(HTTPException) as exc_info:
        store.update_plan_stage2("plan-1", {"status": "ready", "plan_text": "# Plan"})

    assert exc_info.value.status_code == status.HTTP_409_CONFLICT
    assert "invalid plan status transition" in str(exc_info.value.detail)
    store.client.table.return_value.update.assert_not_called()


def test_claim_generation_job_treats_null_status_as_queued(monkeypatch):
    fixed_now = "2026-04-05T12:00:00+00:00"
    monkeypatch.setattr(store_module, "_utc_now_iso", lambda: fixed_now)
    store = _make_store()
    legacy_job = {
        "id": "job-1",
        "status": None,
        "attempt_count": 0,
        "heartbeat_at": None,
        "started_at": None,
    }
    claimed_job = {
        "id": "job-1",
        "status": "running",
        "attempt_count": 1,
        "heartbeat_at": fixed_now,
        "started_at": fixed_now,
        "claimed_by": generation_worker_id(),
        "claimed_at": fixed_now,
        "progress_milestones": [{"code": "job_loaded"}],
    }
    store.get_generation_job = MagicMock(return_value=legacy_job)
    store._run_with_transient_retry = lambda *, operation, fn, attempts=3, backoff_seconds=0.25: fn()
    response = MagicMock()
    response.data = claimed_job
    store.client.rpc.return_value.execute.return_value = response

    result = store.claim_generation_job("job-1")

    assert result == claimed_job
    rpc_name, payload = store.client.rpc.call_args.args
    assert rpc_name == "claim_generation_job"
    assert payload["p_job_id"] == "job-1"
    assert payload["p_expected_status"] == "queued"
    assert payload["p_expected_attempt_count"] == 0
    assert payload["p_worker_id"] == generation_worker_id()
    assert payload["p_claimed_at"] == fixed_now
    assert payload["p_progress_milestones"][0]["code"] == "job_loaded"


def test_claim_generation_job_treats_blank_status_as_queued(monkeypatch):
    fixed_now = "2026-04-05T12:00:00+00:00"
    monkeypatch.setattr(store_module, "_utc_now_iso", lambda: fixed_now)
    store = _make_store()
    legacy_job = {
        "id": "job-1",
        "status": "",
        "attempt_count": 0,
        "heartbeat_at": None,
        "started_at": None,
    }
    claimed_job = {
        "id": "job-1",
        "status": "running",
        "attempt_count": 1,
        "heartbeat_at": fixed_now,
        "started_at": fixed_now,
        "claimed_by": generation_worker_id(),
        "claimed_at": fixed_now,
        "progress_milestones": [{"code": "job_loaded"}],
    }
    store.get_generation_job = MagicMock(return_value=legacy_job)
    store._run_with_transient_retry = lambda *, operation, fn, attempts=3, backoff_seconds=0.25: fn()
    response = MagicMock()
    response.data = claimed_job
    store.client.rpc.return_value.execute.return_value = response

    result = store.claim_generation_job("job-1")

    assert result == claimed_job
    rpc_name, payload = store.client.rpc.call_args.args
    assert rpc_name == "claim_generation_job"
    assert payload["p_expected_status"] == "queued"
    assert payload["p_expected_attempt_count"] == 0
    assert payload["p_worker_id"] == generation_worker_id()


@pytest.mark.parametrize("current_status", ["completed", "failed", "review_required"])
def test_claim_generation_job_returns_none_for_invalid_non_blank_statuses(current_status):
    store = _make_store()
    store.get_generation_job = MagicMock(
        return_value={
            "id": "job-1",
            "status": current_status,
            "attempt_count": 0,
            "heartbeat_at": None,
            "started_at": None,
        }
    )
    store._run_with_transient_retry = MagicMock()

    result = store.claim_generation_job("job-1")

    assert result is None
    store.client.rpc.assert_not_called()
    store._run_with_transient_retry.assert_not_called()


def test_claim_generation_job_returns_none_when_claim_race_loses(monkeypatch):
    fixed_now = "2026-04-05T12:00:00+00:00"
    monkeypatch.setattr(store_module, "_utc_now_iso", lambda: fixed_now)
    store = _make_store()
    queued_job = {
        "id": "job-1",
        "status": "queued",
        "attempt_count": 0,
        "heartbeat_at": None,
        "started_at": None,
    }
    store.get_generation_job = MagicMock(return_value=queued_job)
    store._run_with_transient_retry = lambda *, operation, fn, attempts=3, backoff_seconds=0.25: fn()
    # Another worker won the atomic claim, so the RPC's guarded update matched
    # nothing and returned null.
    response = MagicMock()
    response.data = None
    store.client.rpc.return_value.execute.return_value = response

    result = store.claim_generation_job("job-1")

    assert result is None
    rpc_name, payload = store.client.rpc.call_args.args
    assert rpc_name == "claim_generation_job"
    assert payload["p_expected_status"] == "queued"
    assert payload["p_expected_attempt_count"] == 0


def test_claim_generation_job_returns_claimed_row_with_worker_ownership(monkeypatch):
    fixed_now = "2026-04-05T12:00:00+00:00"
    monkeypatch.setattr(store_module, "_utc_now_iso", lambda: fixed_now)
    store = _make_store()
    queued_job = {
        "id": "job-1",
        "status": "queued",
        "attempt_count": 0,
        "heartbeat_at": None,
        "started_at": None,
    }
    claimed_job = {
        "id": "job-1",
        "status": "running",
        "attempt_count": 1,
        "heartbeat_at": fixed_now,
        "started_at": fixed_now,
        "claimed_by": "worker-a",
        "claimed_at": fixed_now,
        "progress_milestones": [
            {
                "code": "job_loaded",
                "label": "Generation job loaded",
                "detail": "Worker loaded the persisted generation job.",
                "meta": {},
                "at": fixed_now,
            }
        ],
    }
    store.get_generation_job = MagicMock(return_value=queued_job)
    store._run_with_transient_retry = lambda *, operation, fn, attempts=3, backoff_seconds=0.25: fn()
    response = MagicMock()
    response.data = claimed_job
    store.client.rpc.return_value.execute.return_value = response

    result = store.claim_generation_job("job-1", worker_id="worker-a")

    assert result == claimed_job
    rpc_name, payload = store.client.rpc.call_args.args
    assert rpc_name == "claim_generation_job"
    assert payload["p_worker_id"] == "worker-a"
    assert payload["p_progress_milestones"][0]["code"] == "job_loaded"


def test_get_active_generation_job_for_athlete_uses_app_stale_timeout_by_default(monkeypatch):
    monkeypatch.setenv("APP_GENERATION_JOB_STALE_AFTER_SECONDS", "300")
    store = _make_store()
    now = datetime.now(timezone.utc)
    running = {
        "id": "job-1",
        "athlete_id": "athlete-1",
        "status": "running",
        "started_at": (now - timedelta(seconds=120)).isoformat(),
        "heartbeat_at": (now - timedelta(seconds=120)).isoformat(),
        "progress_milestones": [],
    }
    response = MagicMock()
    response.data = [running]
    store._run_with_transient_retry = lambda *, operation, fn, attempts=3, backoff_seconds=0.25: response

    result = store.get_active_generation_job_for_athlete("athlete-1")

    assert result is not None
    assert result["id"] == "job-1"


def test_list_claimable_generation_jobs_uses_app_stale_timeout_by_default(monkeypatch):
    monkeypatch.setenv("APP_GENERATION_JOB_STALE_AFTER_SECONDS", "60")
    monkeypatch.delenv("UNLXCK_CLAIM_LEGACY_BLANK_STATUS_JOBS", raising=False)
    store = _make_store()
    now = datetime.now(timezone.utc)
    running_stale = {
        "id": "job-1",
        "status": "running",
        "created_at": (now - timedelta(seconds=80)).isoformat(),
        "started_at": (now - timedelta(seconds=80)).isoformat(),
        "heartbeat_at": (now - timedelta(seconds=80)).isoformat(),
        "progress_milestones": [],
    }
    queued_response = MagicMock()
    queued_response.data = []
    stale_heartbeat_response = MagicMock()
    stale_heartbeat_response.data = [running_stale]
    stale_without_heartbeat_response = MagicMock()
    stale_without_heartbeat_response.data = []
    responses = [
        queued_response,
        stale_heartbeat_response,
        stale_without_heartbeat_response,
    ]

    def _run(*, operation, fn, attempts=3, backoff_seconds=0.25):
        return responses.pop(0)

    store._run_with_transient_retry = _run

    claimable = store.list_claimable_generation_jobs()

    assert [row["id"] for row in claimable] == ["job-1"]


def test_claim_generation_job_start_uses_app_stale_timeout_by_default(monkeypatch):
    monkeypatch.setenv("APP_GENERATION_JOB_STALE_AFTER_SECONDS", "60")
    fixed_now = "2026-04-05T12:00:00+00:00"
    monkeypatch.setattr(store_module, "_utc_now_iso", lambda: fixed_now)
    store = _make_store()
    now = datetime.now(timezone.utc)
    running_stale = {
        "id": "job-1",
        "status": "running",
        "attempt_count": 1,
        "heartbeat_at": (now - timedelta(seconds=80)).isoformat(),
        "started_at": (now - timedelta(seconds=80)).isoformat(),
        "progress_milestones": [],
    }
    claimed_job = {
        "id": "job-1",
        "status": "running",
        "attempt_count": 2,
        "heartbeat_at": fixed_now,
        "started_at": running_stale["started_at"],
        "claimed_by": generation_worker_id(),
        "claimed_at": fixed_now,
        "progress_milestones": [{"code": "job_loaded"}],
    }
    store.get_generation_job = MagicMock(return_value=running_stale)
    store._run_with_transient_retry = lambda *, operation, fn, attempts=3, backoff_seconds=0.25: fn()
    response = MagicMock()
    response.data = claimed_job
    store.client.rpc.return_value.execute.return_value = response

    result = store.claim_generation_job_start("job-1")

    assert result is not None
    assert result["attempt_count"] == 2
    rpc_name, payload = store.client.rpc.call_args.args
    assert rpc_name == "claim_generation_job"
    assert payload["p_expected_status"] == "running"
    assert payload["p_expected_attempt_count"] == 1


def test_claim_generation_job_start_fails_job_loaded_stall_at_attempt_cap(monkeypatch):
    monkeypatch.setenv("APP_GENERATION_JOB_STALE_AFTER_SECONDS", "60")
    fixed_now = "2026-04-05T12:00:00+00:00"
    monkeypatch.setattr(store_module, "_utc_now_iso", lambda: fixed_now)
    store = _make_store()
    now = datetime.now(timezone.utc)
    old_iso = (now - timedelta(seconds=120)).isoformat()
    stalled = {
        "id": "job-1",
        "status": "running",
        "attempt_count": 2,
        "heartbeat_at": old_iso,
        "started_at": old_iso,
        "stage1_result": None,
        "final_result": None,
        "completed_at": None,
        "progress_milestones": [
            {"code": "job_loaded", "label": "Generation job loaded", "detail": "", "meta": {}, "at": old_iso}
        ],
    }
    store.get_generation_job = MagicMock(return_value=stalled)
    captured = {}

    def _run(*, operation, fn, attempts=3, backoff_seconds=0.25):
        captured["operation"] = operation
        return fn()

    store._run_with_transient_retry = _run
    response = MagicMock()
    response.data = {"id": "job-1", "status": "failed", "attempt_count": 2}
    store.client.rpc.return_value.execute.return_value = response

    result = store.claim_generation_job_start("job-1")

    # Worker reclaim refuses to re-grab the job past its attempt budget and fails it
    # instead of bumping attempt_count to 3.
    assert result is None
    assert captured["operation"] == "fail_generation_job:rpc"
    rpc_name, payload = store.client.rpc.call_args.args
    assert rpc_name == "fail_generation_job"
    assert payload["p_job_id"] == "job-1"
    assert payload["p_expected_status"] == "running"
    assert payload["p_expected_attempt_count"] == 2
    assert payload["p_error"] == "Generation worker stalled after loading the job."
    assert payload["p_failed_at"] == fixed_now
    assert payload["p_heartbeat_at"] == fixed_now
    # The stalled job belongs to a dead worker, so the recovery path must not
    # assert ownership for itself.
    assert payload["p_expected_worker_id"] is None
    assert any(m["code"] == "worker_claim_stalled_failed" for m in payload["p_progress_milestones"])


def test_complete_generation_job_calls_terminal_rpc_successfully():
    store = _make_store()
    response = MagicMock()
    response.data = {
        "id": "job-1",
        "status": "completed",
        "attempt_count": 2,
        "completed_at": "2026-04-05T12:00:00+00:00",
        "failed_at": None,
    }
    store.client.rpc.return_value.execute.return_value = response
    store._run_with_transient_retry = lambda *, operation, fn, attempts=3, backoff_seconds=0.25: fn()

    result = store.complete_generation_job(
        "job-1",
        expected_attempt_count=2,
        final_status="completed",
        final_result={"status": "ready"},
        plan_id="11111111-1111-1111-1111-111111111111",
        completed_at="2026-04-05T12:00:00+00:00",
        heartbeat_at="2026-04-05T12:00:00+00:00",
    )

    assert result["status"] == "completed"
    rpc_name, payload = store.client.rpc.call_args.args
    assert rpc_name == "complete_generation_job"
    assert payload["p_job_id"] == "job-1"
    assert payload["p_expected_status"] == "running"
    assert payload["p_expected_attempt_count"] == 2
    assert payload["p_final_status"] == "completed"
    assert payload["p_final_result"] == {"status": "ready"}
    assert payload["p_expected_worker_id"] == generation_worker_id()


def test_fail_generation_job_calls_terminal_rpc_successfully():
    store = _make_store()
    response = MagicMock()
    response.data = {
        "id": "job-1",
        "status": "failed",
        "attempt_count": 2,
        "error": "Stage 2 failed",
        "failed_at": "2026-04-05T12:00:00+00:00",
    }
    store.client.rpc.return_value.execute.return_value = response
    store._run_with_transient_retry = lambda *, operation, fn, attempts=3, backoff_seconds=0.25: fn()

    result = store.fail_generation_job(
        "job-1",
        expected_attempt_count=2,
        error="Stage 2 failed",
        progress_milestones=[{"code": "failed"}],
        failed_at="2026-04-05T12:00:00+00:00",
        heartbeat_at="2026-04-05T12:00:00+00:00",
    )

    assert result["status"] == "failed"
    rpc_name, payload = store.client.rpc.call_args.args
    assert rpc_name == "fail_generation_job"
    assert payload["p_job_id"] == "job-1"
    assert payload["p_expected_status"] == "running"
    assert payload["p_expected_attempt_count"] == 2
    assert payload["p_error"] == "Stage 2 failed"
    assert payload["p_progress_milestones"] == [{"code": "failed"}]
    assert payload["p_expected_worker_id"] == generation_worker_id()


def test_complete_generation_job_rejects_stale_attempt_with_409():
    store = _make_store()
    store._run_with_transient_retry = MagicMock(
        side_effect=APIError(
            {
                "message": "stale_generation_job_attempt:job-1 expected 2, got 3",
                "code": "P0001",
                "hint": None,
                "details": None,
            }
        )
    )

    with pytest.raises(HTTPException) as exc_info:
        store.complete_generation_job(
            "job-1",
            expected_attempt_count=2,
            final_status="completed",
        )

    assert exc_info.value.status_code == status.HTTP_409_CONFLICT
    assert "stale_generation_job_attempt" in str(exc_info.value.detail)


def test_fail_generation_job_rejects_wrong_status_with_409():
    store = _make_store()
    store._run_with_transient_retry = MagicMock(
        side_effect=APIError(
            {
                "message": "wrong_generation_job_status:job-1 expected running, got completed",
                "code": "P0001",
                "hint": None,
                "details": None,
            }
        )
    )

    with pytest.raises(HTTPException) as exc_info:
        store.fail_generation_job(
            "job-1",
            expected_attempt_count=2,
            error="failed",
        )

    assert exc_info.value.status_code == status.HTTP_409_CONFLICT
    assert "wrong_generation_job_status" in str(exc_info.value.detail)


def test_fail_generation_job_missing_job_returns_404():
    store = _make_store()
    store._run_with_transient_retry = MagicMock(
        side_effect=APIError(
            {
                "message": "generation_job_missing:job-1",
                "code": "P0002",
                "hint": None,
                "details": None,
            }
        )
    )

    with pytest.raises(HTTPException) as exc_info:
        store.fail_generation_job(
            "job-1",
            expected_attempt_count=2,
            error="failed",
        )

    assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
    assert exc_info.value.detail == "generation job not found"


def test_count_active_generation_jobs_uses_app_stale_timeout_by_default(monkeypatch):
    monkeypatch.setenv("APP_GENERATION_JOB_STALE_AFTER_SECONDS", "60")
    store = _make_store()
    response = MagicMock()
    response.count = 3
    def _run(*, operation, fn, attempts=3, backoff_seconds=0.25):
        return fn()
    store._run_with_transient_retry = _run
    store.client.table.return_value.select.return_value.eq.return_value.or_.return_value.execute.return_value = response

    assert store.count_active_generation_jobs() == 3
    or_arg = store.client.table.return_value.select.return_value.eq.return_value.or_.call_args.args[0]
    cutoff_token = "heartbeat_at.gt."
    cutoff_start = or_arg.index(cutoff_token) + len(cutoff_token)
    cutoff_end = or_arg.index(",and(")
    cutoff_iso = or_arg[cutoff_start:cutoff_end]
    cutoff = datetime.fromisoformat(cutoff_iso)
    age = (datetime.now(timezone.utc) - cutoff).total_seconds()
    assert 50 <= age <= 70


def test_generation_stale_timeout_falls_back_to_worker_env_when_app_env_unset(monkeypatch):
    monkeypatch.delenv("APP_GENERATION_JOB_STALE_AFTER_SECONDS", raising=False)
    monkeypatch.setenv("UNLXCK_GENERATION_WORKER_STALE_AFTER_SECONDS", "420")
    store = _make_store()
    response = MagicMock()
    response.count = 1
    def _run(*, operation, fn, attempts=3, backoff_seconds=0.25):
        return fn()
    store._run_with_transient_retry = _run
    store.client.table.return_value.select.return_value.eq.return_value.or_.return_value.execute.return_value = response

    assert store.count_active_generation_jobs() == 1
    or_arg = store.client.table.return_value.select.return_value.eq.return_value.or_.call_args.args[0]
    cutoff_token = "heartbeat_at.gt."
    cutoff_start = or_arg.index(cutoff_token) + len(cutoff_token)
    cutoff_end = or_arg.index(",and(")
    cutoff_iso = or_arg[cutoff_start:cutoff_end]
    cutoff = datetime.fromisoformat(cutoff_iso)
    age = (datetime.now(timezone.utc) - cutoff).total_seconds()
    assert 410 <= age <= 430


def test_profile_bootstrap_logs_omit_email(caplog):
    store = _make_store(admin_emails=set())
    user = _user("private@example.com", user_id="athlete-safe-log")

    with caplog.at_level("INFO", logger="api.store"):
        store._log_profile_event(operation="ensure_start", user=user)

    assert "private@example.com" not in caplog.text
    assert "email=" not in caplog.text
    assert "athlete_id=athlete-safe-log" in caplog.text
    record = caplog.records[-1]
    assert record.athlete_id == "athlete-safe-log"
    assert record.auth_event == "profile_ensure_start"


def test_profile_upsert_failure_logs_sanitized_error(caplog):
    store = _make_store(admin_emails=set())
    user = _user("private@example.com", user_id="athlete-safe-log")
    raw_error = (
        "connection failed email=private@example.com "
        'full_name="Private User" '
        "Authorization=Bearer abcdefghijklmnopqrstuvwxyz123456 "
        "request_payload={'injuries': ['private note']}"
    )
    store.client.table.return_value.upsert.return_value.execute.side_effect = httpx.ConnectError(raw_error)

    with caplog.at_level("WARNING", logger="api.store"), pytest.raises(httpx.ConnectError):
        store._upsert_profile_with_retry(user=user, payload={"id": user.user_id}, attempts=1)

    assert "error=" in caplog.text
    assert "ConnectError" in caplog.text
    assert "private@example.com" not in caplog.text
    assert "Private User" not in caplog.text
    assert "abcdefghijklmnopqrstuvwxyz123456" not in caplog.text
    assert "private note" not in caplog.text
    assert "request_payload=[redacted_payload]" in caplog.text
