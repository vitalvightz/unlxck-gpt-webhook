"""Composable priority helpers for tight deterministic weekly allocation.

The existing planner owns baseline phase priorities and all safety suppression.
This module adds only bounded athlete-priority tie breaking; it never selects a
planner route, revives bridge logic, or removes weekly capacity. Cut-driven
capacity charges belong to ``weight_cut.cut_training_compression_points`` alone.
"""

from __future__ import annotations

from typing import Any

from .goal_priority import role_goal_priority


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
