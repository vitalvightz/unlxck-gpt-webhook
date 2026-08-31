"""Normal-camp calendar placement completion helpers.

This module owns the deterministic fallback that assigns a real training day to
any surviving normal-camp role the primary allocator left dayless. It deliberately
contains no new spacing, contact, compression, or load policy: Step 4 moves the
existing behaviour out of the rendering layer without changing planner output.

The broader renderer cleanup remains a later migration step. Until then,
``weekly_plan_render.fill_missing_session_days`` may re-export this function for
backward compatibility, but the implementation and placement mutation live here.
"""

from __future__ import annotations

from typing import Any

from .normalization import clean_list


_WEEKDAY_ORDER = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def fill_missing_session_days(weekly_role_map: dict[str, Any]) -> dict[str, Any]:
    """Assign ``scheduled_day_hint`` to surviving roles the planner left blank.

    This is intentionally byte-for-byte equivalent in behaviour to the legacy
    helper that lived in ``weekly_plan_render.py``:

    - preserve every existing scheduled day;
    - consider declared training days only;
    - use weekday order for the remaining free days;
    - never create extra roles or overwrite occupied days;
    - leave roles dayless when no declared free day remains.

    The function mutates and returns ``weekly_role_map``.
    """
    if not isinstance(weekly_role_map, dict):
        return weekly_role_map
    for week in weekly_role_map.get("weeks", []) or []:
        if not isinstance(week, dict):
            continue
        roles = [role for role in (week.get("session_roles") or []) if isinstance(role, dict)]
        used = {
            normalized
            for role in roles
            if (normalized := str(role.get("scheduled_day_hint") or "").strip().lower())
        }
        declared = [
            normalized
            for day in clean_list(week.get("declared_training_days"))
            if (normalized := str(day).strip().lower()) in _WEEKDAY_ORDER
        ]
        free = iter(day for day in sorted(set(declared), key=_WEEKDAY_ORDER.index) if day not in used)
        for role in roles:
            if str(role.get("scheduled_day_hint") or "").strip():
                continue
            day = next(free, "")
            if day:
                role["scheduled_day_hint"] = day.title()
    return weekly_role_map
