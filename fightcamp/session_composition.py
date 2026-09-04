"""Authoritative exercise composition for scheduled physical sessions.

Candidate pools remain planning evidence.  This module records the smaller,
deterministic set that the calendar actually assigned to each session; dose
resolution is deliberately downstream of this boundary.
"""

from __future__ import annotations

from typing import Any


def assignment_from_slot(phase: str, slot_group: str, slot: dict[str, Any]) -> dict[str, Any] | None:
    selected = slot.get("selected") if isinstance(slot.get("selected"), dict) else {}
    name = str(selected.get("name") or "").strip()
    if not name:
        return None
    return {
        "slot_id": slot.get("slot_id"),
        "name": name,
        "source_phase": phase,
        "slot_group": slot_group,
        "source_session_index": slot.get("session_index"),
    }


def compose_normal_strength_assignments(
    *, weekly_role_map: dict[str, Any], candidate_pools: dict[str, Any]
) -> dict[str, Any]:
    """Carry Stage 1's selected strength composition onto normal planner roles.

    A strength slot's ``selected`` option is composition truth; its alternates
    remain candidates.  All selected slots belonging to a full session are
    retained, so anchor, secondary, power and support work are not collapsed.
    Late-fight-owned roles are intentionally excluded and receive the shared
    late-fight selector's assignments instead.
    """
    for week in weekly_role_map.get("weeks", []) or []:
        if not isinstance(week, dict):
            continue
        phase = str(week.get("phase") or "").strip().upper()
        pool = candidate_pools.get(phase) if isinstance(candidate_pools, dict) else None
        slots = pool.get("strength_slots", []) if isinstance(pool, dict) else []
        strength_index = 0
        for role in week.get("session_roles", []) or []:
            if not isinstance(role, dict):
                continue
            is_strength = (
                str(role.get("category") or "").lower() == "strength"
                or str(role.get("preferred_pool") or "").lower() == "strength_slots"
            )
            if not is_strength:
                continue
            strength_index += 1
            if role.get("late_fight_tail_owned"):
                continue
            session_index = role.get("strength_session_index") or strength_index
            assignments = []
            for slot in slots:
                if not isinstance(slot, dict) or (slot.get("session_index") or 1) != session_index:
                    continue
                assignment = assignment_from_slot(phase, "strength_slots", slot)
                if assignment:
                    assignments.append(assignment)
            role["selected_exercise_assignments"] = assignments
    return weekly_role_map


def attach_late_fight_assignments(
    roles: list[dict[str, Any]], assignments_by_day: dict[str, list[dict[str, Any]]]
) -> None:
    """Attach the shared late-fight selector result to its scheduled roles."""
    for role in roles:
        if not isinstance(role, dict):
            continue
        label = str(role.get("scheduled_countdown_label") or role.get("countdown_label") or "").strip()
        selected = assignments_by_day.get(label, [])
        role["selected_exercise_assignments"] = [
            {**assignment, "source_phase": assignment.get("source_phase") or assignment.get("phase")}
            for assignment in selected
            if assignment.get("role_key") == role.get("role_key")
        ]
