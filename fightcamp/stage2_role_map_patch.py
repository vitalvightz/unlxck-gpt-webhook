"""Small adapter functions used by stage2_role_map.

This module exists to keep the integration explicit and testable while the
large role-map module remains the source of truth for baseline priorities.
"""

from __future__ import annotations

from typing import Any, Callable

from .stage2_role_map_integration import (
    integrated_allocation_sort_key,
    integrated_compression_floor,
)


def compute_integrated_compression_floor(
    *,
    base_floor: int,
    week_entry: dict[str, Any],
    athlete_model: dict[str, Any],
) -> int:
    return integrated_compression_floor(
        base_floor=base_floor,
        week_entry=week_entry,
        athlete_model=athlete_model,
    )


def build_integrated_role_sort_key(
    *,
    role: dict[str, Any],
    base_rank_fn: Callable[[dict[str, Any]], int],
    athlete_model: dict[str, Any],
) -> tuple[int, int, int]:
    return integrated_allocation_sort_key(
        role=role,
        base_rank=base_rank_fn(role),
        athlete_model=athlete_model,
    )
