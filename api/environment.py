from __future__ import annotations

import os

_PRODUCTION_ENV_VALUES = frozenset({"production", "prod", "live"})
_PRODUCTION_ENV_VARS = ("APP_ENV", "ENVIRONMENT", "UNLXCK_ENV", "NODE_ENV")


def is_production_environment() -> bool:
    for var in _PRODUCTION_ENV_VARS:
        value = os.getenv(var, "").strip().lower()
        if value in _PRODUCTION_ENV_VALUES:
            return True
    return False
