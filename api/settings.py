"""Typed reads of the environment variables the API and worker are tuned with.

One set of rules for every setting: unset or blank means the default; a value
that does not parse logs a warning and falls back to the default; a value
outside the setting's bounds is clamped to them. Settings are read when they
are used, not cached at import, so a deploy can change them per process and
tests can set them per test.
"""

from __future__ import annotations

import logging
import math
import os

logger = logging.getLogger(__name__)

_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_FALSE_VALUES = frozenset({"0", "false", "no", "off"})


def _raw(name: str) -> str | None:
    value = os.getenv(name)
    if value is None or not value.strip():
        return None
    return value.strip()


def _clamp(value: float, minimum: float | None, maximum: float | None) -> float:
    if minimum is not None:
        value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


def env_int(name: str, default: int, *, minimum: int | None = None, maximum: int | None = None) -> int:
    raw = _raw(name)
    if raw is None:
        return default
    try:
        parsed = int(raw)
    except ValueError:
        logger.warning("[config] invalid integer %s=%r; using %s", name, raw, default)
        return default
    return int(_clamp(parsed, minimum, maximum))


def env_float(
    name: str,
    default: float,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
    positive: bool = False,
) -> float:
    """A float setting. ``positive`` rejects zero, negatives and non-finite values."""
    raw = _raw(name)
    if raw is None:
        return float(_clamp(default, minimum, maximum))
    try:
        parsed = float(raw)
    except ValueError:
        logger.warning("[config] invalid number %s=%r; using %s", name, raw, default)
        return float(_clamp(default, minimum, maximum))
    if positive and (not math.isfinite(parsed) or parsed <= 0):
        logger.warning("[config] non-positive %s=%r; using %s", name, raw, default)
        return float(_clamp(default, minimum, maximum))
    return float(_clamp(parsed, minimum, maximum))


def env_flag(name: str, default: bool = False) -> bool:
    """On for 1/true/yes/on, off for 0/false/no/off (any case); otherwise the default."""
    raw = _raw(name)
    if raw is None:
        return default
    lowered = raw.lower()
    if lowered in _TRUE_VALUES:
        return True
    if lowered in _FALSE_VALUES:
        return False
    logger.warning("[config] invalid flag %s=%r; using %s", name, raw, default)
    return default


def env_str(name: str, default: str = "") -> str:
    raw = _raw(name)
    return default if raw is None else raw


def env_csv(name: str, *, lower: bool = False) -> tuple[str, ...]:
    """Comma-separated values, stripped, blanks dropped."""
    items = (item.strip() for item in (os.getenv(name) or "").split(","))
    return tuple(item.lower() if lower else item for item in items if item)
