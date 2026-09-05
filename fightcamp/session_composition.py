"""Authoritative exercise composition for scheduled physical sessions.

Candidate pools remain planning evidence.  This module records the smaller,
deterministic set that the calendar actually assigned to each session; dose
resolution is deliberately downstream of this boundary.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from .strength_session_quality import classify_strength_item


# These are ceilings, not targets. Stage 1 ranking still determines which
# exercises are strongest; composition only prevents a surviving strength role
# from inheriting an implausibly large or repetitive session after compression.
NORMAL_STRENGTH_ROLE_EXERCISE_CAPS: dict[str, int] = {
    "primary_strength_day": 5,
    "structural_strength_day": 5,
    "secondary_strength_day": 4,
    "neural_plus_strength_day": 4,
    "transfer_strength_day": 4,
    "strength_touch_day": 2,
    "small_strength_touch_day": 2,
    "neural_primer_day": 2,
}
DEFAULT_NORMAL_STRENGTH_EXERCISE_CAP = 4
MAX_COMPOSITION_FAMILY_EXPOSURES = 2


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


def _normal_strength_role_cap(role: dict[str, Any]) -> int:
    role_key = str(role.get("role_key") or "").strip().lower()
    return NORMAL_STRENGTH_ROLE_EXERCISE_CAPS.get(
        role_key, DEFAULT_NORMAL_STRENGTH_EXERCISE_CAP
    )


def _strength_composition_families(slot: dict[str, Any]) -> set[str]:
    """Project the existing strength classifier into a few session-level families.

    This deliberately introduces no new exercise taxonomy. The classifier already
    consumes the bank's tags, movement patterns, equipment and exercise identity;
    composition only groups its existing signals so repeated qualities can be
    bounded inside one scheduled session.
    """
    selected = slot.get("selected") if isinstance(slot.get("selected"), dict) else {}
    profile = classify_strength_item(selected)
    categories = set(profile.get("base_categories") or [])
    families: set[str] = set()

    if "lower_body_loaded" in categories:
        families.add("lower_strength")
    if "upper_body_push_pull" in categories:
        families.add("upper_strength")
    if "lower_body_power" in categories or "lower_body_ballistic" in categories:
        families.add("lower_power")
    if "rotational_power" in categories:
        families.add("rotational_power")
    if "upper_body_ballistic" in categories:
        families.add("upper_power")
    if profile.get("support_only") or slot.get("support_only"):
        families.add("support")

    return families


def _bounded_normal_strength_slots(
    slots: list[dict[str, Any]], *, role: dict[str, Any]
) -> list[dict[str, Any]]:
    """Keep ranked Stage 1 selections until the role cap or redundancy bound hits.

    Pool order remains authoritative ranking order. An exercise is skipped only
    when adding it would create a third exposure to one of the major composition
    families already represented twice. Exercises with no recognised family are
    still bounded by the role-level ceiling.
    """
    cap = _normal_strength_role_cap(role)
    family_counts: Counter[str] = Counter()
    kept: list[dict[str, Any]] = []

    for slot in slots:
        if len(kept) >= cap:
            break
        families = _strength_composition_families(slot)
        if any(
            family_counts[family] >= MAX_COMPOSITION_FAMILY_EXPOSURES
            for family in families
        ):
            continue
        kept.append(slot)
        family_counts.update(families)

    return kept


def compose_normal_strength_assignments(
    *, weekly_role_map: dict[str, Any], candidate_pools: dict[str, Any]
) -> dict[str, Any]:
    """Carry bounded Stage 1 strength composition onto normal planner roles.

    A strength slot's ``selected`` option is composition truth; its alternates
    remain candidates. Pool order stays authoritative, while role-specific
    exercise ceilings and the existing strength classifier prevent a compressed
    week from collapsing many selected slots into one oversized or repetitive
    session. Late-fight-owned roles are intentionally excluded and receive the
    shared late-fight selector's assignments instead.
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
            session_slots = [
                slot
                for slot in slots
                if isinstance(slot, dict)
                and (slot.get("session_index") or 1) == session_index
            ]
            bounded_slots = _bounded_normal_strength_slots(session_slots, role=role)
            assignments = []
            for slot in bounded_slots:
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
