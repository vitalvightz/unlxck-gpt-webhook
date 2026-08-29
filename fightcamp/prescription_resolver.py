"""Resolve final athlete-facing prescriptions from role-level countdown dose caps.

Exercise-bank prescriptions describe the base exercise dose. Late-camp role
metadata describes the maximum safe/appropriate dose after calendar placement.
This module reconciles the two deterministically so Stage 2 receives one final
effective prescription instead of contradictory base and countdown metadata.
"""
from __future__ import annotations

import re
from typing import Any


_SETS_REPS_RE = re.compile(r"(?P<sets>\d+)\s*[xX×]\s*(?P<reps>\d+)")
_RPE_RE = re.compile(r"RPE\s*(?P<rpe>\d+(?:\.\d+)?)", re.IGNORECASE)


def _parse_rpe_cap(value: Any) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    nums = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", text)]
    return max(nums) if nums else None


def _exercise_dose_class(option: dict[str, Any]) -> str:
    """Classify how late-camp volume should be reduced for one strength option."""
    quality = str(option.get("quality_class") or "").strip().lower()
    name = str(option.get("name") or "").strip().lower()
    patterns = " ".join(str(x).lower() for x in (option.get("movement_patterns") or []))
    text = f"{quality} {name} {patterns}"

    if option.get("anchor_capable") is True:
        return "anchor"
    if any(token in text for token in ("jump", "bound", "hop", "throw", "plyo", "explosive")):
        return "neural"
    if any(token in text for token in ("pallof", "anti_rotation", "anti-rotation", "core", "trunk", "mobility", "prehab")):
        return "support"
    return "secondary"


def _dynamic_multiplier(*, athlete_model: dict[str, Any] | None) -> float:
    """Return a conservative multiplier that can only reduce the countdown ceiling."""
    athlete = athlete_model or {}
    multiplier = 1.0
    fatigue = str(athlete.get("fatigue_level") or athlete.get("fatigue") or "").strip().lower()
    if fatigue in {"high", "very_high", "critical"}:
        multiplier *= 0.75
    elif fatigue in {"moderate", "medium"}:
        multiplier *= 0.9

    cut = str(
        athlete.get("cut_severity")
        or athlete.get("weight_cut_severity")
        or athlete.get("cut_severity_bucket")
        or ""
    ).strip().lower()
    if cut in {"high", "aggressive", "critical", "extreme"}:
        multiplier *= 0.8
    return max(0.5, min(1.0, multiplier))


def resolve_strength_prescription(
    *,
    option: dict[str, Any],
    role: dict[str, Any],
    athlete_model: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a copy of ``option`` with a deterministic effective prescription.

    The resolver never increases the bank dose. Anchor lifts retain meaningful
    loading longest; secondary/accessory work loses volume sooner; support and
    neural work keep their own rep character rather than being forced into the
    anchor's low-rep cap.
    """
    resolved = dict(option)
    base = str(option.get("prescription") or "").strip()
    cap = role.get("strength_dose_cap") if isinstance(role, dict) else None
    if not base or not isinstance(cap, dict):
        return resolved

    match = _SETS_REPS_RE.search(base)
    if not match:
        return resolved

    base_sets = int(match.group("sets"))
    base_reps = int(match.group("reps"))
    try:
        max_sets = int(cap.get("max_sets"))
        max_reps = int(cap.get("max_reps"))
    except (TypeError, ValueError):
        return resolved

    dose_class = _exercise_dose_class(option)
    multiplier = _dynamic_multiplier(athlete_model=athlete_model)

    if dose_class == "anchor":
        target_sets = min(base_sets, max_sets)
        target_reps = min(base_reps, max_reps)
    elif dose_class == "secondary":
        target_sets = min(base_sets, max(1, max_sets - 1))
        target_reps = min(base_reps, max(3, max_reps + 2))
    elif dose_class == "support":
        target_sets = min(base_sets, max(1, max_sets - 1))
        target_reps = base_reps
    else:  # neural / plyometric work
        target_sets = min(base_sets, max_sets)
        target_reps = min(base_reps, max(1, max_reps))

    target_sets = max(1, int(round(target_sets * multiplier)))
    target_reps = max(1, target_reps)

    effective = _SETS_REPS_RE.sub(f"{target_sets} x {target_reps}", base, count=1)
    rpe_cap = _parse_rpe_cap(role.get("rpe_cap"))
    if rpe_cap is not None:
        rpe_match = _RPE_RE.search(effective)
        if rpe_match:
            current_rpe = float(rpe_match.group("rpe"))
            if current_rpe > rpe_cap:
                replacement = str(int(rpe_cap) if rpe_cap.is_integer() else rpe_cap)
                effective = _RPE_RE.sub(f"RPE {replacement}", effective, count=1)

    resolved["base_prescription"] = base
    resolved["effective_prescription"] = effective
    resolved["prescription"] = effective
    resolved["dose_authority"] = "scheduled_countdown_overlay"
    resolved["dose_class"] = dose_class
    return resolved


def apply_effective_prescriptions(
    *,
    slots: list[dict[str, Any]],
    role: dict[str, Any],
    athlete_model: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Resolve selected and alternate strength options for a scheduled role."""
    output: list[dict[str, Any]] = []
    for slot in slots:
        updated = dict(slot)
        selected = updated.get("selected")
        if isinstance(selected, dict):
            updated["selected"] = resolve_strength_prescription(
                option=selected,
                role=role,
                athlete_model=athlete_model,
            )
        alternates = []
        for alternate in updated.get("alternates") or []:
            if isinstance(alternate, dict):
                alternates.append(
                    resolve_strength_prescription(
                        option=alternate,
                        role=role,
                        athlete_model=athlete_model,
                    )
                )
            else:
                alternates.append(alternate)
        if "alternates" in updated:
            updated["alternates"] = alternates
        output.append(updated)
    return output
