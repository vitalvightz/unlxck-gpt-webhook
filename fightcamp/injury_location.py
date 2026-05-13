from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .injury_location_registry import canonicalize_location_from_registry


def canonicalize_location(value: str | None) -> str | None:
    return canonicalize_location_from_registry(value)


def get_injury_location(entry: Mapping[str, Any] | None) -> str | None:
    if not isinstance(entry, Mapping):
        return None
    for key in ("canonical_location", "region", "location", "display_location", "area"):
        value = entry.get(key)
        normalized = canonicalize_location(value if isinstance(value, str) else None)
        if normalized:
            return normalized
    return None
