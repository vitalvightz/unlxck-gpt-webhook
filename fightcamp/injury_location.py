from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def get_injury_location(entry: Mapping[str, Any] | None) -> str | None:
    if not isinstance(entry, Mapping):
        return None
    for key in ("canonical_location", "region", "location", "display_location", "area"):
        value = entry.get(key)
        if isinstance(value, str):
            cleaned = value.strip().lower()
            if cleaned:
                return cleaned
    return None
