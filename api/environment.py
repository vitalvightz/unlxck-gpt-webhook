from __future__ import annotations

import os

_PRODUCTION_ENV_VALUES = frozenset({"production", "prod", "live"})
_PRODUCTION_ENV_VARS = ("APP_ENV", "ENVIRONMENT", "UNLXCK_ENV", "NODE_ENV")
_PRODUCTION_ENV_DEFAULTS = {"APP_ENV": "production", "UNLXCK_ENV": "production"}


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
