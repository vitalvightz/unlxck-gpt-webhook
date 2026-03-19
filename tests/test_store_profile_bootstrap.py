"""Tests for SupabaseAppStore profile bootstrap role assignment logic."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from api.auth import AuthenticatedUser
from api.models import ProfileUpdateRequest
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


def _mock_upsert_chain(store: SupabaseAppStore, existing_row: dict | None, upserted_row: dict):
    """Configure mock client so ensure_profile() returns the expected data."""
    table_mock = store.client.table.return_value

    # .select("*").eq("id", ...).limit(1).execute()
    select_response = MagicMock()
    select_response.data = [existing_row] if existing_row else []
    (
        table_mock.select.return_value
        .eq.return_value
        .limit.return_value
        .execute.return_value
    ) = select_response

    # .upsert(...).execute()
    table_mock.upsert.return_value.execute.return_value = MagicMock()

    # Second .select("*").eq("id", ...).limit(1).execute() – the re-fetch after upsert
    post_upsert_response = MagicMock()
    post_upsert_response.data = [upserted_row]
    # Re-wire: first call returns existing, second returns upserted_row.
    (
        table_mock.select.return_value
        .eq.return_value
        .limit.return_value
        .execute
    ).side_effect = [select_response, post_upsert_response]


def test_ensure_profile_new_user_gets_athlete_role():
    store = _make_store(admin_emails=set())
    user = _user("newbie@example.com")

    expected_profile = {
        "id": user.user_id,
        "email": user.email,
        "role": "athlete",
        "full_name": user.full_name,
    }
    _mock_upsert_chain(store, existing_row=None, upserted_row=expected_profile)

    result = store.ensure_profile(user)

    # Verify upsert was called with role="athlete"
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
    _mock_upsert_chain(store, existing_row=None, upserted_row=expected_profile)

    store.ensure_profile(user)

    call_args = store.client.table.return_value.upsert.call_args
    payload = call_args[0][0]
    assert payload["role"] == "admin"


def test_ensure_profile_preserves_existing_role():
    store = _make_store(admin_emails=set())
    user = _user("promoted@example.com")

    # Simulate a profile that was previously promoted to admin
    existing = {
        "id": user.user_id,
        "email": user.email,
        "role": "admin",
        "full_name": user.full_name,
    }
    _mock_upsert_chain(store, existing_row=existing, upserted_row=existing)

    store.ensure_profile(user)

    call_args = store.client.table.return_value.upsert.call_args
    payload = call_args[0][0]
    # Must preserve the "admin" role even though the email is not in admin_emails
    assert payload["role"] == "admin"


def test_ensure_profile_preserves_existing_athlete_role():
    store = _make_store(admin_emails={"boss@example.com"})
    user = _user("athlete@example.com")

    existing = {
        "id": user.user_id,
        "email": user.email,
        "role": "athlete",
        "full_name": user.full_name,
    }
    _mock_upsert_chain(store, existing_row=existing, upserted_row=existing)

    store.ensure_profile(user)

    call_args = store.client.table.return_value.upsert.call_args
    payload = call_args[0][0]
    assert payload["role"] == "athlete"


def test_update_profile_retries_without_missing_profile_columns():
    store = _make_store()
    table_mock = store.client.table.return_value

    update_chain = table_mock.update.return_value.eq.return_value.execute
    update_chain.side_effect = [
        Exception("Could not find the 'athlete_locale' column of 'profiles' in the schema cache"),
        MagicMock(),
    ]

    profile_after_update = {
        "id": "uid-1",
        "email": "athlete@example.com",
        "role": "athlete",
        "full_name": "Jake",
        "technical_style": ["boxing"],
        "tactical_style": [],
        "stance": "",
        "professional_status": "",
        "record_summary": "",
        "athlete_timezone": "Europe/London",
        "athlete_locale": "",
        "onboarding_draft": {"current_step": 2},
        "created_at": "2026-03-19T00:00:00Z",
        "updated_at": "2026-03-19T00:00:01Z",
    }
    select_response = MagicMock()
    select_response.data = [profile_after_update]
    table_mock.select.return_value.eq.return_value.limit.return_value.execute.return_value = select_response

    result = store.update_profile(
        "uid-1",
        ProfileUpdateRequest(
            full_name="Jake",
            technical_style=["boxing"],
            athlete_timezone="Europe/London",
            athlete_locale="en-GB",
            onboarding_draft={"current_step": 2},
        ),
    )

    update_calls = table_mock.update.call_args_list
    assert len(update_calls) == 2
    assert update_calls[0].args[0]["athlete_locale"] == "en-GB"
    assert "athlete_locale" not in update_calls[1].args[0]
    assert update_calls[1].args[0]["onboarding_draft"] == {"current_step": 2}
    assert result == profile_after_update
