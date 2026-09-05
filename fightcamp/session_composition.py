"""Authoritative exercise composition for scheduled physical sessions.

Candidate pools remain planning evidence. This module records the smaller,
deterministic set that the calendar actually assigns to each session; dose
resolution remains downstream of this boundary.

Normal strength composition is deliberately reduce-only:
- Stage 1's selected slots are the only candidates considered.
- session role sets the fresh-state exercise ceiling;
- fatigue, weight-cut severity, and injury state can only tighten that ceiling;
- existing exercise tags/classification prevent redundant same-quality loading;
- Stage 2 receives the final closed membership and never chooses replacements.
"""

from __future__ import annotations

from typing import Any

from .normalization import normalize_fatigue_level
from .planner_context import get_planner_athlete_model
from .strength_session_quality import classify_strength_item
from .weight_cut import compute_cut_severity_score, cut_severity_bucket


_NORMAL_STRENGTH_ROLE_CAPS: dict[str, int] = {
    "primary_strength_day": 5,
    "structural_strength_day": 5,
    "secondary_strength_day": 4,
    "neural_plus_strength_day": 4,
    "transfer_strength_day": 4,
    "strength_touch_day": 2,
    "neural_primer_day": 2,
    "small_strength_touch_day": 2,
}
_DEFAULT_NORMAL_STRENGTH_CAP = 4

_FATIGUE_PRESSURE = {"low": 0, "moderate": 1, "high": 2}
_CUT_PRESSURE = {
    "none": 0,
    "low": 0,
    "moderate": 1,
    "high": 2,
    "critical": 3,
    "extreme": 3,
}

_STRENGTH_FAMILIES = frozenset({"lower_strength", "upper_strength"})
_POWER_FAMILIES = frozenset({"lower_power", "rotational_power", "upper_power"})

_ROLE_REQUIRED_FAMILY_GROUPS: dict[str, tuple[frozenset[str], ...]] = {
    "primary_strength_day": (_STRENGTH_FAMILIES,),
    "structural_strength_day": (_STRENGTH_FAMILIES,),
    "secondary_strength_day": (_STRENGTH_FAMILIES,),
    "neural_plus_strength_day": (_POWER_FAMILIES, _STRENGTH_FAMILIES),
    "transfer_strength_day": (_POWER_FAMILIES, _STRENGTH_FAMILIES),
}


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


def _normalized_fatigue(athlete_model: dict[str, Any]) -> str:
    return normalize_fatigue_level(athlete_model)


def _resolved_cut_bucket(athlete_model: dict[str, Any]) -> str:
    bucket = str(athlete_model.get("cut_severity_bucket") or "").strip().lower()
    if bucket in _CUT_PRESSURE:
        return bucket

    flags = {
        str(flag).strip().lower()
        for flag in (athlete_model.get("readiness_flags") or [])
        if str(flag).strip()
    }
    active_cut = bool(athlete_model.get("weight_cut_risk")) or bool(
        flags & {"active_weight_cut", "aggressive_weight_cut", "extreme_weight_cut"}
    )
    if not active_cut:
        return "none"

    score = athlete_model.get("cut_severity_score")
    if score is None:
        score = compute_cut_severity_score(
            athlete_model.get("weight_cut_pct"),
            athlete_model.get("days_until_fight"),
        )
    return cut_severity_bucket(score)


def _injury_restricted(athlete_model: dict[str, Any]) -> bool:
    flags = {
        str(flag).strip().lower()
        for flag in (athlete_model.get("readiness_flags") or [])
        if str(flag).strip()
    }
    injuries = athlete_model.get("injuries") or athlete_model.get("parsed_injuries") or []
    return bool(injuries) or "injury_management" in flags


