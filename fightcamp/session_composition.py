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

import re
from typing import Any

from .normalization import normalize_fatigue_level
from .planner_context import get_planner_athlete_model
from .late_fight_phase_eligibility import scheduled_phase_for_role
from .calendar_context import role_d_day
from .calendar_integrity import relocate_or_suppress_role_for_recovery
from .prescription_resolver import has_verified_low_cost
from .strength_session_quality import classify_strength_item
from .training_context import normalize_equipment_list
from .config import (
    athlete_round_seconds,
    conditioning_effective_dose,
    conditioning_round_prescription,
    conditioning_dose_active_work_seconds,
    conditioning_dose_minutes,
    conditioning_phase_workload_envelope as _conditioning_phase_workload_envelope,
)
from .weight_cut import compute_cut_severity_score, cut_severity_bucket


_NORMAL_STRENGTH_ROLE_CAPS: dict[str, int] = {
    "primary_strength_day": 4,
    "structural_strength_day": 4,
    "secondary_strength_day": 3,
    "neural_plus_strength_day": 3,
    "transfer_strength_day": 3,
    "strength_touch_day": 2,
    "neural_primer_day": 2,
    "small_strength_touch_day": 2,
}
_DEFAULT_NORMAL_STRENGTH_CAP = 3

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

_ADJACENT_STRENGTH_RECOVERY_COST_FIELDS = (
    "movement_cost",
    "impact_cost",
    "eccentric_cost",
    "landing_cost",
    "cns_load",
    "soreness_risk",
)
_ADJACENT_STRENGTH_RECOVERY_REASON = "substantial_repeated_mechanical_loading"

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
    assignment = {
        "slot_id": slot.get("slot_id"),
        "name": name,
        "source_phase": phase,
        "slot_group": slot_group,
        "source_session_index": slot.get("session_index"),
    }
    base_prescription = str(selected.get("prescription") or "").strip()
    if base_prescription:
        assignment["base_prescription"] = base_prescription
    notes = _selected_coaching_notes(selected)
    if notes:
        assignment["coaching_notes"] = notes
    return assignment


def _selected_coaching_notes(option: dict[str, Any] | None) -> str:
    """Return the authored exercise-bank coaching note for a selected option.

    The note travels with the selected assignment so Stage 2 keeps the bank's
    execution guidance without a separate join back to the candidate pool. It is
    coaching evidence only and never a dose authority.
    """
    if not isinstance(option, dict):
        return ""
    note = option.get("notes")
    if not str(note or "").strip():
        metadata = option.get("selection_metadata")
        if isinstance(metadata, dict):
            note = metadata.get("notes")
    return str(note or "").strip()


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


def _pressure_state_from_components(
    *, fatigue: str, cut_bucket: str, injury_restricted: bool
) -> dict[str, Any]:
    fatigue = fatigue if fatigue in _FATIGUE_PRESSURE else "low"
    cut_bucket = cut_bucket if cut_bucket in _CUT_PRESSURE else "none"

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


def composition_pressure_state(athlete_model: dict[str, Any] | None) -> dict[str, Any]:
    """Resolve reduce-only session-composition pressure from existing athlete buckets.

    The strongest active signal owns the base pressure. A second independent
    stressor adds one interaction step, capped at preservation mode (3). This
    avoids naively summing three moderate signals while still recognising that
    combined fatigue/cut/injury meaningfully reduces recovery capacity.
    """
    model = athlete_model if isinstance(athlete_model, dict) else {}
    return _pressure_state_from_components(
        fatigue=_normalized_fatigue(model),
        cut_bucket=_resolved_cut_bucket(model),
        injury_restricted=_injury_restricted(model),
    )


