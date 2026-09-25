"""Resolve the one effective structured calendar for a persisted plan row."""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from collections.abc import Sequence
from datetime import date
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


def _has_usable_dated_calendar(plan: Mapping[str, Any]) -> bool:
    weeks = plan.get("weeks")
    if not isinstance(weeks, Sequence) or isinstance(weeks, (str, bytes, bytearray)):
        return False
    for week in weeks:
        if not isinstance(week, Mapping):
            continue
        days = week.get("days")
        if not isinstance(days, Sequence) or isinstance(days, (str, bytes, bytearray)):
            continue
        for day in days:
            if not isinstance(day, Mapping):
                continue
            try:
                date.fromisoformat(str(day.get("date") or "")[:10])
            except ValueError:
                continue
            return True
    return False


def _has_usable_open_weekly_calendar(
    plan_row: Mapping[str, Any], plan: Mapping[str, Any]
) -> bool:
    """Recognise the older renewable cards whose rows are weekday templates."""

    if str(plan_row.get("fight_date") or "").strip():
        return False
    weeks = plan.get("weeks")
    if not isinstance(weeks, Sequence) or not weeks:
        return False
    valid_weekdays = {"mon", "tue", "wed", "thu", "fri", "sat", "sun"}
    for week in weeks:
        if not isinstance(week, Mapping):
            return False
        days = week.get("days")
        if not isinstance(days, Sequence) or len(days) < 2:
            return False
        if any(
            not isinstance(day, Mapping)
            or str(day.get("weekday") or "").strip().lower()[:3] not in valid_weekdays
            for day in days
        ):
            return False
    return True


def resolve_effective_structured_plan(
    plan_row: Mapping[str, Any], *, raw_markdown: str | None = None
) -> dict[str, Any] | None:
    """Return the valid stored card, or rebuild it from deterministic planner truth.

    Missing and malformed inputs fail closed. In particular, this resolver does
    not derive a calendar from broad recurring metadata.
    """

    legacy_open_calendar: dict[str, Any] | None = None
    stored = _mapping(plan_row.get("structured_plan"))
    if stored:
        parsed = safe_parse_structured_plan(stored, raw_markdown=raw_markdown or None)
        if parsed.ok and parsed.plan is not None:
            return dict(stored)
        # Some older cards predate the current strict display schema but still
        # carry the dated ``weeks`` calendar consumed by session services. Keep
        # their established behaviour; absence of that calendar is what permits
        # deterministic reconstruction.
        if _has_usable_dated_calendar(stored):
            return dict(stored)
        if _has_usable_open_weekly_calendar(plan_row, stored):
            # Try planner reconstruction first. This is retained only for old
            # renewable plans whose canonical cards are weekday templates.
            legacy_open_calendar = dict(stored)
        logger.warning(
            "stored structured_plan failed validation; trying deterministic fallback plan_id=%s",
            plan_row.get("id"),
        )

    planning_brief = _mapping(plan_row.get("planning_brief"))
    # Every surface (plan view, Today, progress) reads the same athlete-visible
    # plan text, so the rebuilt card carries the doses the athlete was given
    # wherever it renders. A held plan's unreleased text is never read here.
    plan_text = raw_markdown or str(plan_row.get("plan_text") or "")
    fallback = build_deterministic_structured_plan(planning_brief, plan_text=plan_text or None)
    if fallback is None:
        return legacy_open_calendar
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
