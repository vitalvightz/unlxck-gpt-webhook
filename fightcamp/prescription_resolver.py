"""Resolve effective late-camp prescriptions from scheduled-day dose envelopes.

Exercise-bank prescriptions remain useful as the base dose, but scheduled-day
countdown rules are authoritative once a role has been placed on the calendar.
This module produces deterministic ``effective_prescription`` metadata so Stage 2
never has to reconcile conflicting base exercise text and role-level caps.

Design contract (kept deliberately narrow):

* It only runs AFTER ``apply_late_camp_role_morph`` has stamped a role's
  ``strength_dose_cap`` (a dict carrying ``max_sets`` / ``max_reps`` /
  ``loaded_allowed``), ``rpe_cap``, ``scheduled_d_day`` and
  ``dose_adjustment_reason``. It never re-derives the countdown band itself — the
  morph owns that — so calendar placement and dose shaping stay upstream.
* It is non-destructive: the exercise-bank prescription is preserved as
  ``base_prescription`` while the scheduled-day result is stored as
  ``effective_prescription`` and marked as the authoritative render dose.
* Exercise class matters. Anchor (primary loaded) work keeps the most meaningful
  loading the band allows; secondary loaded work loses more volume; support /
  trunk / prehab work loses sets but is never forced into low-rep strength reps;
  jumps / throws / neural power work keeps its own neural-quality reps. Loaded
  power/contrast work retains both its loaded-strength and ballistic semantics.
* Athlete readiness / cut / injury state may only reduce the resolved dose
  further — never raise it above the scheduled-day ceiling.
"""

from __future__ import annotations

import re
from typing import Any

from .calendar_context import role_d_day
from .late_camp_role_morph import FULL_STRENGTH_ROLE_KEYS, STRENGTH_NEURAL_MORPH_MAX_D
from .strength_session_quality import (
    ANCHOR_CAPABLE_CLASSES,
    SUPPORT_ONLY_CLASSES,
    classify_strength_item,
)


class MissingLateCampEffectiveStrengthAuthorityError(ValueError):
    """A loaded late-camp role reached the Stage 2 boundary without dose truth."""

    code = "missing_late_camp_effective_strength_authority"

    def __init__(self, details: dict[str, Any]):
        self.details = details
        fields = ", ".join(str(field) for field in details.get("missing_fields", []))
        super().__init__(
            f"{self.code}: role_key={details.get('role_key')!r}, "
            f"week_index={details.get('week_index')!r}, "
            f"session_index={details.get('session_index')!r}, "
            f"scheduled_weekday={details.get('scheduled_weekday')!r}, "
            f"original_countdown={details.get('original_countdown')!r}, "
            f"scheduled_countdown={details.get('scheduled_countdown')!r}, "
            f"resolved_d_day={details.get('resolved_d_day')!r}, "
            f"missing_fields=[{fields}]"
        )

# Movement-role names that mark low-load trunk / prehab / support work even when
# a quality class is unavailable. Mirrors the reservoir/support taxonomy.
_SUPPORT_MOVEMENT_ROLES = frozenset(
    {
        "anti_rotation",
        "trunk",
        "core",
        "mobility",
        "prehab",
        "rehab",
        "strength_support",
    }
)


def _parse_sets_reps(prescription: str) -> tuple[int | None, int | None]:
    text = str(prescription or "")
    match = re.search(r"\b(\d+)\s*[xX×]\s*(\d+)\b", text)
    if not match:
        return None, None
    return int(match.group(1)), int(match.group(2))


def _rpe_ceiling(rpe_cap: Any) -> int | None:
    """Return the numeric high end of an RPE cap string like ``"6-7"`` -> 7."""
    values = [int(match) for match in re.findall(r"\d+", str(rpe_cap or ""))]
    return max(values) if values else None


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _slot_selected(slot: dict[str, Any]) -> dict[str, Any]:
    selected = slot.get("selected")
    return selected if isinstance(selected, dict) else {}


