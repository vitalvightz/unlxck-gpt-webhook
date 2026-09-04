"""Canonical sport identity and explicit planning-family reuse.

Identity normalization preserves unknown tokens for strict sport filtering.
Only planning_format applies the legacy MMA fallback, with an audit warning.
"""
from __future__ import annotations

import logging
import re
from typing import Any

SUPPORTED_SPORTS = ("boxing", "kickboxing", "muay_thai", "mma", "wrestling", "bjj")

SPORT_ALIASES = {
    "karate": "karate",
    "grappler": "grappling",
    "grappling": "grappling",
    "boxer": "boxing",
    "boxing": "boxing",
    "kickboxer": "kickboxing",
    "kickboxing": "kickboxing",
    "muay_thai": "muay_thai",
    "muaythai": "muay_thai",
    "mma": "mma",
    "mixed_martial_arts": "mma",
    "wrestler": "wrestling",
    "wrestling": "wrestling",
    "bjj": "bjj",
    "jiu_jitsu": "bjj",
    "brazilian_jiu_jitsu": "bjj",
}

PLANNING_FAMILIES = {
    "karate": "kickboxing",
    "boxing": "boxing",
    "kickboxing": "kickboxing",
    "muay_thai": "muay_thai",
    "mma": "mma",
    "wrestling": "mma",
    "bjj": "mma",
    "grappling": "mma",
}

# Compatibility export for callers that previously imported STYLE_MAP.
# Runtime consumers should call planning_format to handle aliases and fallback.
STYLE_MAP = {alias: PLANNING_FAMILIES[sport] for alias, sport in SPORT_ALIASES.items()}
STYLE_MAP["muay thai"] = "muay_thai"


def normalize_sport(value: Any) -> str:
    """Return canonical identity; never collapse wrestling/BJJ into MMA."""
    token = re.sub(r"[\s_\-/.+]+", "_", str(value or "").strip().lower()).strip("_")
    return SPORT_ALIASES.get(token, token)


def planning_format(value: Any, *, fallback: str | None = "mma") -> str | None:
    """Resolve phase/energy weights, explicitly auditing unsupported input.

    Nutrition passes fallback=None to retain its date-only phase estimate.
    """
    sport = normalize_sport(value)
    if sport in PLANNING_FAMILIES:
        return PLANNING_FAMILIES[sport]
    logging.getLogger(__name__).warning(
        "unsupported_sport_planning_fallback sport=%r fallback=%r", sport, fallback
    )
    return fallback
