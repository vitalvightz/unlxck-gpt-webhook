"""Resolve effective late-camp prescriptions from scheduled-day dose envelopes.

Exercise-bank prescriptions remain useful as the base dose, but scheduled-day
countdown rules are authoritative once a role has been placed on the calendar.
This module produces deterministic effective-prescription metadata so Stage 2
never has to reconcile conflicting base exercise text and role-level caps.
"""

from __future__ import annotations

import re
from typing import Any


def _parse_sets_reps(prescription: str) -> tuple[int | None, int | None]:
    text = str(prescription or "")
    match = re.search(r"\b(\d+)\s*[xX×]\s*(\d+)\b", text)
    if not match:
        return None, None
    return int(match.group(1)), int(match.group(2))


def _role_kind(role: dict[str, Any], slot: dict[str, Any]) -> str:
    if slot.get("anchor_capable") or slot.get("quality_class") in {"anchor", "primary"}:
        return "anchor"
    movement = str(slot.get("role") or "").strip().lower()
    if movement in {"anti_rotation", "trunk", "core", "mobility", "prehab", "strength_support"}:
        return "support"
    return "secondary"


def _effective_counts(
    *,
    base_sets: int | None,
    base_reps: int | None,
    role_kind: str,
    strength_cap: dict[str, Any],
) -> tuple[int | None, int | None]:
    max_sets = strength_cap.get("max_sets")
    max_reps = strength_cap.get("max_reps")

    try:
        max_sets = int(max_sets) if max_sets is not None else None
    except (TypeError, ValueError):
        max_sets = None
    try:
        max_reps = int(max_reps) if max_reps is not None else None
    except (TypeError, ValueError):
        max_reps = None

    if role_kind == "anchor":
        sets = min(base_sets, max_sets) if base_sets is not None and max_sets is not None else (base_sets or max_sets)
        reps = min(base_reps, max_reps) if base_reps is not None and max_reps is not None else (base_reps or max_reps)
        return sets, reps

    if role_kind == "secondary":
        secondary_set_cap = max(1, (max_sets - 1) if isinstance(max_sets, int) and max_sets > 1 else (max_sets or 1))
        sets = min(base_sets, secondary_set_cap) if base_sets is not None else secondary_set_cap
        if base_reps is None:
            reps = None
        elif isinstance(max_reps, int) and max_reps <= 2:
            reps = min(base_reps, max_reps)
        else:
            reps = min(base_reps, 5)
        return sets, reps

    # Trunk/prehab/support work should not be forced into strength-lift rep caps.
    support_set_cap = 2 if not isinstance(max_sets, int) else min(2, max_sets)
    sets = min(base_sets, support_set_cap) if base_sets is not None else support_set_cap
    reps = base_reps
    return sets, reps


def _format_effective_prescription(
    *,
    base_prescription: str,
    sets: int | None,
    reps: int | None,
    rpe_cap: str | None,
) -> str:
    if sets is None or reps is None:
        return base_prescription
    dose = f"{sets} x {reps}"
    if rpe_cap:
        dose += f" @ RPE {rpe_cap} max"
    return dose


def resolve_strength_slot_prescription(
    *,
    role: dict[str, Any],
    slot: dict[str, Any],
) -> dict[str, Any]:
    """Return deterministic effective prescription metadata for one strength slot."""
    selected = slot.get("selected") if isinstance(slot.get("selected"), dict) else {}
    base_prescription = str(selected.get("prescription") or "").strip()
    cap = role.get("strength_dose_cap") if isinstance(role.get("strength_dose_cap"), dict) else None
    if not cap or not base_prescription:
        return {
            "base_prescription": base_prescription,
            "effective_prescription": base_prescription,
            "dose_authority": "exercise_bank",
        }

    kind = _role_kind(role, slot)
    base_sets, base_reps = _parse_sets_reps(base_prescription)
    sets, reps = _effective_counts(
        base_sets=base_sets,
        base_reps=base_reps,
        role_kind=kind,
        strength_cap=cap,
    )
    effective = _format_effective_prescription(
        base_prescription=base_prescription,
        sets=sets,
        reps=reps,
        rpe_cap=str(role.get("rpe_cap") or "").strip() or None,
    )
    return {
        "base_prescription": base_prescription,
        "effective_prescription": effective,
        "dose_authority": "scheduled_countdown_overlay",
        "dose_role_kind": kind,
        "strength_dose_cap": dict(cap),
    }


def apply_effective_strength_prescriptions(
    *,
    weekly_role_map: dict[str, Any],
    candidate_pools: dict[str, Any],
) -> dict[str, Any]:
    """Attach resolved strength prescriptions to role metadata for Stage 2 rendering.

    The resolver is deliberately non-destructive: bank prescriptions remain available
    as ``base_prescription`` while the scheduled-day result is stored under
    ``effective_strength_prescriptions`` and must be preferred by downstream renderers.
    """
    if not isinstance(weekly_role_map, dict) or not isinstance(candidate_pools, dict):
        return weekly_role_map

    for week in weekly_role_map.get("weeks", []) or []:
        if not isinstance(week, dict):
            continue
        phase = str(week.get("phase") or "").strip().upper()
        phase_pool = candidate_pools.get(phase) if isinstance(candidate_pools.get(phase), dict) else {}
        strength_slots = phase_pool.get("strength") if isinstance(phase_pool.get("strength"), list) else []
        for role in week.get("session_roles") or []:
            if not isinstance(role, dict) or not isinstance(role.get("strength_dose_cap"), dict):
                continue
            resolved = []
            for slot in strength_slots:
                if not isinstance(slot, dict):
                    continue
                item = resolve_strength_slot_prescription(role=role, slot=slot)
                if item.get("effective_prescription"):
                    resolved.append({
                        "slot_id": slot.get("slot_id"),
                        "name": (slot.get("selected") or {}).get("name") if isinstance(slot.get("selected"), dict) else None,
                        **item,
                    })
            if resolved:
                role["effective_strength_prescriptions"] = resolved
    return weekly_role_map
