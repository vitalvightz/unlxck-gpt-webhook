"""Composable priority helpers for tight deterministic weekly allocation.

The existing planner owns baseline phase priorities and all safety suppression.
This module adds only bounded athlete-priority tie breaking and a late-camp cut
compression increment; it never selects a planner route or revives bridge logic.
"""

from __future__ import annotations

from typing import Any

from .goal_priority import role_goal_priority
from .late_camp_safety import aggressive_cut_extra_compression


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