def _slot_quality_class(slot: dict[str, Any]) -> str:
    """Return the quality class the planner already stamped, or ``""``.

    Only explicit slot / selected metadata is used here — classification of a
    bare exercise is done in :func:`_role_kind` as a last resort so an explicit
    ``anchor_capable`` / ``support_only`` flag always wins over a default class.
    """
    selected = _slot_selected(slot)
    for source in (slot, selected):
        quality_class = str(source.get("quality_class") or "").strip()
        if quality_class:
            return quality_class
    return ""


def _has_explicit_strength_intensity(prescription: str) -> bool:
    """Return whether a power-labelled item explicitly carries loaded intensity."""
    text = str(prescription or "")
    return bool(
        re.search(r"\b\d+(?:\.\d+)?(?:\s*[-–]\s*\d+(?:\.\d+)?)?\s*%", text)
        or re.search(r"\bRPE\s*[:=]?\s*\d+(?:\.\d+)?", text, re.I)
    )


def _is_loaded_power_hybrid(slot: dict[str, Any], *, classified: dict[str, Any] | None = None) -> bool:
    """Identify a ballistic/contrast slot that also contains real loaded work.

    ``anchor_power`` is intentionally broad: it covers pure jumps/throws as well
    as contrast lifts such as ``Heavy RDL → Broad Jump``. The latter must not lose
    their loaded-strength semantics merely because power is the headline quality.
    We require both an explicit loaded structural signal and an explicit working
    intensity; pure neural/ballistic work therefore remains power-only.
    """
    selected = _slot_selected(slot)
    quality_class = _slot_quality_class(slot)
    profile = classified
    if not quality_class and selected:
        profile = profile or classify_strength_item(selected)
        quality_class = str(profile.get("quality_class") or "")
    if quality_class != "anchor_power":
        return False

    base_categories = {
        str(value).strip()
        for value in [
            *(slot.get("base_categories") or []),
            *(selected.get("base_categories") or []),
        ]
        if str(value).strip()
    }
    if not base_categories and selected:
        profile = profile or classify_strength_item(selected)
        base_categories.update(str(value).strip() for value in profile.get("base_categories") or [] if str(value).strip())
    loaded_structure = bool(base_categories & {"lower_body_loaded", "upper_body_push_pull"})
    if not loaded_structure and profile:
        loaded_structure = bool(profile.get("loaded_pattern"))
    return loaded_structure and _has_explicit_strength_intensity(selected.get("prescription") or "")


def _role_kind(slot: dict[str, Any]) -> str:
    """Classify a strength slot's programming role.

    Returns one of ``anchor`` (primary loaded strength / max-force isometric),
    ``hybrid`` (loaded contrast/power work that carries both strength and power),
    ``power`` (pure jumps / throws / olympic / ballistic neural work), ``support``
    (trunk / anti-rotation / prehab / accessory) or ``secondary`` (a loaded lift
    that is not the session's primary anchor). Explicit structural flags win; a
    bare exercise is classified only when it carries no such signal.
    """
    selected = _slot_selected(slot)
    quality_class = _slot_quality_class(slot)
    anchor_flag = bool(slot.get("anchor_capable") or selected.get("anchor_capable"))
    support_flag = bool(slot.get("support_only") or selected.get("support_only"))
    movement = str(slot.get("role") or selected.get("role") or "").strip().lower()

    if quality_class == "anchor_power":
        return "hybrid" if _is_loaded_power_hybrid(slot) else "power"
    if support_flag or quality_class in SUPPORT_ONLY_CLASSES or movement in _SUPPORT_MOVEMENT_ROLES:
        return "support"
    if anchor_flag or quality_class in ANCHOR_CAPABLE_CLASSES:
        return "anchor"

    # No explicit structural signal at all: fall back to classifying the exercise.
    if not quality_class and not anchor_flag and not support_flag and selected:
        classified = classify_strength_item(selected)
        classified_class = str(classified.get("quality_class") or "")
        if classified_class == "anchor_power":
            return "hybrid" if _is_loaded_power_hybrid(slot, classified=classified) else "power"
        if classified.get("support_only") and movement not in {"press", "hinge", "squat", "pull", "row"}:
            return "support"
        if classified.get("anchor_capable"):
            return "anchor"
    return "secondary"


