from __future__ import annotations

import logging
import os
import warnings
from dataclasses import dataclass
from threading import RLock
from time import monotonic
from typing import Any, Protocol

import httpx
from fastapi import HTTPException, status
from supabase import Client, ClientOptions, create_client

from .environment import is_production_environment

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
        self._token_cache: dict[str, tuple[AuthenticatedUser, float]] = {}
        self._cache_lock = RLock()
        try:
            self._cache_ttl_seconds = int(os.getenv("AUTH_TOKEN_CACHE_TTL") or "60")
        except ValueError:
            logger.warning("[auth] invalid AUTH_TOKEN_CACHE_TTL; falling back to 60")
            self._cache_ttl_seconds = 60

        try:
            self._max_cache_size = int(os.getenv("AUTH_TOKEN_CACHE_MAX_SIZE") or "1000")
        except ValueError:
            logger.warning("[auth] invalid AUTH_TOKEN_CACHE_MAX_SIZE; falling back to 1000")
            self._max_cache_size = 1000

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

        # Disable HTTP/2 to avoid RemoteProtocolError (GOAWAY frames) when
        # Supabase terminates a multiplexed connection after several streams.
        # Explicit timeout avoids httpx's short default read timeout causing
        # false auth outages during transient Supabase latency spikes.
        _client_opts = ClientOptions(
            httpx_client=httpx.Client(
                http2=False,
                timeout=httpx.Timeout(
                    connect=5.0,
                    read=30.0,
                    write=5.0,
                    pool=15.0,
                ),
                limits=httpx.Limits(
                    max_connections=50,
                    max_keepalive_connections=20,
                    keepalive_expiry=30.0,
                ),
            )
        )

        if service_role_key:
            logger.info("[auth] initializing with SUPABASE_SERVICE_ROLE_KEY has_url=%s", bool(url))
            return cls(create_client(url, service_role_key, options=_client_opts))

        if allow_anon_fallback and is_production_environment():
            logger.error(
                "[auth] anon_fallback_blocked_in_production "
                "ALLOW_SUPABASE_ANON_AUTH_FALLBACK is ignored in production; "
                "SUPABASE_SERVICE_ROLE_KEY must be set"
            )
            raise RuntimeError(
                "SUPABASE_SERVICE_ROLE_KEY is required in production; "
                "ALLOW_SUPABASE_ANON_AUTH_FALLBACK is ignored."
            )

        if allow_anon_fallback and anon_key:
            logger.warning(
                "[auth] SUPABASE_SERVICE_ROLE_KEY not set; using SUPABASE_ANON_KEY because "
                "ALLOW_SUPABASE_ANON_AUTH_FALLBACK is enabled has_url=%s",
                bool(url),
            )
            return cls(create_client(url, anon_key, options=_client_opts))

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

        cached_user = self._get_cached_user(token)
        if cached_user is not None:
            return cached_user

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

        authenticated_user = AuthenticatedUser(
            user_id=str(user_id),
            email=email,
            full_name=str(full_name),
            metadata=metadata,
        )

        self._cache_user(token, authenticated_user)

        return authenticated_user

    def _get_cached_user(self, token: str) -> AuthenticatedUser | None:
        now = monotonic()

        with self._cache_lock:
            cached = self._token_cache.get(token)

            if cached is None:
                return None

            user, expires_at = cached

            if expires_at <= now:
                self._token_cache.pop(token, None)
                return None

            return user

    def _cache_user(self, token: str, user: AuthenticatedUser) -> None:
        now = monotonic()

        with self._cache_lock:
            self._token_cache[token] = (user, now + self._cache_ttl_seconds)
            self._prune_cache(now)

    def _prune_cache(self, now: float) -> None:
        expired_tokens = [
            cache_token
            for cache_token, (_, expires_at) in self._token_cache.items()
            if expires_at <= now
        ]

        for cache_token in expired_tokens:
            self._token_cache.pop(cache_token, None)

        while self._token_cache and len(self._token_cache) > self._max_cache_size:
            oldest_token = next(iter(self._token_cache))
            self._token_cache.pop(oldest_token, None)

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
