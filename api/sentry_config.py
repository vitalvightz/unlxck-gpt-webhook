from __future__ import annotations

import copy
import os
from collections.abc import Mapping
from typing import Any

import sentry_sdk

_SENSITIVE_KEYS = frozenset(
    {
        "access_token",
        "api_key",
        "athlete_email",
        "athlete_name",
        "athlete_profile",
        "authorization",
        "cookie",
        "email",
        "goal",
        "goals",
        "injuries",
        "injury",
        "intake",
        "name",
        "notes",
        "openai_api_key",
        "pain",
        "plan",
        "program",
        "programme",
        "prompt",
        "refresh_token",
        "service_role_key",
        "set-cookie",
        "supabase_anon_key",
        "supabase_service_role_key",
        "supabase_token",
        "token",
    }
)

_REDACTED = "[Filtered]"


def _env_flag(name: str, default: str) -> bool:
    return os.getenv(name, default).strip().lower() == "true"


def _parse_traces_sample_rate() -> float:
    raw_value = os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.1").strip()
    try:
        return float(raw_value)
    except ValueError:
        return 0.1


def _is_sensitive_key(key: object) -> bool:
    normalized = str(key).strip().lower().replace("-", "_")
    if normalized in _SENSITIVE_KEYS:
        return True
    return any(fragment in normalized for fragment in ("api_key", "authorization", "cookie", "secret", "token"))


def _scrub_sensitive_values(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            key: _REDACTED if _is_sensitive_key(key) else _scrub_sensitive_values(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_scrub_sensitive_values(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_scrub_sensitive_values(item) for item in value)
    return value


def scrub_sentry_event(event: dict[str, Any], hint: dict[str, Any] | None = None) -> dict[str, Any]:
    scrubbed = copy.deepcopy(event)
    request = scrubbed.get("request")
    if isinstance(request, dict):
        headers = request.get("headers")
        if isinstance(headers, dict):
            request["headers"] = _scrub_sensitive_values(headers)
        request.pop("data", None)
        request.pop("cookies", None)
        request.pop("env", None)

    return _scrub_sensitive_values(scrubbed)


def init_sentry() -> None:
    sentry_sdk.init(
        dsn=os.getenv("SENTRY_DSN"),
        environment=os.getenv("SENTRY_ENVIRONMENT", "production"),
        traces_sample_rate=_parse_traces_sample_rate(),
        send_default_pii=_env_flag("SENTRY_SEND_DEFAULT_PII", "false"),
        enable_logs=_env_flag("SENTRY_ENABLE_LOGS", "true"),
        before_send=scrub_sentry_event,
    )