def _slot_quality_class_effective(slot: dict[str, Any]) -> str:
    """Quality class including the classify fallback (for anchor-loaded demotion)."""
    quality_class = _slot_quality_class(slot)
    if quality_class:
        return quality_class
    selected = _slot_selected(slot)
    if selected:
        return str(classify_strength_item(selected).get("quality_class") or "")
    return ""


def _effective_counts(
    *,
    base_sets: int | None,
    base_reps: int | None,
    role_kind: str,
    strength_cap: dict[str, Any],
) -> tuple[int | None, int | None, bool]:
    """Return ``(effective_sets, effective_reps, loaded)`` for one slot.

    ``loaded`` is False when the resolved prescription carries no loaded strength
    stimulus (either the band forbids loaded lifting, or the exercise is neural /
    support work that is never treated as loaded strength).
    """
    max_sets = _int_or_none(strength_cap.get("max_sets"))
    max_reps = _int_or_none(strength_cap.get("max_reps"))
    # Absent flag (hand-built caps in focused unit tests) means "loaded still
    # allowed" so the anchor/secondary/hybrid maths run as before.
    loaded_allowed = strength_cap.get("loaded_allowed") is not False

    if role_kind in {"anchor", "secondary", "hybrid"}:
        if not loaded_allowed:
            # Band no longer permits loaded strength work: no loaded lift renders.
            return None, None, False

    if role_kind in {"anchor", "hybrid"}:
        sets = (
            min(base_sets, max_sets)
            if base_sets is not None and max_sets is not None
            else (base_sets if base_sets is not None else max_sets)
        )
        reps = (
            min(base_reps, max_reps)
            if base_reps is not None and max_reps is not None
            else (base_reps if base_reps is not None else max_reps)
        )
        return sets, reps, True

    if role_kind == "secondary":
        # Secondary loaded work loses a set earlier than the anchor.
        secondary_set_cap = max(1, (max_sets - 1) if isinstance(max_sets, int) and max_sets > 1 else (max_sets or 1))
        sets = min(base_sets, secondary_set_cap) if base_sets is not None else secondary_set_cap
        if base_reps is None:
            reps = None
        elif isinstance(max_reps, int) and max_reps <= 2:
            reps = min(base_reps, max_reps)
        else:
            # Keep a strength-meaningful rep count rather than collapsing to the
            # anchor's low-rep cap.
            reps = min(base_reps, 5)
        return sets, reps, True

    if role_kind == "power":
        # Jumps / throws / neural power keep their own neural-quality reps; only
        # total volume (sets) tracks the countdown ceiling. Never a loaded lift.
        if isinstance(max_sets, int):
            sets = min(base_sets, max_sets) if base_sets is not None else max_sets
        else:
            sets = base_sets
        return sets, base_reps, False

    # Support / trunk / anti-rotation / prehab: reduce sets, keep reps. Never
    # forced into 2-3 rep strength work, never treated as loaded strength.
    support_set_cap = 2 if not isinstance(max_sets, int) else min(2, max_sets)
    sets = min(base_sets, support_set_cap) if base_sets is not None else support_set_cap
    return sets, base_reps, False


_NO_LOADED_LIFTING = "No loaded lifting — neural/primer, readiness or mobility only"


