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
from .strength_session_quality import classify_strength_item
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
                "core_balance_support": bool(profile.get("core_balance_support")),
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
    return weekly_role_map


def _conditioning_duration_minutes(option: dict[str, Any]) -> float | None:
    metadata = option.get("selection_metadata") if isinstance(option.get("selection_metadata"), dict) else {}
    for key in ("total_minutes", "duration_min"):
        value = metadata.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return max(0.0, float(value))

    text = str(metadata.get("duration") or metadata.get("timing") or "").lower()
    match = re.search(r"(\d+(?:\.\d+)?)\s*(?:[-–]\s*\d+(?:\.\d+)?)?\s*min", text)
    return float(match.group(1)) if match else None


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


def _conditioning_prescription(option: dict[str, Any], *, rounds: int | None = None) -> str:
    metadata = option.get("selection_metadata") if isinstance(option.get("selection_metadata"), dict) else {}
    if rounds is not None:
        work_sec = _float_or_none(metadata.get("work_sec"))
        if work_sec is not None and work_sec > 0:
            work_text = f"{work_sec:g} sec work"
            parts = [f"{rounds} x {work_text}"]
            rest_sec = _float_or_none(metadata.get("rest_sec"))
            if rest_sec is not None and rest_sec > 0:
                parts.append(f"{rest_sec:g} sec rest")
            rpe = _float_or_none(metadata.get("rpe"))
            if rpe is not None:
                parts.append(f"RPE {rpe:g}")
            return "; ".join(parts)
    base = str(option.get("prescription") or metadata.get("timing") or metadata.get("duration") or "").strip()
    if base:
        return base
    total_minutes = _float_or_none(metadata.get("total_minutes"))
    return f"{total_minutes:g} min" if total_minutes is not None and total_minutes > 0 else ""


def _conditioning_phase_workload_envelope(
    *, phase: str, system: str
) -> tuple[float | None, float | None]:
    """Use the existing rendered phase dose guidance as the composition envelope.

    These are not new global targets: they are the lower active-work edge and
    elapsed cap already stated by ``render_conditioning_block`` for GPP/SPP.
    A bank prescription, injury/recovery filtering, and role-level safety
    remain authoritative; this only prevents a short first drill from defining
    the whole multi-movement session.
    """
    phase = str(phase or "").upper()
    if system == "glycolytic" and phase == "GPP":
        # Existing GPP combat-pressure floor: 6-8 x 60 sec hard.
        return 6 * 60.0, 30.0
    if phase == "GPP":
        # 3 x 3 min is the low edge of the existing GPP 3-5 x 3-5 min template.
        return 9 * 60.0, 30.0
    if phase == "SPP":
        # 4 x 2 min is the low edge of the existing SPP 4-6 x 2-5 min template.
        return 8 * 60.0, 25.0
    return None, None


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
        metadata = item[1].get("selection_metadata") if isinstance(item[1].get("selection_metadata"), dict) else {}
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
    for week in weekly_role_map.get("weeks", []) or []:
        if not isinstance(week, dict):
            continue
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

            preferred_system = str(role.get("preferred_system") or "").strip().lower()
            matching_slots = [
                slot
                for slot in slots
                if isinstance(slot, dict)
                and str(slot.get("role") or "").strip().lower() == preferred_system
            ]
            options: list[tuple[dict[str, Any], dict[str, Any], bool]] = []
            seen_names: set[str] = set()
            for is_selected in (True, False):
                for slot in matching_slots:
                    candidates = (
                        [slot.get("selected")]
                        if is_selected
                        else list(slot.get("alternates") or [])
                    )
                    for option in candidates:
                        if not isinstance(option, dict):
                            continue
                        name = str(option.get("name") or "").strip()
                        if not name or name in seen_names:
                            continue
                        seen_names.add(name)
                        options.append((slot, option, is_selected))

            if not options:
                continue

            adjacent_hard_spar = _conditioning_role_is_hard_spar_adjacent(week, role)
            selected: list[tuple[dict[str, Any], dict[str, Any], bool]] = []
            total_minutes = 0.0
            for slot, option, is_selected in options:
                duration = _conditioning_duration_minutes(option)
                if selected:
                    if duration is not None and total_minutes + duration > 45:
                        continue
                selected.append((slot, option, is_selected))
                if duration is not None:
                    total_minutes += duration
                if adjacent_hard_spar:
                    break
                if preferred_system == "aerobic" and len(selected) >= 2 and total_minutes >= 25:
                    break
                if len(selected) >= 3:
                    break

            selected, high_load_rounds, underfill_reason, high_load_budget = _conditioning_partition_high_load(
                selected,
                phase=phase,
                system=preferred_system,
            )
            long_aerobic = preferred_system == "aerobic" and total_minutes >= 25
            minimum = None if adjacent_hard_spar else (2 if long_aerobic else 3)

            assignments = []
            for slot, option, is_selected in selected:
                name = str(option.get("name") or "")
                allocated_rounds = high_load_rounds.get(name)
                assignments.append(
                    {
                        "slot_id": slot.get("slot_id"),
                        "name": name,
                        "source_phase": phase,
                        "slot_group": "conditioning_slots",
                        "selected_option": is_selected,
                        "base_prescription": _conditioning_prescription(option),
                        "effective_prescription": _conditioning_prescription(option, rounds=allocated_rounds),
                        "effective_rounds": allocated_rounds,
                    }
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
