from __future__ import annotations

from collections.abc import Mapping
from typing import Any


_LOCATION_VARIANTS = {
    "lower_back": "lower back",
    "upper_back": "upper back",
    "hip_flexor": "hip flexor",
    "si_joint": "si joint",
    "bicep": "biceps",
    "hamstrings": "hamstring",
    "glutes": "glute",
    "quads": "quad",
}


def canonicalize_location(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip().lower()
    if not cleaned:
        return None

    cleaned = cleaned.removeprefix("left ").removeprefix("right ").removeprefix("both ").strip()
    if not cleaned:
        return None
    return _LOCATION_VARIANTS.get(cleaned, cleaned)


def get_injury_location(entry: Mapping[str, Any] | None) -> str | None:
    if not isinstance(entry, Mapping):
        return None
    for key in ("canonical_location", "region", "location", "display_location", "area"):
        value = entry.get(key)
        normalized = canonicalize_location(value if isinstance(value, str) else None)
        if normalized:
            return normalized
    return None
