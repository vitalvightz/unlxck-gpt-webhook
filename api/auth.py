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
        """Create a SupabaseAuthService from environment variables.

        Requires ``SUPABASE_URL`` and ``SUPABASE_SERVICE_ROLE_KEY``.
        ``SUPABASE_ANON_KEY`` is accepted as a fallback for token-lookup only
        (not for privileged writes), but a warning is logged so the operator
        knows they are running with reduced privileges.
        """
        url = os.getenv("SUPABASE_URL", "").strip()
        if not url:
            raise RuntimeError(
                "SUPABASE_URL is required but not set. "
                "Set it in your .env file or environment before starting the server."
            )

        service_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
        anon_key = os.getenv("SUPABASE_ANON_KEY", "").strip()

        if service_key:
            key = service_key
        elif anon_key:
            logger.warning(
                "auth: SUPABASE_SERVICE_ROLE_KEY is not set; "
                "falling back to SUPABASE_ANON_KEY for token lookup. "
                "This is only safe for auth token verification – "
                "privileged store operations still require SUPABASE_SERVICE_ROLE_KEY."
            )
            key = anon_key
        else:
            raise RuntimeError(
                "Neither SUPABASE_SERVICE_ROLE_KEY nor SUPABASE_ANON_KEY is set. "
                "At minimum, set SUPABASE_ANON_KEY for auth token lookup; "
                "set SUPABASE_SERVICE_ROLE_KEY for full backend operation."
            )

        return cls(create_client(url, key))

    def get_user_from_token(self, token: str) -> AuthenticatedUser:
        try:
            response = self.client.auth.get_user(token)
        except Exception as exc:  # pragma: no cover - network/runtime integration
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="invalid authentication token",
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