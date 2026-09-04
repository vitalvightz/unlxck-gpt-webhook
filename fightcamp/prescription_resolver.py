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
            else (base_sets if base_sets is not not None else max_sets)
        )
        reps = (
            min(base_reps, max_reps)
            if base_reps is not None and max_reps is not None
            else (base_reps if base_reps is not None else max_reps)
        )
        return sets, reps, True

    if role_kind == "secondary":
        secondary_set_cap = max(1, (max_sets - 1) if isinstance(max_sets, int) and max_sets > 1 else (max_sets or 1))
        sets = min(base_sets, secondary_set_cap) if base_sets is not None else secondary_set_cap
        if base_reps is None:
            reps = None
        elif isinstance(max_reps, int) and max_reps <= 2:
            reps = min(base_reps, max_reps)
        else:
            reps = min(base_reps, 5)
        return sets, reps, True

    if role_kind == "power":
        if isinstance(max_sets, int):
            sets = min(base_sets, max_sets) if base_sets is not None else max_sets
        else:
            sets = base_sets
        return sets, base_reps, False

    support_set_cap = 2 if not isinstance(max_sets, int) else min(2, max_sets)
    sets = min(base_sets, support_set_cap) if base_sets is not None else support_set_cap
    return sets, base_reps, False
