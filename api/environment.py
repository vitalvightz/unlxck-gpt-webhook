from __future__ import annotations

import os

_PRODUCTION_ENV_VALUES = frozenset({"production", "prod", "live"})
_PRODUCTION_ENV_VARS = ("APP_ENV", "ENVIRONMENT", "UNLXCK_ENV", "NODE_ENV")
_PRODUCTION_ENV_DEFAULTS = {"APP_ENV": "production", "UNLXCK_ENV": "production"}


def should_default_to_production() -> bool:
    if "PYTEST_CURRENT_TEST" in os.environ:
        return False

    supabase_url = os.getenv("SUPABASE_URL", "").strip()
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()

    if any(local in supabase_url for local in ("localhost", "127.0.0.1", "::1")):
        return False

    return bool(supabase_url or supabase_key)


def apply_production_environment_defaults() -> None:
    """Default deploy-critical environment markers when runtime config omits them."""
    for var, value in _PRODUCTION_ENV_DEFAULTS.items():
        if not os.getenv(var, "").strip():
            os.environ[var] = value


def is_production_environment() -> bool:
    for var in _PRODUCTION_ENV_VARS:
        value = os.getenv(var, "").strip().lower()
        if value in _PRODUCTION_ENV_VALUES:
            return True
    return False
