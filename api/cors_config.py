"""CORS configuration helpers extracted from api.app (PR2: pure helpers)."""
from __future__ import annotations

import os
from urllib.parse import urlsplit

from .environment import is_production_environment


LOCAL_HOST_NAMES = ("localhost", "127.0.0.1", "::1")


def get_cors_origins() -> list[str]:
    value = os.getenv(
        "APP_CORS_ORIGINS",
        "http://127.0.0.1:3000,http://localhost:3000",
    )
    return [_normalize_origin(origin) for origin in value.split(",") if origin.strip()]


def _normalize_origin(origin: str) -> str:
    normalized = origin.strip()
    if not normalized:
        return ""
    if "://" not in normalized:
        host = normalized.split("/", 1)[0].lower()
        if host.startswith("[") and "]" in host:
            host_name = host[1:].split("]", 1)[0]
        else:
            host_name = host.split(":", 1)[0]
        scheme = "http" if host_name in LOCAL_HOST_NAMES else "https"
        normalized = f"{scheme}://{normalized}"
    parsed = urlsplit(normalized)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(f"APP_CORS_ORIGINS entries must be full origins. Received: {origin!r}")
    return f"{parsed.scheme}://{parsed.netloc}"


def get_cors_origin_regex() -> str | None:
    value = os.getenv("APP_CORS_ORIGIN_REGEX", "").strip()
    return value or None


def _allow_production_cors_regex() -> bool:
    return os.getenv("APP_ALLOW_PRODUCTION_CORS_REGEX", "").strip() == "1"


_UNSAFE_CORS_REGEX_PATTERNS = frozenset({".*", "^.*$", ".+", "^.+$", "^.*", ".*$", "^.+", ".+$"})


_UNSAFE_CORS_REGEX_SCHEME_PATTERNS = frozenset({
    "https://.*",
    "^https://.*$",
    "https://.+",
    "^https://.+$",
    "http://.*",
    "^http://.*$",
    "http://.+",
    "^http://.+$",
})


def _is_broad_cors_regex(regex: str) -> bool:
    normalized = regex.strip()
    if not normalized:
        return False
    if normalized in _UNSAFE_CORS_REGEX_PATTERNS:
        return True
    if normalized in _UNSAFE_CORS_REGEX_SCHEME_PATTERNS:
        return True
    return False


def validate_production_cors_config(origins: list[str], regex: str | None) -> None:
    if not is_production_environment():
        return

    violations: list[str] = []

    if not origins and not regex:
        violations.append(
            "APP_CORS_ORIGINS must list at least one origin "
            "in production"
        )

    for origin in origins:
        if origin == "*":
            violations.append("APP_CORS_ORIGINS cannot contain '*' in production")
            continue
        parsed = urlsplit(origin)
        host = (parsed.hostname or "").lower()
        netloc = (parsed.netloc or "").lower()
        if not host or "*" in netloc:
            violations.append(
                f"APP_CORS_ORIGINS cannot contain '*' wildcards in production: {origin!r}"
            )
            continue
        if host in LOCAL_HOST_NAMES:
            violations.append(
                f"APP_CORS_ORIGINS cannot contain localhost origins in production: {origin!r}"
            )

    if regex is not None:
        if not _allow_production_cors_regex():
            violations.append(
                "APP_CORS_ORIGIN_REGEX is disabled in production unless "
                "APP_ALLOW_PRODUCTION_CORS_REGEX=1 is set"
            )
        elif _is_broad_cors_regex(regex):
            violations.append(
                f"APP_CORS_ORIGIN_REGEX is too broad for production: {regex!r}"
            )

    if not violations:
        return

    raise ValueError(
        "Unsafe production CORS configuration. "
        "Refusing to boot with unsafe production CORS. "
        + "; ".join(violations)
    )
