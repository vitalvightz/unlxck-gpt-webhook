"""Composable priority helpers for tight deterministic weekly allocation.

The existing planner owns baseline phase priorities and all safety suppression.
This module adds only bounded athlete-priority tie breaking and a late-camp cut
compression increment; it never selects a planner route or revives bridge logic.
"""

from __future__ import annotations

from typing import Any

from .goal_priority import role_goal_priority
from .late_camp_safety import aggressive_cut_extra_compression


def late_camp_week_reference_d_day(
    week_entry: dict[str, Any], athlete_model: dict[str, Any]
) -> int | None:
    """Resolve a conservative scheduled-day reference for weekly cut compression.

    Use the closest scheduled calendar D-day in the week when available. This
    keeps cut-load shaping tied to the actual sessions in the week rather than
    only to plan-generation day. Fall back to days_until_fight if calendar data
    is unavailable.
    """
    d_days: list[int] = []
    for day in week_entry.get("calendar_days") or []:
        try:
            d_day = int(day.get("d_day"))
        except (AttributeError, TypeError, ValueError):
            continue
        if d_day >= 0:
            d_days.append(d_day)
    if d_days:
        return min(d_days)
    try:
        value = int(athlete_model.get("days_until_fight"))
    except (TypeError, ValueError):
        return None
    return value if value >= 0 else None


def allocation_sort_key(
    *,
    base_rank: int,
    role: dict[str, Any],
    athlete_model: dict[str, Any],
    dedicated_recovery: bool = False,
) -> tuple[int, int, int]:
    """Return a stable sort key preserving safety/phase rank as first authority.

    Athlete goal priority only breaks roles that already share the same baseline
    planner rank; it cannot rescue a role that safety logic has demoted.
    """

    return (
        int(base_rank),
        int(role_goal_priority(role, athlete_model)),
        1 if dedicated_recovery else 0,
    )


def readiness_compression_floor_with_late_cut(
    *,
    base_floor: int,
    athlete_model: dict[str, Any],
    scheduled_d_day: int | None = None,
) -> int:
    """Add one bounded compression slot for high+ cuts in late normal camp."""

    return max(
        0,
        int(base_floor)
        + aggressive_cut_extra_compression(
            athlete_model,
            scheduled_d_day=scheduled_d_day,
        ),
    )
