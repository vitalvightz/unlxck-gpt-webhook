from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Protocol

from fastapi import HTTPException, status
from supabase import Client, create_client

logger = logging.getLogger(__name__)


@dataclass
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
        key = service_role_key or anon_key
        if not url or not key:
            raise RuntimeError(
                "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY (or SUPABASE_ANON_KEY) are required"
            )
        if service_role_key:
            logger.info("[auth] initializing with SUPABASE_SERVICE_ROLE_KEY has_url=%s", bool(url))
        else:
            logger.warning(
                "[auth] SUPABASE_SERVICE_ROLE_KEY not set; falling back to SUPABASE_ANON_KEY "
                "- token verification may be restricted has_url=%s",
                bool(url),
            )
        return cls(create_client(url, key))

    def get_user_from_token(self, token: str) -> AuthenticatedUser:
        try:
            response = self.client.auth.get_user(token)
        except Exception as exc:  # pragma: no cover - network/runtime integration
            logger.exception("[auth] upstream token verification failed")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="authentication service temporarily unavailable",
            ) from exc

        user = getattr(response, "user", None)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="authentication required",
            )

        metadata = getattr(user, "user_metadata", {}) or {}
        full_name = metadata.get("full_name") or metadata.get("name") or user.email or "Athlete"
        return AuthenticatedUser(
            user_id=str(user.id),
            email=str(user.email or ""),
            full_name=str(full_name),
            metadata=metadata,
        )