def _format_effective_prescription(
    *,
    base_prescription: str,
    sets: int | None,
    reps: int | None,
    rpe_cap: str | None,
    loaded: bool,
    suppressed_loaded_lift: bool = False,
) -> str:
    if sets is None or reps is None:
        # Only a loaded lift forbidden by the countdown band is suppressed.
        # Timed isometrics, throws, primers and support work often have a valid
        # non-NxM bank prescription and must retain it verbatim.
        return _NO_LOADED_LIFTING if suppressed_loaded_lift else base_prescription
    if sets == 0 or reps == 0:
        return _NO_LOADED_LIFTING
    dose = f"{sets} x {reps}"
    if rpe_cap:
        dose += f" @ RPE {rpe_cap} max"
    return dose


def _athlete_dose_reduction(athlete_state: dict[str, Any] | None) -> int:
    """Return an additional set reduction (0 or 1) from athlete readiness state.

    Athlete state may only ever REDUCE the countdown-resolved dose, never raise
    it. A single bounded step keeps the reduction monotonic: any active risk
    signal reduces by one set; a higher-risk profile is therefore always the same
    or lower than a lower-risk one at the same D-day, never higher.
    """
    if not isinstance(athlete_state, dict):
        return 0
    if any(
        bool(athlete_state.get(flag))
        for flag in ("high_fatigue", "aggressive_weight_cut", "recent_contact_load", "injury_restricted")
    ):
        return 1
    return 0


def athlete_dose_state(athlete_model: dict[str, Any] | None) -> dict[str, bool]:
    """Derive the reduce-only athlete readiness signals the resolver consumes."""
    if not isinstance(athlete_model, dict):
        return {}
    readiness_flags = {
        str(flag).strip().lower()
        for flag in (athlete_model.get("readiness_flags") or [])
        if str(flag).strip()
    }
    fatigue = str(athlete_model.get("fatigue") or "").strip().lower()
    cut_bucket = str(athlete_model.get("cut_severity_bucket") or "").strip().lower()
    try:
        weight_cut_pct = float(athlete_model.get("weight_cut_pct") or 0.0)
    except (TypeError, ValueError):
        weight_cut_pct = 0.0
    injuries = athlete_model.get("injuries") or athlete_model.get("parsed_injuries") or []
    return {
        "high_fatigue": fatigue == "high" or "high_fatigue" in readiness_flags,
        "aggressive_weight_cut": (
            "aggressive_weight_cut" in readiness_flags
            or cut_bucket in {"high", "aggressive", "severe"}
            or weight_cut_pct >= 5.0
        ),
        "injury_restricted": bool(injuries) or "injury_management" in readiness_flags,
        # Reserved for future per-day coach/contact adjacency; left False here so
        # the reduction stays athlete-level and monotonic in this PR.
        "recent_contact_load": False,
    }


def resolve_strength_slot_prescription(
    *,
    role: dict[str, Any],
    slot: dict[str, Any],
    athlete_state: dict[str, Any] | None = None,
    force_kind: str | None = None,
) -> dict[str, Any]:
    """Return deterministic effective-prescription metadata for one strength slot.

    ``force_kind`` lets the caller override the per-slot classification (used to
    demote the non-primary loaded lift in a multi-lift session to ``secondary``).
    """
    selected = _slot_selected(slot)
    base_prescription = str(selected.get("prescription") or "").strip()
    cap = role.get("strength_dose_cap") if isinstance(role.get("strength_dose_cap"), dict) else None
    if not cap or not base_prescription:
        return {
            "base_prescription": base_prescription,
            "effective_prescription": base_prescription,
            "dose_authority": "exercise_bank",
        }

    kind = force_kind or _role_kind(slot)
    base_sets, base_reps = _parse_sets_reps(base_prescription)
    sets, reps, loaded = _effective_counts(
        base_sets=base_sets,
        base_reps=base_reps,
        role_kind=kind,
        strength_cap=cap,
    )

    # Readiness / cut / injury state can only pull the dose down further.
    reduction = _athlete_dose_reduction(athlete_state)
    if reduction and loaded and isinstance(sets, int) and sets > 1:
        sets = max(1, sets - reduction)

    rpe_cap = str(role.get("rpe_cap") or "").strip() or None
    effective = _format_effective_prescription(
        base_prescription=base_prescription,
        sets=sets,
        reps=reps,
        rpe_cap=rpe_cap,
        loaded=loaded,
        suppressed_loaded_lift=kind in {"anchor", "secondary", "hybrid"} and not loaded,
    )
    result = {
        "base_prescription": base_prescription,
        "effective_prescription": effective,
        "dose_authority": "scheduled_countdown_overlay",
        "dose_role_kind": kind,
        "dose_adjustment_reason": role.get("dose_adjustment_reason"),
        "effective_loaded": bool(loaded),
        "strength_dose_cap": dict(cap),
    }
    if isinstance(sets, int):
        result["effective_max_sets"] = sets
    if isinstance(reps, int):
        result["effective_max_reps"] = reps
    rpe_high = _rpe_ceiling(role.get("rpe_cap"))
    if rpe_high is not None:
        result["effective_rpe_cap"] = rpe_high
    return result


