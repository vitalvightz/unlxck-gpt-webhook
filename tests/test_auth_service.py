from __future__ import annotations

from unittest.mock import MagicMock

import httpx
import pytest
from fastapi import HTTPException, status

import api.auth as auth_module
from api.auth import SupabaseAuthService, is_auth_api_error


class _FakeGotrueAuthApiError(Exception):
    """Stand-in matching the gotrue.errors.AuthApiError surface."""

    def __init__(self, status_code: int):
        super().__init__(f"auth error {status_code}")
        self.status = status_code


_FakeGotrueAuthApiError.__module__ = "gotrue.errors"
_FakeGotrueAuthApiError.__name__ = "AuthApiError"


class _FakeSupabaseAuthApiError(Exception):
    """Stand-in matching the supabase_auth.errors.AuthApiError surface."""

    def __init__(self, status_code: int):
        super().__init__(f"auth error {status_code}")
        self.status = status_code


_FakeSupabaseAuthApiError.__module__ = "supabase_auth.errors"
_FakeSupabaseAuthApiError.__name__ = "AuthApiError"


def _patch_auth_types(monkeypatch, *types):
    monkeypatch.setattr(auth_module, "AUTH_API_ERROR_TYPES", tuple(types))


def test_get_user_from_token_maps_gotrue_auth_api_error_to_http_401(monkeypatch):
    _patch_auth_types(monkeypatch, _FakeGotrueAuthApiError)
    client = MagicMock()
    client.auth.get_user.side_effect = _FakeGotrueAuthApiError(401)

    service = SupabaseAuthService(client)

    with pytest.raises(HTTPException) as exc_info:
        service.get_user_from_token("bad-token")

    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert exc_info.value.detail == "invalid authentication token"


def test_get_user_from_token_maps_supabase_auth_api_error_to_http_401(monkeypatch):
    """Regression: production raises supabase_auth.errors.AuthApiError, not gotrue."""
    _patch_auth_types(monkeypatch, _FakeSupabaseAuthApiError)
    client = MagicMock()
    client.auth.get_user.side_effect = _FakeSupabaseAuthApiError(401)

    service = SupabaseAuthService(client)

    with pytest.raises(HTTPException) as exc_info:
        service.get_user_from_token("bad-token")

    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert exc_info.value.detail == "invalid authentication token"


def test_get_user_from_token_maps_bad_jwt_400_to_http_401(monkeypatch):
    _patch_auth_types(monkeypatch, _FakeSupabaseAuthApiError)
    client = MagicMock()
    client.auth.get_user.side_effect = _FakeSupabaseAuthApiError(400)

    service = SupabaseAuthService(client)

    with pytest.raises(HTTPException) as exc_info:
        service.get_user_from_token("malformed-token")

    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert exc_info.value.detail == "invalid authentication token"


def test_get_user_from_token_maps_upstream_auth_failure_to_http_503(monkeypatch):
    _patch_auth_types(monkeypatch, _FakeSupabaseAuthApiError)
    client = MagicMock()
    client.auth.get_user.side_effect = _FakeSupabaseAuthApiError(500)

    service = SupabaseAuthService(client)

    with pytest.raises(HTTPException) as exc_info:
        service.get_user_from_token("any-token")

    assert exc_info.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert exc_info.value.detail == "authentication service temporarily unavailable"


def test_get_user_from_token_falls_back_to_duck_typing(monkeypatch):
    """When no AuthApiError type is importable, module/name match still catches it."""
    _patch_auth_types(monkeypatch)
    client = MagicMock()
    client.auth.get_user.side_effect = _FakeSupabaseAuthApiError(401)

    service = SupabaseAuthService(client)

    with pytest.raises(HTTPException) as exc_info:
        service.get_user_from_token("bad-token")

    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert exc_info.value.detail == "invalid authentication token"


def test_get_user_from_token_does_not_swallow_unrelated_errors(monkeypatch):
    """Non-auth runtime errors must bubble up rather than be reclassified."""
    _patch_auth_types(monkeypatch, _FakeSupabaseAuthApiError)
    client = MagicMock()
    client.auth.get_user.side_effect = RuntimeError("database is down")

    service = SupabaseAuthService(client)

    with pytest.raises(RuntimeError, match="database is down"):
        service.get_user_from_token("any-token")


