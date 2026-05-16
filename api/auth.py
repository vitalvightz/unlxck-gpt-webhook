from __future__ import annotations

import logging
import os
import warnings
from dataclasses import dataclass
from typing import Any, Protocol

import httpx
from fastapi import HTTPException, status
from supabase import Client, create_client

logger = logging.getLogger(__name__)


def _collect_auth_api_error_types() -> tuple[type[BaseException], ...]:
    classes: list[type[BaseException]] = []
    try:
        from supabase_auth.errors import AuthApiError as _SupabaseAuthApiError
    except ImportError:  # pragma: no cover - dependency may be absent
        pass
    else:
        classes.append(_SupabaseAuthApiError)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            from gotrue.errors import AuthApiError as _GotrueAuthApiError
    except ImportError:  # pragma: no cover - dependency may be absent
        pass
    else:
        if _GotrueAuthApiError not in classes:
            classes.append(_GotrueAuthApiError)
    return tuple(classes)


AUTH_API_ERROR_TYPES: tuple[type[BaseException], ...] = _collect_auth_api_error_types()


def is_auth_api_error(exc: BaseException) -> bool:
    if AUTH_API_ERROR_TYPES and isinstance(exc, AUTH_API_ERROR_TYPES):
        return True
    # Duck-typing fallback covers vendored or renamed Supabase auth modules.
    return exc.__class__.__name__ == "AuthApiError" and (
        exc.__class__.__module__.startswith("gotrue")
        or exc.__class__.__module__.startswith("supabase_auth")
    )


@dataclass(frozen=True)
class AuthenticatedUser:
    user_id: str
    email: str
    full_name: str
    metadata: dict[str, Any]


class AuthService(Protocol):
    def get_user_from_token(self, token: str) -> AuthenticatedUser: ...


class SupabaseAuthService:
    def __init__(self, client: Client):
        self.client = client

    @classmethod
    def from_env(cls) -> "SupabaseAuthService":
        url = os.getenv("SUPABASE_URL")
        service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        anon_key = os.getenv("SUPABASE_ANON_KEY")
        allow_anon_fallback = (
            os.getenv("ALLOW_SUPABASE_ANON_AUTH_FALLBACK", "").strip().lower()
            in {"1", "true", "yes"}
        )

        if not url:
            raise RuntimeError("SUPABASE_URL is required")

        if service_role_key:
            logger.info("[auth] initializing with SUPABASE_SERVICE_ROLE_KEY has_url=%s", bool(url))
            return cls(create_client(url, service_role_key))

        if allow_anon_fallback and anon_key:
            logger.warning(
                "[auth] SUPABASE_SERVICE_ROLE_KEY not set; using SUPABASE_ANON_KEY because "
                "ALLOW_SUPABASE_ANON_AUTH_FALLBACK is enabled has_url=%s",
                bool(url),
            )
            return cls(create_client(url, anon_key))

        raise RuntimeError(
            "SUPABASE_SERVICE_ROLE_KEY is required. "
            "Set ALLOW_SUPABASE_ANON_AUTH_FALLBACK=true only for local/dev fallback."
        )

    def get_user_from_token(self, token: str) -> AuthenticatedUser:
        token = token.strip()

        if not token:
            raise self._unauthorized()

        if token.lower().startswith("bearer "):
            token = token.split(" ", 1)[1].strip()

        if not token:
            raise self._unauthorized()

        try:
            response = self.client.auth.get_user(token)
        except httpx.HTTPError as exc:  # pragma: no cover - network/runtime integration
            logger.exception("[auth] upstream token verification failed")
            raise self._auth_unavailable() from exc
        except Exception as exc:
            if not is_auth_api_error(exc):
                raise

            status_code = getattr(exc, "status", None) or getattr(exc, "status_code", None)

            if status_code in {400, 401, 403}:
                logger.warning(
                    "[auth] invalid_token status=%s error_class=%s",
                    status_code,
                    exc.__class__.__module__ + "." + exc.__class__.__name__,
                )
                raise self._invalid_token() from exc

            logger.exception("[auth] upstream token verification failed")
            raise self._auth_unavailable() from exc

        user = getattr(response, "user", None)

        if user is None:
            raise self._invalid_token()

        user_id = getattr(user, "id", None)
        if not user_id:
            logger.warning("[auth] verified user response missing user id")
            raise self._invalid_token()

        raw_metadata = getattr(user, "user_metadata", {}) or {}
        metadata = raw_metadata if isinstance(raw_metadata, dict) else {}

        email = str(getattr(user, "email", None) or "")
        full_name = (
            metadata.get("full_name")
            or metadata.get("name")
            or email
            or "Athlete"
        )

        return AuthenticatedUser(
            user_id=str(user_id),
            email=email,
            full_name=str(full_name),
            metadata=metadata,
        )

    @staticmethod
    def _unauthorized() -> HTTPException:
        return HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="authentication required",
        )

    @staticmethod
    def _invalid_token() -> HTTPException:
        return HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid authentication token",
        )

    @staticmethod
    def _auth_unavailable() -> HTTPException:
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="authentication service temporarily unavailable",
        )