def _strength_slots_for_phase(candidate_pools: dict[str, Any], phase: str) -> list[dict[str, Any]]:
    phase_pool = candidate_pools.get(phase)
    if not isinstance(phase_pool, dict):
        return []
    slots = phase_pool.get("strength_slots")
    if not isinstance(slots, list):
        return []
    return [slot for slot in slots if isinstance(slot, dict)]


def _is_strength_role(role: dict[str, Any]) -> bool:
    role_key = str(role.get("role_key") or "").strip().lower()
    return (
        str(role.get("category") or "").strip().lower() == "strength"
        or role_key in FULL_STRENGTH_ROLE_KEYS
        or str(role.get("preferred_pool") or "").strip().lower() == "strength_slots"
    )


def _strength_role_slot_groups(
    *,
    weekly_role_map: dict[str, Any],
    candidate_pools: dict[str, Any],
):
    """Yield each scheduled strength role with the candidate slots it owns."""
    for week in weekly_role_map.get("weeks", []) or []:
        if not isinstance(week, dict):
            continue
        phase = str(week.get("phase") or "").strip().upper()
        strength_slots = _strength_slots_for_phase(candidate_pools, phase)
        strength_role_index = 0
        for role in week.get("session_roles") or []:
            if not isinstance(role, dict) or not _is_strength_role(role):
                continue
            strength_role_index += 1
            role_session_index = _int_or_none(role.get("strength_session_index")) or strength_role_index
            owned_slots = [
                slot
                for slot in strength_slots
                if (_int_or_none(slot.get("session_index")) or 1) == role_session_index
            ]
            yield week, role, owned_slots


def _loaded_candidate_names(owned_slots: list[dict[str, Any]]) -> list[str]:
    names: list[str] = []
    for slot in owned_slots:
        selected = _slot_selected(slot)
        if (
            _role_kind(slot) not in {"anchor", "secondary", "hybrid"}
            or not str(selected.get("prescription") or "").strip()
        ):
            continue
        name = str(selected.get("name") or slot.get("slot_id") or "").strip()
        if name and name not in names:
            names.append(name)
    return names