def composition_pressure_state(athlete_model: dict[str, Any] | None) -> dict[str, Any]:
    """Resolve reduce-only session-composition pressure from existing athlete buckets.

    The strongest active signal owns the base pressure. A second independent
    stressor adds one interaction step, capped at preservation mode (3). This
    avoids naively summing three moderate signals while still recognising that
    combined fatigue/cut/injury meaningfully reduces recovery capacity.
    """
    model = athlete_model if isinstance(athlete_model, dict) else {}
    fatigue = _normalized_fatigue(model)
    cut_bucket = _resolved_cut_bucket(model)
    injury_restricted = _injury_restricted(model)

    fatigue_pressure = _FATIGUE_PRESSURE[fatigue]
    cut_pressure = _CUT_PRESSURE[cut_bucket]
    injury_pressure = 1 if injury_restricted else 0
    pressures = (fatigue_pressure, cut_pressure, injury_pressure)
    active_stressors = sum(value > 0 for value in pressures)

    pressure = max(pressures, default=0)
    if active_stressors >= 2:
        pressure += 1
    pressure = min(3, pressure)

    return {
        "pressure": pressure,
        "fatigue": fatigue,
        "fatigue_pressure": fatigue_pressure,
        "cut_severity_bucket": cut_bucket,
        "cut_pressure": cut_pressure,
        "injury_restricted": injury_restricted,
        "injury_pressure": injury_pressure,
        "active_stressors": active_stressors,
    }


def _effective_role_cap(role_key: str, pressure: int) -> tuple[int, int]:
    base_cap = _NORMAL_STRENGTH_ROLE_CAPS.get(role_key, _DEFAULT_NORMAL_STRENGTH_CAP)
    if pressure <= 0:
        return base_cap, base_cap
    if pressure == 1:
        return base_cap, max(2, base_cap - 1)
    if pressure == 2:
        return base_cap, max(2, base_cap - 2)
    return base_cap, 2


def _slot_selected_item(slot: dict[str, Any]) -> dict[str, Any]:
    selected = slot.get("selected") if isinstance(slot.get("selected"), dict) else {}
    merged = {
        key: value
        for key, value in slot.items()
        if key not in {"selected", "alternates"}
    }
    merged.update(selected)
    return merged


def _composition_families(slot: dict[str, Any]) -> tuple[set[str], dict[str, Any]]:
    profile = classify_strength_item(_slot_selected_item(slot))
    categories = set(profile.get("base_categories") or [])
    families: set[str] = set()
    if "lower_body_loaded" in categories:
        families.add("lower_strength")
    if "upper_body_push_pull" in categories:
        families.add("upper_strength")
    if "lower_body_power" in categories:
        families.add("lower_power")
    if "rotational_power" in categories:
        families.add("rotational_power")
    if "upper_body_ballistic" in categories:
        families.add("upper_power")
    if profile.get("support_only"):
        families.add("support")
    return families, profile


def _slot_priority(slot: dict[str, Any], original_index: int) -> tuple[int, int]:
    try:
        priority = int(slot.get("priority"))
    except (TypeError, ValueError):
        priority = 10_000
    return priority, original_index


