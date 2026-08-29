"""Integration helpers for stage2_role_map allocator safeguards.

These wrappers keep the large role-map module focused while composing the
new scarce-capacity goal tie-break and scheduled-day high-cut compression
without changing planner routing.
"""

from __future__ import annotations

from typing import Any

from .allocator_priority import allocation_sort_key, readiness_compression_floor_with_late_cut


def late_camp_week_reference_d_day(week_entry: dict[str, Any], athlete_model: dict[str, Any]) -> int | None:
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


def integrated_compression_floor(
    *,
    base_floor: int,
    week_entry: dict[str, Any],
    athlete_model: dict[str, Any],
) -> int:
    """Apply the bounded high+ cut increment to the existing compression floor."""
    return readiness_compression_floor_with_late_cut(
        base_floor=base_floor,
        athlete_model=athlete_model,
        scheduled_d_day=late_camp_week_reference_d_day(week_entry, athlete_model),
    )


def integrated_allocation_sort_key(
    *,
    role: dict[str, Any],
    base_rank: int,
    athlete_model: dict[str, Any],
) -> tuple[int, int, int]:
    """Compose baseline rank with bounded athlete-goal tie breaking."""
    return allocation_sort_key(
        base_rank=base_rank,
        role=role,
        athlete_model=athlete_model,
        dedicated_recovery=role.get("is_dedicated_recovery_mobility_day") is True,
    )
