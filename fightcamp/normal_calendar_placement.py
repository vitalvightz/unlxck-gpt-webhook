"""Normal-camp calendar placement completion helpers.

This module owns the deterministic fallback that assigns a real training day to
any surviving normal-camp role the primary allocator left dayless. It contains no
role-budget, compression, or contact-resolution policy of its own.

As of Step 8 the renderer is read-only and no longer re-exports this function:
placement (this helper plus the allocator) is owned here, and the renderer reads
the assigned ``scheduled_day_hint`` without importing or completing missing days.

As of Step 9B this completion consults the same shared ``combat_load_policy``
legality the allocator does (through the canonical ``calendar_context`` adapter):
it fills a role onto a free declared day only when the policy does not FORBID that
day for the role, so completion can never re-introduce a forbidden placement the
allocator deliberately declined. Legality is not decided here — the policy remains
the rule authority, and a week with no resolved contact context evaluates every
day as ALLOW, preserving the legacy weekday-order behaviour exactly.
"""

from __future__ import annotations

from typing import Any

from .calendar_context import classify_role, normal_week_legality, week_scope
from .normalization import clean_list


_WEEKDAY_ORDER = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def fill_missing_session_days(weekly_role_map: dict[str, Any]) -> dict[str, Any]:
    """Assign ``scheduled_day_hint`` to surviving roles the planner left blank.

    Behaviour:

    - preserve every existing scheduled day;
    - consider declared training days only;
    - use weekday order for the remaining free days, but skip a day the shared
      policy FORBIDs for the role (ALLOW preferred over DEPRIORITIZE);
    - never create extra roles or overwrite occupied days;
    - leave a role dayless when no legal free declared day remains.

    With no resolved contact context the legality view has no events and every day
    is ALLOW, so this is byte-for-byte the legacy weekday-order fill. The function
    mutates and returns ``weekly_role_map``.
    """
    if not isinstance(weekly_role_map, dict):
        return weekly_role_map
    for ordinal, week in enumerate(weekly_role_map.get("weeks", []) or [], start=1):
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
        ordered_declared = sorted(set(declared), key=_WEEKDAY_ORDER.index)
        legality = normal_week_legality(
            week.get("hard_sparring_plan"),
            week.get("declared_hard_sparring_days"),
            scope=week_scope(week, ordinal),
        )
        for role in roles:
            if str(role.get("scheduled_day_hint") or "").strip():
                continue
            free = [day for day in ordered_declared if day not in used]
            if not free:
                continue
            profile = classify_role(role)
            if profile is None:
                # Unclassifiable role: legality is not ours to decide, keep the
                # legacy weekday-order pick.
                day = free[0]
            else:
                day = legality.best_legal_weekday(profile, free)
            if day:
                role["scheduled_day_hint"] = day.title()
                used.add(day)
    return weekly_role_map