def _candidate_records(slots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for index, slot in enumerate(slots):
        assignment = assignment_from_slot("", "strength_slots", slot)
        if not assignment:
            continue
        families, profile = _composition_families(slot)
        records.append(
            {
                "slot": slot,
                "name": assignment["name"],
                "families": families,
                "support_only": bool(profile.get("support_only")),
                "sort_key": _slot_priority(slot, index),
                "original_index": index,
            }
        )
    return sorted(
        records,
        key=lambda item: (
            1 if item["support_only"] else 0,
            item["sort_key"][0],
            item["sort_key"][1],
        ),
    )


def _would_exceed_family_limit(
    families: set[str],
    family_counts: dict[str, int],
    family_limit: int,
) -> bool:
    major = families - {"support"}
    return any(family_counts.get(family, 0) >= family_limit for family in major)


def _add_record(
    record: dict[str, Any],
    selected: list[dict[str, Any]],
    family_counts: dict[str, int],
) -> None:
    selected.append(record)
    for family in record["families"]:
        family_counts[family] = family_counts.get(family, 0) + 1


def _select_bounded_records(
    records: list[dict[str, Any]],
    *,
    role_key: str,
    cap: int,
    pressure: int,
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    family_limit = 2 if pressure <= 1 else 1
    selected: list[dict[str, Any]] = []
    family_counts: dict[str, int] = {}
    dropped: dict[str, str] = {}

    required_groups = _ROLE_REQUIRED_FAMILY_GROUPS.get(role_key, ())
    for required_group in required_groups:
        if len(selected) >= cap:
            break
        covered = set().union(*(item["families"] for item in selected)) if selected else set()
        if covered & required_group:
            continue
        for record in records:
            if record in selected or not (record["families"] & required_group):
                continue
            if _would_exceed_family_limit(record["families"], family_counts, family_limit):
                continue
            _add_record(record, selected, family_counts)
            break

    for record in records:
        if len(selected) >= cap:
            break
        if record in selected:
            continue
        if _would_exceed_family_limit(record["families"], family_counts, family_limit):
            dropped[record["name"]] = "redundant_major_family"
            continue
        _add_record(record, selected, family_counts)

    selected_ids = {id(item) for item in selected}
    for record in records:
        if id(record) in selected_ids:
            continue
        dropped.setdefault(record["name"], "role_or_readiness_cap")

    return selected, dropped


def _pressure_state_from_map(weekly_role_map: dict[str, Any]) -> dict[str, Any] | None:
    state = weekly_role_map.get("strength_composition_context")
    if not isinstance(state, dict):
        return None
    try:
        pressure = int(state.get("pressure"))
    except (TypeError, ValueError):
        return None
    if pressure not in {0, 1, 2, 3}:
        return None
    return dict(state)


def compose_normal_strength_assignments(
    *, weekly_role_map: dict[str, Any], candidate_pools: dict[str, Any]
) -> dict[str, Any]:
    """Carry bounded Stage 1 strength composition onto normal planner roles.

    Closed membership remains Stage 1 authority. This function never chooses an
    alternate and never invents an exercise. It only prunes already-selected
    slots using role ceilings, athlete recovery pressure, and existing movement
    tags. Late-fight-owned roles are excluded and keep their dedicated selector.
    """
    athlete_model = get_planner_athlete_model()
    pressure_state = (
        composition_pressure_state(athlete_model)
        if athlete_model is not None
        else _pressure_state_from_map(weekly_role_map)
    )
    if pressure_state is None:
        pressure_state = composition_pressure_state(None)

    weekly_role_map["strength_composition_context"] = dict(pressure_state)
    pressure = int(pressure_state["pressure"])

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
            owned_slots = [
                slot
                for slot in slots
                if isinstance(slot, dict) and (slot.get("session_index") or 1) == session_index
            ]
            records = _candidate_records(owned_slots)
            role_key = str(role.get("role_key") or "").strip()
            base_cap, effective_cap = _effective_role_cap(role_key, pressure)
            selected_records, dropped = _select_bounded_records(
                records,
                role_key=role_key,
                cap=effective_cap,
                pressure=pressure,
            )

            assignments: list[dict[str, Any]] = []
            for record in selected_records:
                assignment = assignment_from_slot(phase, "strength_slots", record["slot"])
                if assignment:
                    assignments.append(assignment)
            role["selected_exercise_assignments"] = assignments
            role["strength_composition_policy"] = {
                **pressure_state,
                "role_key": role_key,
                "base_exercise_cap": base_cap,
                "effective_exercise_cap": effective_cap,
                "major_family_limit": 2 if pressure <= 1 else 1,
                "selected_count": len(assignments),
                "selected_names": [item["name"] for item in assignments],
                "dropped": [
                    {"name": name, "reason": reason}
                    for name, reason in dropped.items()
                ],
            }
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
