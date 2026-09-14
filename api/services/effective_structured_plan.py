"""Resolve the one effective structured calendar for a persisted plan row."""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from collections.abc import Sequence
from typing import Any

from api.structured_plan_deterministic_fallback import build_deterministic_structured_plan
from api.structured_plan_models import safe_parse_structured_plan

logger = logging.getLogger(__name__)


def _mapping(value: Any) -> Mapping[str, Any] | None:
    if isinstance(value, Mapping):
        return value
    if isinstance(value, str) and value.strip():
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            return None
        return decoded if isinstance(decoded, Mapping) else None
    return None


def resolve_effective_structured_plan(
    plan_row: Mapping[str, Any], *, raw_markdown: str | None = None
) -> dict[str, Any] | None:
    """Return the valid stored card, or rebuild it from deterministic planner truth.

    Missing and malformed inputs fail closed. In particular, this resolver does
    not derive a calendar from broad recurring metadata.
    """

    stored = _mapping(plan_row.get("structured_plan"))
    if stored:
        parsed = safe_parse_structured_plan(stored, raw_markdown=raw_markdown or None)
        if parsed.ok and parsed.plan is not None:
            return dict(stored)
        # Some older cards predate the current strict display schema but still
        # carry the dated ``weeks`` calendar consumed by session services. Keep
        # their established behaviour; absence of that calendar is what permits
        # deterministic reconstruction.
        weeks = stored.get("weeks")
        if isinstance(weeks, Sequence) and not isinstance(weeks, (str, bytes, bytearray)):
            return dict(stored)
        logger.warning(
            "stored structured_plan failed validation; trying deterministic fallback plan_id=%s",
            plan_row.get("id"),
        )

    planning_brief = _mapping(plan_row.get("planning_brief"))
    fallback = build_deterministic_structured_plan(planning_brief)
    if fallback is None:
        return None
    parsed = safe_parse_structured_plan(fallback, raw_markdown=raw_markdown or None)
    if not parsed.ok or parsed.plan is None:
        logger.warning(
            "deterministic structured fallback failed validation plan_id=%s",
            plan_row.get("id"),
        )
        return None
    logger.info("deterministic effective structured plan assembled plan_id=%s", plan_row.get("id"))
    return fallback


__all__ = ["resolve_effective_structured_plan"]
