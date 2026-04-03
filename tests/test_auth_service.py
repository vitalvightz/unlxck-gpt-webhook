from __future__ import annotations

from unittest.mock import MagicMock

import httpx
import pytest
from fastapi import HTTPException, status

import api.auth as auth_module
from api.auth import SupabaseAuthService


class _FakeAuthApiError(Exception):
    def __init__(self, status_code: int):
        super().__init__(f"auth error {status_code}")
        self.status = status_code


def test_get_user_from_token_maps_auth_api_unauthorized_to_http_401(monkeypatch):
    monkeypatch.setattr(auth_module, "AuthApiError", _FakeAuthApiError)
    client = MagicMock()
    client.auth.get_user.side_effect = _FakeAuthApiError(401)

    service = SupabaseAuthService(client)

    with pytest.raises(HTTPException) as exc_info:
        service.get_user_from_token("bad-token")

    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert exc_info.value.detail == "authentication required"


def test_get_user_from_token_maps_httpx_failures_to_http_503():
    client = MagicMock()
    client.auth.get_user.side_effect = httpx.ReadTimeout("timed out")

    service = SupabaseAuthService(client)

    with pytest.raises(HTTPException) as exc_info:
        service.get_user_from_token("slow-token")

    assert exc_info.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert exc_info.value.detail == "authentication service temporarily unavailable"