def assert_late_camp_effective_strength_authority(
    *,
    weekly_role_map: dict[str, Any],
    candidate_pools: dict[str, Any],
) -> None:
    """Block Stage 2 when a loaded countdown role lacks scheduled-day authority."""
    if not isinstance(weekly_role_map, dict) or not isinstance(candidate_pools, dict):
        return

    for week, role, owned_slots in _strength_role_slot_groups(
        weekly_role_map=weekly_role_map,
        candidate_pools=candidate_pools,
    ):
        d_day = role_d_day(week, role)
        loaded_names = _loaded_candidate_names(owned_slots)
        if (
            d_day is None
            or not 0 <= d_day <= STRENGTH_NEURAL_MORPH_MAX_D
            or not loaded_names
        ):
            continue

        missing: list[str] = []
        cap = role.get("strength_dose_cap")
        if not isinstance(cap, dict):
            missing.append("strength_dose_cap")
        elif not isinstance(cap.get("loaded_allowed"), bool):
            missing.append("strength_dose_cap.loaded_allowed")

        if _int_or_none(role.get("scheduled_d_day")) != d_day:
            missing.append("scheduled_d_day")
        if not str(role.get("dose_adjustment_reason") or "").strip():
            missing.append("dose_adjustment_reason")
        if _rpe_ceiling(role.get("rpe_cap")) is None:
            missing.append("rpe_cap")

        prescriptions = role.get("effective_strength_prescriptions")
        if not isinstance(prescriptions, list) or not prescriptions:
            missing.append("effective_strength_prescriptions")
            prescriptions = []
        by_name = {
            str(item.get("name") or "").strip(): item
            for item in prescriptions
            if isinstance(item, dict) and str(item.get("name") or "").strip()
        }
        for name in loaded_names:
            item = by_name.get(name)
            if not item:
                missing.append(f"effective_strength_prescriptions[{name}]")
                continue
            if not str(item.get("effective_prescription") or "").strip():
                missing.append(f"effective_strength_prescriptions[{name}].effective_prescription")
            if item.get("dose_authority") != "scheduled_countdown_overlay":
                missing.append(f"effective_strength_prescriptions[{name}].dose_authority")
            if not isinstance(item.get("effective_loaded"), bool):
                missing.append(f"effective_strength_prescriptions[{name}].effective_loaded")

        envelope = role.get("effective_strength_envelope")
        if not isinstance(envelope, dict):
            missing.append("effective_strength_envelope")
        else:
            if _int_or_none(envelope.get("scheduled_d_day")) != d_day:
                missing.append("effective_strength_envelope.scheduled_d_day")
            if not isinstance(envelope.get("loaded_allowed"), bool):
                missing.append("effective_strength_envelope.loaded_allowed")
            if _int_or_none(envelope.get("rpe_cap_high")) is None:
                missing.append("effective_strength_envelope.rpe_cap_high")

        if missing:
            raise MissingLateCampEffectiveStrengthAuthorityError(
                {
                    "role_key": role.get("role_key"),
                    "week_index": week.get("week_index"),
                    "session_index": role.get("session_index"),
                    "scheduled_weekday": role.get("scheduled_day_hint") or role.get("real_weekday"),
                    "original_countdown": role.get("countdown_label"),
                    "scheduled_countdown": role.get("scheduled_countdown_label"),
                    "resolved_d_day": d_day,
                    "loaded_exercises": loaded_names,
                    "missing_fields": missing,
                }
            )


_PRIORITY_ORDER = {"critical": 0, "anchor": 0, "primary": 0, "high": 1, "secondary": 1,
                   "medium": 2, "support": 2, "power": 2, "ballistic": 2, "low": 3}


def _slot_priority(slot: dict[str, Any]) -> tuple[int, int]:
    raw_priority = slot.get("priority")
    priority = _int_or_none(raw_priority)
    if priority is None:
        priority = _PRIORITY_ORDER.get(str(raw_priority or "").strip().lower())
    session_index = _int_or_none(slot.get("session_index")) or 1
    return (priority if priority is not None else 10_000, session_index)


