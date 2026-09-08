"""Source-backed dose and coaching context for closed Stage 2 assignments.

This projection never selects exercises. It joins the already-selected member to
its exact bank option, retains the scheduled effective dose, and exposes only
that member's useful coaching evidence. Missing dose authority is an error,
not permission for the finalizer to invent a workout.
"""
from __future__ import annotations

from copy import deepcopy
import re
from typing import Any

from .prescription_resolver import (
    athlete_dose_state,
    resolve_strength_slot_prescription,
)


class MissingSelectedPrescriptionError(ValueError):
    code = "missing_selected_prescription"

    def __init__(self, details: dict[str, Any]):
        self.details = details
        super().__init__(f"{self.code}: {details}")


def _text(value: Any) -> str:
    return str(value).strip() if isinstance(value, (str, int, float)) and not isinstance(value, bool) else ""


def _dose(value: Any) -> str:
    if isinstance(value, dict):
        value = value.get("display") or value.get("dose") or value.get("text")
    return _text(value)


def _quantitative(value: Any) -> str:
    text = _dose(value)
    if not text or text.lower() in {"strength", "power", "conditioning", "tbd", "n/a", "none", "null"}:
        return ""
    return text if re.search(r"\d", text) else ""


def _source_index(pools: dict[str, Any]) -> dict[tuple[str, str, str, str], list[tuple[dict, dict]]]:
    index: dict[tuple[str, str, str, str], list[tuple[dict, dict]]] = {}
    for phase, pool in pools.items():
        if not isinstance(pool, dict):
            continue
        for group in ("strength_slots", "conditioning_slots", "late_tail_candidates"):
            for slot in pool.get(group) or []:
                if not isinstance(slot, dict):
                    continue
                slot_id = _text(slot.get("slot_id"))
                for option in [slot.get("selected"), *(slot.get("alternates") or [])]:
                    if not isinstance(option, dict):
                        continue
                    name = _text(option.get("name"))
                    if name:
                        key = (str(phase).upper(), group, slot_id, name)
                        index.setdefault(key, []).append((slot, option))
    return index


def _source_for(index: dict, assignment: dict) -> tuple[dict, dict] | None:
    phase = _text(assignment.get("source_phase") or assignment.get("phase")).upper()
    group = _text(assignment.get("slot_group"))
    slot_id = _text(assignment.get("slot_id"))
    name = _text(assignment.get("name"))
    if not phase or not name:
        return None
    groups = (group,) if group else ("strength_slots", "conditioning_slots", "late_tail_candidates")
    matches: list[tuple[dict, dict]] = []
    for candidate_group in groups:
        matches.extend(index.get((phase, candidate_group, slot_id, name), []))
    # Older late-tail assignments sometimes use a different slot identifier.
    # A unique exact phase/name match is safe for provenance, never for selection.
    if not matches and not slot_id:
        matches = [item for key, values in index.items()
                   if key[0] == phase and key[3] == name and key[1] in groups
                   for item in values]
    # Multiple distinct sources are ambiguous. Do not guess from a display name.
    unique = {(id(slot), id(option)): (slot, option) for slot, option in matches}
    return next(iter(unique.values())) if len(unique) == 1 else None


def _coaching_context(option: dict) -> dict[str, Any]:
    metadata = option.get("selection_metadata") if isinstance(option.get("selection_metadata"), dict) else {}
    def get(key: str) -> Any:
        return option.get(key) if option.get(key) not in (None, "", []) else metadata.get(key)

    context: dict[str, Any] = {}
    for key in ("notes", "cue", "cue_execution", "side_instruction", "quality_stop_rule",
                "purpose", "description", "load", "rest", "timing"):
        value = get(key)
        if isinstance(value, str) and value.strip():
            context[key] = value.strip()
        elif isinstance(value, list):
            cleaned = [_text(item) for item in value if _text(item)]
            if cleaned:
                context[key] = cleaned
    technical = option.get("technical_footwork_prescription")
    if isinstance(technical, dict):
        for key in ("cue", "cue_execution", "side_instruction", "quality_stop_rule"):
            value = technical.get(key)
            if _text(value):
                context[key] = _text(value)
    return context


def _authoritative_tail_dose(brief: dict, role: dict, assignment: dict) -> str:
    spec = brief.get("late_fight_plan_spec") or {}
    by_day = spec.get("allowed_exercise_assignments_by_day") or {}
    if not isinstance(by_day, dict):
        return ""
    label = _text(role.get("scheduled_countdown_label") or role.get("countdown_label"))
    name = _text(assignment.get("name"))
    slot_id = _text(assignment.get("slot_id"))
    for candidate in by_day.get(label) or []:
        if not isinstance(candidate, dict) or _text(candidate.get("name")) != name:
            continue
        if slot_id and _text(candidate.get("slot_id")) not in ("", slot_id):
            continue
        if _text(candidate.get("role_key")) not in ("", _text(role.get("role_key"))):
            continue
        dose = _dose(candidate.get("effective_prescription"))
        if dose:
            return dose
    return ""


