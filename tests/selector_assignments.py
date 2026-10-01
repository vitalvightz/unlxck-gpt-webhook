"""Stand-in for the Stage 1 selector in resolver-level tests.

``apply_effective_strength_prescriptions`` resolves only the slots a role's
``selected_exercise_assignments`` names: candidate slots in the pool are
diagnostics and never prescription authority. In production the selector writes
that field; tests that hand-build a weekly role map must do the same, or the
resolver correctly resolves nothing.

``apply_with_selected_membership`` assigns every candidate slot that belongs to
a strength role's session (the grouping the resolver used before membership
became authoritative) and then runs the real resolver. Roles that already carry
``selected_exercise_assignments`` are left untouched.
"""
from __future__ import annotations

from typing import Any

from fightcamp.prescription_resolver import (
    _int_or_none,
    _is_strength_role,
    _strength_slots_for_phase,
    apply_effective_strength_prescriptions,
)
from fightcamp.session_composition import assignment_from_slot


def assign_selected_membership(
    weekly_role_map: dict[str, Any], candidate_pools: dict[str, Any]
) -> None:
    for week in weekly_role_map.get("weeks") or []:
        if not isinstance(week, dict):
            continue
        phase = str(week.get("phase") or "").strip().upper()
        slots = _strength_slots_for_phase(candidate_pools, phase)
        ordinal = 0
        for role in week.get("session_roles") or []:
            if not isinstance(role, dict) or not _is_strength_role(role):
                continue
            ordinal += 1
            if isinstance(role.get("selected_exercise_assignments"), list):
                continue
            session_index = _int_or_none(role.get("strength_session_index")) or ordinal
            assignments = [
                assignment_from_slot(phase, "strength_slots", slot)
                for slot in slots
                if (_int_or_none(slot.get("session_index")) or 1) == session_index
            ]
            role["selected_exercise_assignments"] = [item for item in assignments if item]


def apply_with_selected_membership(
    *,
    weekly_role_map: dict[str, Any],
    candidate_pools: dict[str, Any],
    athlete_model: dict[str, Any] | None = None,
) -> dict[str, Any]:
    assign_selected_membership(weekly_role_map, candidate_pools)
    return apply_effective_strength_prescriptions(
        weekly_role_map=weekly_role_map,
        candidate_pools=candidate_pools,
        athlete_model=athlete_model,
    )
