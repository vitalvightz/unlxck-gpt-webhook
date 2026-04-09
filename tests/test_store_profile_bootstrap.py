"""Tests for SupabaseAppStore profile bootstrap role assignment and retry logic."""
from __future__ import annotations

from unittest.mock import MagicMock

import httpx
import pytest
from fastapi import HTTPException, status
from postgrest.exceptions import APIError

import api.store as store_module
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


def test_ensure_profile_retries_without_unknown_profiles_column_when_schema_is_behind():
    store = _make_store(admin_emails=set())
    user = _user("schema-gap@example.com")
    expected_profile = {
        "id": user.user_id,
        "email": user.email,
        "role": "athlete",
        "full_name": user.full_name,
    }
    _configure_profile_reads(store, None, expected_profile)

    upsert_execute = store.client.table.return_value.upsert.return_value.execute
    upsert_execute.side_effect = [
        APIError(
            {
                "message": "Could not find the 'nutrition_profile' column of 'profiles' in the schema cache",
                "code": "PGRST204",
                "hint": None,
                "details": None,
            }
        ),
        MagicMock(),
    ]

    result = store.ensure_profile(user)

    assert result["id"] == user.user_id
    first_payload = store.client.table.return_value.upsert.call_args_list[0][0][0]
    second_payload = store.client.table.return_value.upsert.call_args_list[1][0][0]
    assert "nutrition_profile" in first_payload
    assert "nutrition_profile" not in second_payload


def test_extract_missing_profiles_column_ignores_non_column_errors():
    store = _make_store()
    error = APIError(
        {
            "message": "duplicate key value violates unique constraint",
            "code": "23505",
            "hint": None,
            "details": None,
        }
    )

    assert store._extract_missing_profiles_column(error) is None


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


def test_get_admin_athlete_returns_503_when_lookup_is_transiently_unavailable():
    store = _make_store()
    store._run_with_transient_retry = MagicMock(side_effect=httpx.ReadTimeout("timed out"))

    with pytest.raises(HTTPException) as exc_info:
        store.get_admin_athlete("athlete-1")

    assert exc_info.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert exc_info.value.detail == "admin athlete service temporarily unavailable"


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