def _float_or_none(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed


def _int_or_none(value: Any) -> int | None:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _active_weight_cut(
    athlete_model: dict[str, Any], *, current_bucket: str, cut_pct: float | None
) -> bool:
    flags = {
        str(flag).strip().lower()
        for flag in (athlete_model.get("readiness_flags") or [])
        if str(flag).strip()
    }
    return bool(
        athlete_model.get("weight_cut_risk")
        or flags & {"active_weight_cut", "aggressive_weight_cut", "extreme_weight_cut"}
        or (cut_pct is not None and cut_pct > 0.0)
        or current_bucket not in {"", "none"}
    )


def _composition_context_from_model(athlete_model: dict[str, Any] | None) -> dict[str, Any]:
    model = athlete_model if isinstance(athlete_model, dict) else {}
    current_state = composition_pressure_state(model)
    cut_pct = _float_or_none(model.get("weight_cut_pct"))
    if cut_pct is not None and cut_pct <= 0.0:
        cut_pct = None

    return {
        **current_state,
        "generation_days_until_fight": _int_or_none(model.get("days_until_fight")),
        "weight_cut_pct": cut_pct,
        "active_weight_cut": _active_weight_cut(
            model,
            current_bucket=str(current_state["cut_severity_bucket"]),
            cut_pct=cut_pct,
        ),
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
    """Map existing Stage 1 quality metadata into broad session families.

    Stage 1 already serializes ``base_categories`` and ``support_only`` from the
    exercise classifier. Those fields are preferred as authoritative evidence;
    reclassification is only a fallback/union for older or hand-built slots.
    """
    item = _slot_selected_item(slot)
    profile = classify_strength_item(item)
    categories = {
        str(value).strip()
        for value in [
            *(slot.get("base_categories") or []),
            *(item.get("base_categories") or []),
            *(profile.get("base_categories") or []),
        ]
        if str(value).strip()
    }
    support_only = bool(
        slot.get("support_only")
        or item.get("support_only")
        or profile.get("support_only")
    )

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
    if support_only:
        families.add("support")

    effective_profile = dict(profile)
    effective_profile["base_categories"] = sorted(categories)
    effective_profile["support_only"] = support_only
    return families, effective_profile


def _serialized_quality_class(slot: dict[str, Any]) -> str:
    item = _slot_selected_item(slot)
    return str(slot.get("quality_class") or item.get("quality_class") or "").strip()


def _slot_uses_loaded_equipment(slot: dict[str, Any]) -> bool:
    item = _slot_selected_item(slot)
    equipment = normalize_equipment_list(item.get("equipment") or [])
    return bool(
        {
            "barbell",
            "trap_bar",
            "dumbbell",
            "dumbbells",
            "kettlebell",
            "kettlebells",
            "cable",
            "landmine",
            "sandbag",
            "bulgarian_bag",
            "log",
            "atlas_stone",
            "water_jug",
            "weight_vest",
            "plate",
            "partner",
        }
        & set(equipment)
    )


def _slot_has_core_balance_signal(slot: dict[str, Any]) -> bool:
    item = _slot_selected_item(slot)
    tags = {
        re.sub(r"[^a-z0-9]+", "_", str(value).strip().lower()).strip("_")
        for value in [
            *(slot.get("tags") or []),
            *(item.get("tags") or []),
            *(slot.get("movement_patterns") or []),
            *(item.get("movement_patterns") or []),
            slot.get("movement"),
            item.get("movement"),
        ]
        if str(value).strip()
    }
    return bool(
        tags
        & {
            "core",
            "core_stability",
            "core_strength",
            "trunk",
            "trunk_strength",
            "anti_rotation",
            "balance",
            "stability",
            "proprioception",
        }
    )


def _slot_priority(slot: dict[str, Any], original_index: int) -> tuple[int, int]:
    try:
        priority = int(slot.get("priority"))
    except (TypeError, ValueError):
        priority = 10_000
    return priority, original_index


def _slot_mechanical_risk_tags(slot: dict[str, Any]) -> set[str]:
    item = _slot_selected_item(slot)
    metadata = item.get("selection_metadata")
    nested_tags = (
        metadata.get("mechanical_risk_tags", [])
        if isinstance(metadata, dict)
        else []
    )
    return {
        str(value).strip().lower()
        for value in [
            *(slot.get("mechanical_risk_tags") or []),
            *(item.get("mechanical_risk_tags") or []),
            *nested_tags,
        ]
        if str(value).strip().lower().startswith("mech_")
    }


def _candidate_records(slots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for index, slot in enumerate(slots):
        assignment = assignment_from_slot("", "strength_slots", slot)
        if not assignment:
            continue
        families, profile = _composition_families(slot)
        serialized_quality_class = _serialized_quality_class(slot)
        serialized_support_only = serialized_quality_class in {"support_accessory", "support_isometric", "rehab_support"}
        has_major_family = bool(families - {"support"})
        support_only = bool(serialized_support_only or (profile.get("support_only") and not has_major_family))
        records.append(
            {
                "slot": slot,
                "name": assignment["name"],
                "families": families,
                "support_only": support_only,
                "core_balance_support": bool(
                    profile.get("core_balance_support")
                    or (serialized_support_only and _slot_has_core_balance_signal(slot))
                ),
                "loaded_pattern": bool(profile.get("loaded_pattern") and (not serialized_support_only or _slot_uses_loaded_equipment(slot))),
                "force_isometric": bool(profile.get("force_isometric")),
                "power_pattern": bool(profile.get("power_pattern")),
                "quality_class": serialized_quality_class or str(profile.get("quality_class") or ""),
                "mechanical_risk_tags": _slot_mechanical_risk_tags(slot),
                "verified_low_recovery_cost": has_verified_low_cost(
                    slot,
                    fields=_ADJACENT_STRENGTH_RECOVERY_COST_FIELDS,
                ),
                "material_movement_cost": not has_verified_low_cost(
                    slot,
                    fields=("movement_cost",),
                ),
                "sort_key": _slot_priority(slot, index),
                "original_index": index,
            }
        )
    return sorted(records, key=lambda item: item["sort_key"])


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
    preserve_trunk_support: bool = False,
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    family_limit = 2 if pressure == 0 else 1
    selected: list[dict[str, Any]] = []
    family_counts: dict[str, int] = {}
    dropped: dict[str, str] = {}

    unsatisfied_groups = list(_ROLE_REQUIRED_FAMILY_GROUPS.get(role_key, ()))
    while unsatisfied_groups:
        if len(selected) >= cap:
            break
        eligible = [
            record
            for record in records
            if record not in selected
            and any(record["families"] & group for group in unsatisfied_groups)
            and not _would_exceed_family_limit(
                record["families"], family_counts, family_limit
            )
        ]
        if not eligible:
            break
        record = max(
            eligible,
            key=lambda item: sum(
                bool(item["families"] & group) for group in unsatisfied_groups
            ),
        )
        _add_record(record, selected, family_counts)
        unsatisfied_groups = [
            group for group in unsatisfied_groups if not (record["families"] & group)
        ]

    # An explicitly selected trunk-strength limiter belongs inside the retained
    # maintenance session when the conditioning priority shift leaves only one
    # strength slot. Keep it inside the existing cap and bank membership.
    if preserve_trunk_support and len(selected) < cap:
        trunk_options = [
            record
            for record in records
            if record not in selected
            and record.get("core_balance_support")
            and not _would_exceed_family_limit(
                record["families"], family_counts, family_limit
            )
        ]
        if trunk_options:
            _add_record(trunk_options[0], selected, family_counts)

    # Preserve Stage 1 ranking as the authority. Support/accessory status is only
    # a drop preference when the session actually has to shrink; it is never a
    # global pre-selection ranking penalty.
    fill_records = records
    if len(records) > cap:
        fill_records = sorted(
            records,
            key=lambda item: (
                1 if item["support_only"] else 0,
                item["sort_key"][0],
                item["sort_key"][1],
            ),
        )

    for record in fill_records:
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

    selected.sort(key=lambda item: item["sort_key"])
    return selected, dropped


def _pressure_context_from_map(weekly_role_map: dict[str, Any]) -> dict[str, Any] | None:
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


def _trunk_strength_selected(athlete_model: dict[str, Any] | None) -> bool:
    model = athlete_model if isinstance(athlete_model, dict) else {}
    values = [
        *(model.get("key_goals") or []),
        *(model.get("goals") or []),
        *(model.get("weaknesses") or []),
        *(model.get("weak_areas") or []),
    ]
    return any(
        re.sub(r"[^a-z0-9]+", "_", str(value).strip().lower()).strip("_")
        == "trunk_strength"
        for value in values
    )


def _low_load_trunk_support_records(slots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records = []
    for record in _candidate_records(slots):
        if (
            record.get("support_only")
            and record.get("core_balance_support")
            and not record.get("loaded_pattern")
            and not record.get("force_isometric")
            and not record.get("power_pattern")
            and record.get("quality_class") in {"support_accessory", "support_isometric"}
        ):
            records.append(record)
    return records


def _role_days_until_fight(role: dict[str, Any]) -> int | None:
    for key in ("countdown_offset", "scheduled_countdown_offset"):
        value = _int_or_none(role.get(key))
        if value is not None:
            return max(0, value)

    for key in ("scheduled_countdown_label", "countdown_label"):
        label = str(role.get(key) or "").strip().upper()
        if not label.startswith("D-"):
            continue
        value = _int_or_none(label[2:])
        if value is not None:
            return max(0, value)
    return None


def _role_pressure_state(
    context: dict[str, Any], *, role: dict[str, Any], fatigue_applied: bool
) -> dict[str, Any]:
    fatigue = str(context.get("fatigue") or "low").strip().lower() if fatigue_applied else "low"
    if fatigue not in _FATIGUE_PRESSURE:
        fatigue = "low"

    active_cut = bool(context.get("active_weight_cut"))
    cut_bucket = str(context.get("cut_severity_bucket") or "none").strip().lower()
    role_d_day = _role_days_until_fight(role)
    cut_pct = _float_or_none(context.get("weight_cut_pct"))
    if active_cut and cut_pct is not None and cut_pct > 0.0 and role_d_day is not None:
        cut_bucket = cut_severity_bucket(compute_cut_severity_score(cut_pct, role_d_day))
    elif not active_cut:
        cut_bucket = "none"

    state = _pressure_state_from_components(
        fatigue=fatigue,
        cut_bucket=cut_bucket,
        injury_restricted=bool(context.get("injury_restricted")),
    )
    state["fatigue_applied"] = fatigue_applied
    state["role_days_until_fight"] = role_d_day
    return state


def _substantial_mechanical_tags(records: list[dict[str, Any]]) -> set[str]:
    if not records:
        return set()
    return set().union(
        *[
            record["mechanical_risk_tags"]
            for record in records
            if record["material_movement_cost"]
        ]
    )


def _all_mechanical_tags(records: list[dict[str, Any]]) -> set[str]:
    return (
        set().union(*(record["mechanical_risk_tags"] for record in records))
        if records
        else set()
    )


def _assign_selected_records(
    entry: dict[str, Any], selected_records: list[dict[str, Any]]
) -> None:
    assignments = []
    for record in selected_records:
        assignment = assignment_from_slot(
            entry["phase"], "strength_slots", record["slot"]
        )
        if assignment:
            assignments.append(assignment)
    entry["role"]["selected_exercise_assignments"] = assignments
    policy = entry["role"]["strength_composition_policy"]
    policy["selected_count"] = len(assignments)
    policy["selected_names"] = [item["name"] for item in assignments]
    entry["selected_records"] = selected_records


def _apply_adjacent_strength_recovery(
    weekly_role_map: dict[str, Any], entries: list[dict[str, Any]]
) -> None:
    scheduled = [
        entry
        for entry in entries
        if role_d_day(entry["week"], entry["role"]) is not None
        and entry["role"] in (entry["week"].get("session_roles") or [])
    ]
    scheduled.sort(
        key=lambda entry: role_d_day(entry["week"], entry["role"]),
        reverse=True,
    )

    for index, current in enumerate(scheduled):
        current_d_day = role_d_day(current["week"], current["role"])
        if current_d_day is None:
            continue
        previous = [
            entry
            for entry in scheduled[:index]
            if role_d_day(entry["week"], entry["role"]) == current_d_day + 1
            and entry["role"] in (entry["week"].get("session_roles") or [])
        ]
        if not previous:
            continue

        previous_records = [
            record for entry in previous for record in entry["selected_records"]
        ]
        previous_substantial_tags = _substantial_mechanical_tags(previous_records)
        shared_tags = _all_mechanical_tags(previous_records) & _all_mechanical_tags(
            current["selected_records"]
        )
        conflicting_tags = previous_substantial_tags & _substantial_mechanical_tags(
            current["selected_records"]
        )
        evidence = {
            "consecutive": True,
            "previous_d_day": current_d_day + 1,
            "current_d_day": current_d_day,
            "shared_mechanical_tags": sorted(shared_tags),
            "substantial_overlap_tags": sorted(conflicting_tags),
            "previous_material_items": [
                record["name"]
                for record in previous_records
                if record["material_movement_cost"]
            ],
            "current_material_items": [
                record["name"]
                for record in current["selected_records"]
                if record["material_movement_cost"]
            ],
            "current_verified_low_cost_items": [
                record["name"]
                for record in current["selected_records"]
                if record["verified_low_recovery_cost"]
            ],
        }

        if not conflicting_tags:
            evidence["decision"] = "compatible"
            current["role"]["strength_composition_policy"][
                "adjacent_strength_recovery"
            ] = evidence
            continue

        safe_records = [
            record
            for record in current["records"]
            if not record["material_movement_cost"]
            or not (record["mechanical_risk_tags"] & previous_substantial_tags)
        ]
        selected_records, dropped = _select_bounded_records(
            safe_records,
            role_key=current["role_key"],
            cap=current["effective_cap"],
            pressure=current["pressure"],
            preserve_trunk_support=current["preserve_trunk_support"],
        )
        if selected_records:
            _assign_selected_records(current, selected_records)
            policy = current["role"]["strength_composition_policy"]
            existing_dropped = {
                str(item.get("name") or ""): str(item.get("reason") or "")
                for item in policy.get("dropped") or []
                if isinstance(item, dict) and str(item.get("name") or "")
            }
            existing_dropped.update(dropped)
            for record in current["records"]:
                if record not in safe_records:
                    existing_dropped[record["name"]] = _ADJACENT_STRENGTH_RECOVERY_REASON
            policy["dropped"] = [
                {"name": name, "reason": reason}
                for name, reason in existing_dropped.items()
            ]
            evidence["decision"] = "selection_modified"
            policy["adjacent_strength_recovery"] = evidence
            continue

        current_substantial_tags = _substantial_mechanical_tags(current["selected_records"])
        excluded_d_days: set[int] = set()
        for other in scheduled:
            if other is current:
                continue
            other_d_day = role_d_day(other["week"], other["role"])
            if other_d_day is None:
                continue
            if current_substantial_tags & _substantial_mechanical_tags(other["selected_records"]):
                excluded_d_days.update({other_d_day - 1, other_d_day, other_d_day + 1})

        action = relocate_or_suppress_role_for_recovery(
            weekly_role_map,
            current["role"],
            excluded_d_days=excluded_d_days,
            reason_code=_ADJACENT_STRENGTH_RECOVERY_REASON,
        )
        evidence["decision"] = (
            str(action.get("action")) if isinstance(action, dict) else "unchanged"
        )
        if isinstance(action, dict) and action.get("to_d_day") is not None:
            evidence["relocated_to_d_day"] = action["to_d_day"]
        current["role"]["strength_composition_policy"][
            "adjacent_strength_recovery"
        ] = evidence


def compose_normal_strength_assignments(
    *, weekly_role_map: dict[str, Any], candidate_pools: dict[str, Any]
) -> dict[str, Any]:
    """Carry bounded Stage 1 strength composition onto normal planner roles.

    Closed membership remains Stage 1 authority. This function never chooses an
    alternate and never invents an exercise. It only prunes already-selected
    slots using role ceilings, athlete recovery pressure, and existing movement
    tags. Late-fight-owned roles are excluded and keep their dedicated selector.

    Current fatigue is applied only to the first camp week containing a normal
    strength role handled here. Persistent injury state remains active, while
    weight-cut severity is recalculated from each role's D-day when the cut
    percentage is available.
    """
    athlete_model = get_planner_athlete_model()
    pressure_context = (
        _composition_context_from_model(athlete_model)
        if athlete_model is not None
        else _pressure_context_from_map(weekly_role_map)
    )
    if pressure_context is None:
        pressure_context = _composition_context_from_model(None)
    trunk_strength_selected = _trunk_strength_selected(athlete_model)

    weekly_role_map["strength_composition_context"] = dict(pressure_context)
    composed_roles: list[dict[str, Any]] = []

    first_strength_week_position = next(
        (
            position
            for position, week in enumerate(weekly_role_map.get("weeks", []) or [])
            if isinstance(week, dict)
            and any(
                isinstance(role, dict)
                and not role.get("late_fight_tail_owned")
                and (
                    str(role.get("category") or "").lower() == "strength"
                    or str(role.get("preferred_pool") or "").lower() == "strength_slots"
                )
                for role in (week.get("session_roles", []) or [])
            )
        ),
        None,
    )

    for week_position, week in enumerate(weekly_role_map.get("weeks", []) or []):
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

            pressure_state = _role_pressure_state(
                pressure_context,
                role=role,
                fatigue_applied=week_position == first_strength_week_position,
            )
            pressure = int(pressure_state["pressure"])

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
                preserve_trunk_support=trunk_strength_selected,
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
                "major_family_limit": 2 if pressure == 0 else 1,
                "selected_count": len(assignments),
                "selected_names": [item["name"] for item in assignments],
                "dropped": [
                    {"name": name, "reason": reason}
                    for name, reason in dropped.items()
                ],
            }
            composed_roles.append(
                {
                    "week": week,
                    "role": role,
                    "phase": phase,
                    "records": records,
                    "selected_records": selected_records,
                    "role_key": role_key,
                    "effective_cap": effective_cap,
                    "pressure": pressure,
                    "preserve_trunk_support": trunk_strength_selected,
                }
            )
    _apply_adjacent_strength_recovery(weekly_role_map, composed_roles)
    return weekly_role_map


def _conditioning_duration_minutes(option: dict[str, Any]) -> float | None:
    return conditioning_dose_minutes(_conditioning_effective_dose(option))


def _conditioning_is_high_load(option: dict[str, Any]) -> bool:
    metadata = option.get("selection_metadata") if isinstance(option.get("selection_metadata"), dict) else {}
    rpe = _float_or_none(metadata.get("rpe"))
    load_tokens = " ".join(
        str(metadata.get(key) or "").strip().lower()
        for key in ("load", "intensity", "lactate_load", "movement_cost")
    )
    return bool((rpe is not None and rpe >= 8) or re.search(r"\b(?:high|max|maximal|all[- ]out)\b", load_tokens))


def _conditioning_rounds(option: dict[str, Any]) -> int | None:
    metadata = option.get("selection_metadata") if isinstance(option.get("selection_metadata"), dict) else {}
    rounds = _float_or_none(metadata.get("rounds"))
    if rounds is None or rounds <= 0 or not rounds.is_integer():
        return None
    return int(rounds)


def _conditioning_effective_dose(option: dict[str, Any]) -> dict[str, Any]:
    """Bank dose for this option, resolved to the athlete's own round length."""
    metadata = option.get("selection_metadata") if isinstance(option.get("selection_metadata"), dict) else {}
    athlete_model = get_planner_athlete_model() or {}
    return conditioning_effective_dose(
        metadata, athlete_round_seconds(athlete_model.get("rounds_format"))
    )


def _conditioning_active_work_seconds(option: dict[str, Any]) -> float | None:
    return conditioning_dose_active_work_seconds(_conditioning_effective_dose(option))


def _conditioning_round_seconds(option: dict[str, Any]) -> float | None:
    """Round duration for a round-based option, owned by the athlete's format.

    Only an option the bank marks ``round_based`` is a fight round, so only
    those re-anchor to the athlete's own "Rounds x Minutes" intake. Every other
    dose — machine threshold blocks, EMOMs, carries, short interval drills —
    keeps the work interval the bank authored. Round count, rest, RPE, exercise
    identity, scoring and mechanical metadata are untouched either way.
    """
    metadata = option.get("selection_metadata") if isinstance(option.get("selection_metadata"), dict) else {}
    if not metadata.get("round_based"):
        return None
    athlete_model = get_planner_athlete_model() or {}
    return athlete_round_seconds(athlete_model.get("rounds_format"))


def _conditioning_prescription(option: dict[str, Any], *, rounds: int | None = None) -> str:
    metadata = option.get("selection_metadata") if isinstance(option.get("selection_metadata"), dict) else {}
    athlete_round_sec = _conditioning_round_seconds(option)
    # A round-based option states its work interval in fight rounds, so it
    # renders at the athlete's own round length even when nothing repartitioned
    # it. The bank keeps the round count, rest and RPE.
    effective_rounds = rounds if rounds is not None else (
        _conditioning_rounds(option) if athlete_round_sec else None
    )
    if effective_rounds is not None:
        rendered = conditioning_round_prescription(
            effective_rounds,
            athlete_round_sec,
            work_sec=_float_or_none(metadata.get("work_sec")),
            rest_sec=_float_or_none(metadata.get("rest_sec")),
            rpe=_float_or_none(metadata.get("rpe")),
        )
        if rendered:
            return rendered
    base = str(option.get("prescription") or metadata.get("timing") or metadata.get("duration") or "").strip()
    if base:
        return base
    total_minutes = _float_or_none(metadata.get("total_minutes"))
    return f"{total_minutes:g} min" if total_minutes is not None and total_minutes > 0 else ""


def _conditioning_partition_high_load(
    selected: list[tuple[dict[str, Any], dict[str, Any], bool]],
    *,
    phase: str,
    system: str,
) -> tuple[
    list[tuple[dict[str, Any], dict[str, Any], bool]],
    dict[str, int],
    str | None,
    dict[str, float | None],
]:
    """Partition one phase-appropriate workload across known high-load drills."""
    high_load = []
    for item in selected:
        if not _conditioning_is_high_load(item[1]):
            continue
        metadata = item[1].get("selection_metadata") if isinstance(item[1].get("selection_metadata"), dict) else {}
        dose_text = str(metadata.get("duration") or metadata.get("timing") or "").lower()
        if not re.search(r"\b(?:reps?|per[-\s]?side|/side|yds?|yards?|meters?|feet|ft|m)\b", dose_text):
            high_load.append(item)
    if len(high_load) < 2:
        return selected, {}, None, {}

    dose_data: list[tuple[tuple[dict[str, Any], dict[str, Any], bool], float, float, int]] = []
    for item in high_load:
        metadata = _conditioning_effective_dose(item[1])
        work_sec = _float_or_none(metadata.get("work_sec"))
        rest_sec = _float_or_none(metadata.get("rest_sec"))
        rounds = _conditioning_rounds(item[1])
        if (
            work_sec is None
            or work_sec <= 0
            or rest_sec is None
            or rest_sec < 0
            or rounds is None
        ):
            retained = [candidate for candidate in selected if candidate not in high_load]
            return retained, {}, "high_load_dose_unknown", {}
        dose_data.append((item, work_sec, rest_sec, rounds))

    target_active_work, elapsed_cap_minutes = _conditioning_phase_workload_envelope(
        phase=phase, system=system
    )
    if target_active_work is None or elapsed_cap_minutes is None:
        return selected, {}, None, {}

    elapsed_cap_seconds = elapsed_cap_minutes * 60.0
    minimum_required = sum(work_sec for _, work_sec, _, _ in dose_data)
    minimum_elapsed = sum(work_sec for _, work_sec, _, _ in dose_data)
    if minimum_required > target_active_work or minimum_elapsed > elapsed_cap_seconds:
        retained = [candidate for candidate in selected if candidate not in high_load]
        return retained, {}, "high_load_dose_underfilled", {
            "target_active_work_seconds": target_active_work,
            "elapsed_cap_seconds": elapsed_cap_seconds,
        }

    allocated = {str(item[1].get("name") or ""): 1 for item, _, _, _ in dose_data}
    active_work = minimum_required
    elapsed_work = minimum_elapsed
    while True:
        progressed = False
        for item, work_sec, rest_sec, max_rounds in dose_data:
            name = str(item[1].get("name") or "")
            additional_elapsed = work_sec + rest_sec
            if (
                allocated[name] >= max_rounds
                or active_work + work_sec > target_active_work
                or elapsed_work + additional_elapsed > elapsed_cap_seconds
            ):
                continue
            allocated[name] += 1
            active_work += work_sec
            elapsed_work += additional_elapsed
            progressed = True
        if not progressed:
            break
    underfill_reason = None if active_work >= target_active_work else "phase_system_dose_capacity_limited"
    return selected, allocated, underfill_reason, {
        "target_active_work_seconds": target_active_work,
        "allocated_active_work_seconds": active_work,
        "elapsed_cap_seconds": elapsed_cap_seconds,
        "allocated_elapsed_seconds": elapsed_work,
    }


def _conditioning_phase_for_role(week: dict[str, Any], role: dict[str, Any]) -> str:
    athlete_model = get_planner_athlete_model() or {}
    return scheduled_phase_for_role(
        role,
        athlete_model=athlete_model,
        spec_phase=week.get("phase"),
    ) or str(week.get("phase") or "").strip().upper()


def _conditioning_role_is_hard_spar_adjacent(week: dict[str, Any], role: dict[str, Any]) -> bool:
    weekday_order = {
        "monday": 0,
        "tuesday": 1,
        "wednesday": 2,
        "thursday": 3,
        "friday": 4,
        "saturday": 5,
        "sunday": 6,
    }
    scheduled_day = str(role.get("scheduled_day_hint") or "").strip().lower()
    scheduled_index = weekday_order.get(scheduled_day)
    if scheduled_index is None:
        return False

    hard_days = {
        str(day).strip().lower()
        for day in (week.get("effective_hard_sparring_days") or [])
        if str(day).strip()
    }
    if not hard_days:
        hard_days = {
            str(entry.get("day") or "").strip().lower()
            for entry in (week.get("hard_sparring_plan") or [])
            if isinstance(entry, dict) and entry.get("status") == "hard_as_planned"
        }
    return any(
        ((weekday_order[hard_day] - scheduled_index) % 7) in {1, 6}
        for hard_day in hard_days
        if hard_day in weekday_order
    )


def compose_normal_conditioning_assignments(
    *, weekly_role_map: dict[str, Any], candidate_pools: dict[str, Any]
) -> dict[str, Any]:
    """Attach a safe bank-backed minimum composition to normal conditioning roles."""
    athlete_model = get_planner_athlete_model()
    pressure_context = _composition_context_from_model(athlete_model)
    trunk_strength_selected = _trunk_strength_selected(athlete_model)

    for week in weekly_role_map.get("weeks", []) or []:
        if not isinstance(week, dict):
            continue
        embedded_trunk_support_count = 0
        for role in week.get("session_roles", []) or []:
            if (
                not isinstance(role, dict)
                or role.get("late_fight_tail_owned")
                or str(role.get("category") or "").strip().lower() != "conditioning"
            ):
                continue

            phase = _conditioning_phase_for_role(week, role)
            pool = candidate_pools.get(phase) if isinstance(candidate_pools, dict) else None
            slots = pool.get("conditioning_slots", []) if isinstance(pool, dict) else []
            strength_slots = pool.get("strength_slots", []) if isinstance(pool, dict) else []

            preferred_system = str(role.get("preferred_system") or "").strip().lower()
            matching_slots = [
                slot
                for slot in slots
                if isinstance(slot, dict)
                and str(slot.get("role") or "").strip().lower() == preferred_system
            ]
            # Membership is one member per Stage 1 slot. A slot's ``alternates``
            # are its same-role substitution reservoir, not additional session
            # members: drawing from them turns one selected drill plus its two
            # backups into a fake three-exercise circuit.
            options: list[tuple[dict[str, Any], dict[str, Any], bool]] = []
            seen_names: set[str] = set()
            for slot in matching_slots:
                option = slot.get("selected")
                if not isinstance(option, dict):
                    continue
                name = str(option.get("name") or "").strip()
                if not name or name in seen_names:
                    continue
                seen_names.add(name)
                options.append((slot, option, True))

            if not options:
                continue

            adjacent_hard_spar = _conditioning_role_is_hard_spar_adjacent(week, role)
            # Resolve the phase/system workload first: a session is complete
            # when it carries that workload, not when it reaches three members.
            target_active_work, _ = _conditioning_phase_workload_envelope(
                phase=phase, system=preferred_system
            )
            selected: list[tuple[dict[str, Any], dict[str, Any], bool]] = []
            total_minutes = 0.0
            active_work_seconds = 0.0
            for slot, option, is_selected in options:
                duration = _conditioning_duration_minutes(option)
                if selected:
                    if duration is not None and total_minutes + duration > 45:
                        continue
                selected.append((slot, option, is_selected))
                if duration is not None:
                    total_minutes += duration
                active_work = _conditioning_active_work_seconds(option)
                if active_work is not None:
                    active_work_seconds += active_work
                if adjacent_hard_spar:
                    break
                if preferred_system == "aerobic" and len(selected) >= 2 and total_minutes >= 25:
                    break
                if target_active_work is not None and active_work_seconds >= target_active_work:
                    break
                if len(selected) >= 3:
                    break

            # Count the members that delivered the workload before the
            # partitioner may drop undoseable high-load drills, so a dropped
            # session still reports as underfilled.
            composed_count = len(selected)
            selected, high_load_rounds, underfill_reason, high_load_budget = _conditioning_partition_high_load(
                selected,
                phase=phase,
                system=preferred_system,
            )
            long_aerobic = preferred_system == "aerobic" and total_minutes >= 25
            # A session that already carries its phase/system workload is
            # complete at whatever member count delivered it; the count floor
            # only applies while the workload is still unmet or unknown.
            workload_met = (
                target_active_work is not None and active_work_seconds >= target_active_work
            )
            if adjacent_hard_spar:
                minimum = None
            elif workload_met:
                minimum = composed_count
            else:
                minimum = 2 if long_aerobic else 3

            assignments = []
            selected_names: set[str] = set()
            for slot, option, is_selected in selected:
                name = str(option.get("name") or "")
                if name:
                    selected_names.add(name)
                allocated_rounds = high_load_rounds.get(name)
                assignment = {
                    "slot_id": slot.get("slot_id"),
                    "name": name,
                    "source_phase": phase,
                    "slot_group": "conditioning_slots",
                    "selected_option": is_selected,
                    "base_prescription": _conditioning_prescription(option),
                    "effective_prescription": _conditioning_prescription(option, rounds=allocated_rounds),
                    "effective_rounds": allocated_rounds,
                }
                notes = _selected_coaching_notes(option)
                if notes:
                    assignment["coaching_notes"] = notes
                assignments.append(assignment)

            trunk_support_added = False
            trunk_support_skip_reason = ""
            pressure_state = _role_pressure_state(
                pressure_context,
                role=role,
                fatigue_applied=True,
            )
            if trunk_strength_selected and not adjacent_hard_spar and int(pressure_state["pressure"]) < 2:
                trunk_options = [
                    record
                    for record in _low_load_trunk_support_records(strength_slots)
                    if record["name"] not in selected_names
                ]
                if embedded_trunk_support_count >= 2:
                    trunk_support_skip_reason = "weekly_trunk_support_cap"
                elif trunk_options:
                    record = trunk_options[0]
                    assignment = assignment_from_slot(phase, "strength_slots", record["slot"])
                    if assignment:
                        assignment.update(
                            {
                                "embedded_support": True,
                                "support_dose_category": "low_load_trunk",
                                "effective_prescription": "1-2 controlled sets; stop before fatigue",
                            }
                        )
                        assignments.append(assignment)
                        selected_names.add(record["name"])
                        embedded_trunk_support_count += 1
                        trunk_support_added = True
            elif trunk_strength_selected:
                trunk_support_skip_reason = (
                    "hard_sparring_adjacent"
                    if adjacent_hard_spar
                    else "readiness_pressure"
                )

            role["selected_exercise_assignments"] = assignments
            role["conditioning_composition_policy"] = {
                "minimum_exercise_count": minimum,
                "selected_count": len(assignments),
                "long_aerobic_session": long_aerobic,
                "hard_sparring_adjacent": adjacent_hard_spar,
                "high_load_workload_envelope": high_load_budget,
                "partitioned_high_load_rounds": high_load_rounds,
                "underfill_reason": underfill_reason,
                "workload_limited": bool(minimum is not None and len(assignments) < minimum),
                "embedded_trunk_support": trunk_support_added,
                "embedded_trunk_support_count": 1 if trunk_support_added else 0,
                "embedded_trunk_support_skip_reason": trunk_support_skip_reason,
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
