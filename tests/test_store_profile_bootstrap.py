"""Tests for SupabaseAppStore profile bootstrap role assignment and retry logic."""
from __future__ import annotations

from unittest.mock import MagicMock

import httpx
import pytest
from fastapi import HTTPException, status
from postgrest.exceptions import APIError

import api.store as store_module
from support import _build_request
from api.auth import AuthenticatedUser
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


def test_ensure_profile_existing_admin_is_not_auto_demoted_when_email_removed_from_env():
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



def test_ensure_profile_existing_athlete_is_promoted_to_admin_when_email_is_configured():
    store = _make_store(admin_emails={"promoted@example.com"})
    user = _user("promoted@example.com")
    existing = {
        "id": user.user_id,
        "email": user.email,
        "role": "athlete",
        "full_name": user.full_name,
    }
    promoted = {**existing, "role": "admin"}
    _configure_profile_reads(store, existing, promoted)
    store.client.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock()

    result = store.ensure_profile(user)

    store.client.table.return_value.update.assert_called_once_with({"role": "admin"})
    assert result["role"] == "admin"
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
    store._run_with_transient_retry = MagicMock(side_effect=[None, duplicate_error, existing_job])

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

    store.validate_runtime_schema()


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


def test_claim_generation_job_returns_none_when_compare_and_swap_loses(monkeypatch):
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
    claimed_by_other_worker = {
        "id": "job-1",
        "status": "running",
        "attempt_count": 1,
        "heartbeat_at": "2026-04-05T12:00:01+00:00",
        "started_at": "2026-04-05T12:00:01+00:00",
    }
    store.get_generation_job = MagicMock(side_effect=[queued_job, claimed_by_other_worker])
    store._run_with_transient_retry = lambda *, operation, fn, attempts=3, backoff_seconds=0.25: fn()
    execute = (
        store.client.table.return_value.update.return_value.eq.return_value.eq.return_value.eq.return_value.execute
    )
    execute.return_value = MagicMock()

    result = store.claim_generation_job("job-1")

    assert result is None
    store.client.table.return_value.update.assert_called_once()
    store.client.table.return_value.update.return_value.eq.assert_called_once_with("id", "job-1")
    store.client.table.return_value.update.return_value.eq.return_value.eq.assert_called_once_with(
        "status", "queued"
    )
    store.client.table.return_value.update.return_value.eq.return_value.eq.return_value.eq.assert_called_once_with(
        "attempt_count", 0
    )


def test_claim_generation_job_returns_updated_row_when_compare_and_swap_succeeds(monkeypatch):
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
    }
    store.get_generation_job = MagicMock(side_effect=[queued_job, claimed_job])
    store._run_with_transient_retry = lambda *, operation, fn, attempts=3, backoff_seconds=0.25: fn()
    execute = (
        store.client.table.return_value.update.return_value.eq.return_value.eq.return_value.eq.return_value.execute
    )
    execute.return_value = MagicMock()

    result = store.claim_generation_job("job-1")

    assert result == claimed_job