def _visible_roles(brief: dict):
    sequence = brief.get("late_fight_session_sequence")
    if isinstance(sequence, list):
        for role in sequence:
            if isinstance(role, dict):
                yield role
        return
    for week in (brief.get("weekly_role_map") or {}).get("weeks") or []:
        if isinstance(week, dict):
            for role in week.get("session_roles") or []:
                if isinstance(role, dict):
                    yield role


def enrich_selected_assignment_context(brief: dict[str, Any]) -> dict[str, Any]:
    """Return a non-mutating, source-backed finalizer projection.

    Existing effective prescriptions always win. The normal strength bank dose
    is restored only when no scheduled cap exists. Capped strength resolution
    delegates to the existing resolver; a missing late-tail conditioning dose
    must be recovered from the actual selected-day authority, never a raw bank
    template. Missing closed strength/conditioning doses fail before rendering.
    """
    result = deepcopy(brief)
    pools = result.get("candidate_pools") or {}
    index = _source_index(pools) if isinstance(pools, dict) else {}
    athlete = result.get("athlete_snapshot") or result.get("athlete_model") or {}
    athlete_state = athlete_dose_state(athlete)

    for role in _visible_roles(result):
        assignments = role.get("selected_exercise_assignments")
        if not isinstance(assignments, list):
            continue
        category = _text(role.get("category")).lower()
        strength_records = [entry for entry in role.get("effective_strength_prescriptions") or []
                            if isinstance(entry, dict)]
        records_by_key = {(_text(entry.get("slot_id")), _text(entry.get("name"))): entry
                          for entry in strength_records}
        for assignment in assignments:
            if not isinstance(assignment, dict):
                continue
            name = _text(assignment.get("name"))
            if not name:
                continue
            source = _source_for(index, assignment)
            slot, option = source if source else ({}, {})
            if option:
                context = _coaching_context(option)
                if context:
                    assignment["coaching_context"] = context
                base = _quantitative(assignment.get("base_prescription")) or _quantitative(option.get("prescription"))
                if base:
                    assignment.setdefault("base_prescription", base)
            else:
                base = _quantitative(assignment.get("base_prescription"))

            effective = _dose(assignment.get("effective_prescription"))
            key = (_text(assignment.get("slot_id")), name)
            record = records_by_key.get(key)
            if not effective and record:
                effective = _dose(record.get("effective_prescription"))

            is_strength = category == "strength" and assignment.get("slot_group") == "strength_slots"
            if not effective and is_strength and source:
                cap = role.get("strength_dose_cap")
                if isinstance(cap, dict):
                    # Reuse existing scheduled-day/readiness logic. Never restore
                    # the uncapped bank dose over a late-camp restriction.
                    selected_slot = {**slot, "selected": option}
                    resolved = resolve_strength_slot_prescription(
                        role=role, slot=selected_slot, athlete_state=athlete_state,
                    )
                    effective = _dose(resolved.get("effective_prescription"))
                    if effective:
                        record = {"slot_id": assignment.get("slot_id"), "name": name, **resolved}
                else:
                    effective = base
                    if effective:
                        record = {"slot_id": assignment.get("slot_id"), "name": name,
                                  "base_prescription": base, "effective_prescription": effective,
                                  "dose_authority": "exercise_bank"}

            if not effective and role.get("late_fight_tail_owned"):
                effective = _authoritative_tail_dose(result, role, assignment)
            if not effective and category == "conditioning" and not role.get("late_fight_tail_owned"):
                # Normal conditioning has no scheduled-day cap in this source
                # projection. Preserve the already-selected bank prescription.
                effective = base

            if effective:
                assignment["effective_prescription"] = effective
                if record and is_strength and key not in records_by_key:
                    strength_records.append(record)
                    records_by_key[key] = record
            elif category in {"strength", "conditioning"}:
                raise MissingSelectedPrescriptionError({
                    "role_key": role.get("role_key"),
                    "scheduled_countdown_label": role.get("scheduled_countdown_label") or role.get("countdown_label"),
                    "slot_id": assignment.get("slot_id"), "name": name,
                    "reason": "selected_source_dose_unresolved",
                })

        if category == "strength" and strength_records:
            role["effective_strength_prescriptions"] = strength_records
    return result