def test_get_user_from_token_maps_httpx_failures_to_http_503():
    client = MagicMock()
    client.auth.get_user.side_effect = httpx.ReadTimeout("timed out")

    service = SupabaseAuthService(client)

    with pytest.raises(HTTPException) as exc_info:
        service.get_user_from_token("slow-token")

    assert exc_info.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert exc_info.value.detail == "authentication service temporarily unavailable"


def test_get_user_from_token_maps_missing_user_to_http_401_invalid_token():
    client = MagicMock()
    client.auth.get_user.return_value = type("Response", (), {"user": None})()

    service = SupabaseAuthService(client)

    with pytest.raises(HTTPException) as exc_info:
        service.get_user_from_token("bad-token")

    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert exc_info.value.detail == "invalid authentication token"


def test_get_user_from_token_missing_bearer_returns_authentication_required():
    service = SupabaseAuthService(MagicMock())

    with pytest.raises(HTTPException) as exc_info:
        service.get_user_from_token("")

    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert exc_info.value.detail == "authentication required"


def test_is_auth_api_error_duck_types_supabase_module():
    assert is_auth_api_error(_FakeSupabaseAuthApiError(401))
    assert is_auth_api_error(_FakeGotrueAuthApiError(401))
    assert not is_auth_api_error(RuntimeError("nope"))


def _clear_env_detection_vars(monkeypatch):
    for var in ("APP_ENV", "ENVIRONMENT", "UNLXCK_ENV", "NODE_ENV"):
        monkeypatch.delenv(var, raising=False)


def test_from_env_blocks_anon_fallback_in_production(monkeypatch):
    _clear_env_detection_vars(monkeypatch)
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key-value")
    monkeypatch.setenv("ALLOW_SUPABASE_ANON_AUTH_FALLBACK", "true")
    monkeypatch.setattr(auth_module, "create_client", lambda url, key: MagicMock())

    with pytest.raises(RuntimeError) as exc_info:
        SupabaseAuthService.from_env()

    message = str(exc_info.value)
    assert "production" in message.lower()
    assert "anon-key-value" not in message  # never leak the key


@pytest.mark.parametrize(
    "env_var,env_value",
    [
        ("APP_ENV", "production"),
        ("ENVIRONMENT", "prod"),
        ("UNLXCK_ENV", "live"),
        ("NODE_ENV", "production"),
    ],
)
def test_from_env_blocks_anon_fallback_across_production_env_vars(monkeypatch, env_var, env_value):
    _clear_env_detection_vars(monkeypatch)
    monkeypatch.setenv(env_var, env_value)
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key-value")
    monkeypatch.setenv("ALLOW_SUPABASE_ANON_AUTH_FALLBACK", "true")
    monkeypatch.setattr(auth_module, "create_client", lambda url, key: MagicMock())

    with pytest.raises(RuntimeError):
        SupabaseAuthService.from_env()


def test_from_env_allows_anon_fallback_in_development(monkeypatch):
    _clear_env_detection_vars(monkeypatch)
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key-value")
    monkeypatch.setenv("ALLOW_SUPABASE_ANON_AUTH_FALLBACK", "true")
    created_clients: list[tuple[str, str, object]] = []

    def _fake_create_client(url, key, options=None):
        created_clients.append((url, key, options))
        return MagicMock()

    monkeypatch.setattr(auth_module, "create_client", _fake_create_client)

    service = SupabaseAuthService.from_env()

    assert service is not None
    assert created_clients[0][:2] == ("https://example.supabase.co", "anon-key-value")
    assert created_clients[0][2] is not None


def test_from_env_requires_service_role_without_fallback(monkeypatch):
    _clear_env_detection_vars(monkeypatch)
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    monkeypatch.delenv("SUPABASE_ANON_KEY", raising=False)
    monkeypatch.delenv("ALLOW_SUPABASE_ANON_AUTH_FALLBACK", raising=False)

    with pytest.raises(RuntimeError) as exc_info:
        SupabaseAuthService.from_env()

    assert "SUPABASE_SERVICE_ROLE_KEY" in str(exc_info.value)


def test_collected_auth_api_error_types_includes_supabase_auth_when_available():
    """Smoke-test: when supabase_auth is installed, its AuthApiError is in the tuple."""
    try:
        from supabase_auth.errors import AuthApiError as SupabaseAuthApiError
    except Exception:
        pytest.skip("supabase_auth is not installed in this environment")

    assert SupabaseAuthApiError in auth_module.AUTH_API_ERROR_TYPES
