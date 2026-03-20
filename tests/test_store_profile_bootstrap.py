"""Tests for SupabaseAppStore profile bootstrap role assignment and retry logic."""
from __future__ import annotations

from unittest.mock import MagicMock

import httpx

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
