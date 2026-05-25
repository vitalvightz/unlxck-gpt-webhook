from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException, status
from postgrest.exceptions import APIError as PostgrestAPIError

from api.store import SupabaseAppStore


def _make_store() -> SupabaseAppStore:
    return SupabaseAppStore(client=MagicMock(), admin_emails=set())


def _profile(username: str | None = "current_name") -> dict:
    return {"id": "athlete-1", "username": username, "username_change_history": []}


def test_change_username_calls_atomic_rpc_and_returns_latest_profile():
    store = _make_store()
    store._require_profile = MagicMock(side_effect=[_profile(), _profile("new_name")])

    result = store.change_username("athlete-1", "New_Name")

    store.client.rpc.assert_called_once_with(
        "change_profile_username",
        {"p_profile_id": "athlete-1", "p_username": "new_name"},
    )
    assert result["username"] == "new_name"


@pytest.mark.parametrize(
    "message",
    [
        {"message": "duplicate key value violates unique constraint"},
        {"message": "already exists", "code": "23505"},
        {"message": "unique violation"},
    ],
)
def test_change_username_maps_duplicate_rpc_errors_to_409(message: dict[str, str]):
    store = _make_store()
    store._require_profile = MagicMock(return_value=_profile())
    store.client.rpc.return_value.execute.side_effect = PostgrestAPIError(message)

    with pytest.raises(HTTPException) as exc_info:
        store.change_username("athlete-1", "new_name")

    assert exc_info.value.status_code == status.HTTP_409_CONFLICT
    assert exc_info.value.detail == "That username is already taken. Pick another."


def test_change_username_maps_rate_limit_rpc_errors_to_429():
    store = _make_store()
    store._require_profile = MagicMock(return_value=_profile())
    store.client.rpc.return_value.execute.side_effect = PostgrestAPIError(
        {"message": "username_rate_limit_exceeded:2026-06-01 00:00:00+00"}
    )

    with pytest.raises(HTTPException) as exc_info:
        store.change_username("athlete-1", "new_name")

    assert exc_info.value.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert "You can change your username up to 4 times every 30 days." in exc_info.value.detail
    assert "Next change available 2026-06-01 00:00:00+00." in exc_info.value.detail


def test_change_username_unknown_postgrest_error_uses_store_error_path():
    store = _make_store()
    store._require_profile = MagicMock(return_value=_profile())
    store.client.rpc.return_value.execute.side_effect = PostgrestAPIError({"message": "rpc exploded"})

    with pytest.raises(HTTPException) as exc_info:
        store.change_username("athlete-1", "new_name")

    assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert exc_info.value.detail == "failed to change username"