def _build_role_envelope(
    role: dict[str, Any],
    resolved: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Summarise the loaded-strength ceiling for the validator to compare against.

    The envelope tracks the anchor (most permissive loaded lift) so a rendered
    dose only trips the validator when it exceeds even that ceiling, and lists
    the loaded exercise names so the validator can match rendered lines precisely
    without dose-checking legitimately higher-rep support / power work.
    """
    cap = role.get("strength_dose_cap") if isinstance(role.get("strength_dose_cap"), dict) else {}
    loaded_entries = [item for item in resolved if item.get("dose_role_kind") in {"anchor", "secondary", "hybrid"}]
    loaded_names = [item.get("name") for item in loaded_entries if item.get("name")]
    loaded_allowed = cap.get("loaded_allowed") is not False and any(
        item.get("effective_loaded") for item in loaded_entries
    )

    max_sets = None
    max_reps = None
    for item in loaded_entries:
        if not item.get("effective_loaded"):
            continue
        item_sets = item.get("effective_max_sets")
        item_reps = item.get("effective_max_reps")
        if isinstance(item_sets, int):
            max_sets = item_sets if max_sets is None else max(max_sets, item_sets)
        if isinstance(item_reps, int):
            max_reps = item_reps if max_reps is None else max(max_reps, item_reps)

    envelope = {
        "scheduled_d_day": role.get("scheduled_d_day"),
        "dose_adjustment_reason": role.get("dose_adjustment_reason"),
        "loaded_allowed": bool(loaded_allowed),
        "rpe_cap_high": _rpe_ceiling(role.get("rpe_cap")),
        "loaded_exercise_names": loaded_names,
    }
    if isinstance(max_sets, int):
        envelope["max_sets"] = max_sets
    if isinstance(max_reps, int):
        envelope["max_reps"] = max_reps
    return envelope


def apply_effective_strength_prescriptions(
    *,
    weekly_role_map: dict[str, Any],
    candidate_pools: dict[str, Any],
    athlete_model: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Attach resolved strength prescriptions to role metadata for Stage 2.

    Runs after ``apply_late_camp_role_morph`` so every strength role that a
    countdown cap applies to already carries ``strength_dose_cap`` (with
    ``loaded_allowed``), ``rpe_cap``, ``scheduled_d_day`` and
    ``dose_adjustment_reason``. The resolver is deliberately non-destructive: bank
    prescriptions stay as ``base_prescription`` while the scheduled-day result is
    stored under ``effective_strength_prescriptions`` (per candidate slot) and
    summarised in ``effective_strength_envelope`` for validator enforcement.
    """
    if not isinstance(weekly_role_map, dict) or not isinstance(candidate_pools, dict):
        return weekly_role_map

    athlete_state = athlete_dose_state(athlete_model)

    for week, role, owned_slots in _strength_role_slot_groups(
        weekly_role_map=weekly_role_map,
        candidate_pools=candidate_pools,
    ):
        if not isinstance(role.get("strength_dose_cap"), dict):
            continue
        scheduled_d_day = role_d_day(week, role)
        if scheduled_d_day is not None:
            role["scheduled_d_day"] = scheduled_d_day

        # Demote every anchor-capable loaded lift after the highest-priority one
        # to ``secondary`` so later loaded work loses more volume. Loaded-power
        # hybrids compete for the same loaded-anchor budget; pure neural power
        # remains outside it. Ordered by planner slot priority.
        anchor_loaded_used = False
        resolved: list[dict[str, Any]] = []
        for slot in sorted(owned_slots, key=_slot_priority):
            kind = _role_kind(slot)
            force_kind = None
            if kind in {"anchor", "hybrid"} and _slot_quality_class_effective(slot) != "anchor_force_isometric":
                if anchor_loaded_used:
                    force_kind = "secondary"
                else:
                    anchor_loaded_used = True
            item = resolve_strength_slot_prescription(
                role=role,
                slot=slot,
                athlete_state=athlete_state,
                force_kind=force_kind,
            )
            if not item.get("effective_prescription"):
                continue
            entry = {
                "slot_id": slot.get("slot_id"),
                "name": (_slot_selected(slot).get("name") if _slot_selected(slot) else None),
                **item,
            }
            resolved.append(entry)

        if not resolved:
            continue
        role["effective_strength_prescriptions"] = resolved
        envelope = _build_role_envelope(role, resolved)
        if envelope:
            role["effective_strength_envelope"] = envelope
    return weekly_role_map
