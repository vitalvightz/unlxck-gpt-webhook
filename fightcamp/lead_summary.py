"""Deterministic injury / weight-cut lead summary.

The Stage 2 validator requires that, when an athlete has an active injury or an
active weight cut, that context is summarised *before* the training detail —
specifically it scans the first ten plan lines for an injury keyword
(``injur|pain|strain|restriction|rehab|stop rule|...``) or a weight-cut keyword
(``weight cut|cut stress|target weight|dehydrat|...``). Stage 1 historically
buried both in the Athlete Profile near the bottom of the plan, so the finalizer
had to lift them up itself (validator codes ``missing_injury_lead_summary`` /
``missing_weight_cut_lead_summary``).

This module renders a short, athlete-facing lead summary deterministically from
the same athlete model the validator reads, using the same active-injury /
active-cut detection, so the requirement is satisfied at the source.
"""

from __future__ import annotations

from typing import Any

from .normalization import clean_list
from .stage2_render_guards import _has_active_injury_from_athlete_model

_ACTIVE_WEIGHT_CUT_FLAGS = {"active_weight_cut", "aggressive_weight_cut"}


def _athlete_model(planning_brief: dict[str, Any]) -> dict[str, Any]:
    model = planning_brief.get("athlete_model")
    if isinstance(model, dict) and model:
        return model
    snapshot = planning_brief.get("athlete_snapshot")
    return snapshot if isinstance(snapshot, dict) else {}


def _readiness_flags(athlete: dict[str, Any]) -> set[str]:
    return {str(flag).strip().lower() for flag in clean_list(athlete.get("readiness_flags")) if str(flag).strip()}


def _injury_active(athlete: dict[str, Any], readiness_flags: set[str]) -> bool:
    # Mirrors stage2_validator._risk_tone_context injury detection.
    return _has_active_injury_from_athlete_model(athlete) or "injury_management" in readiness_flags


def _weight_cut_active(athlete: dict[str, Any], readiness_flags: set[str]) -> bool:
    # Mirrors stage2_validator._weight_cut_context active detection.
    return bool(athlete.get("weight_cut_risk") or (readiness_flags & _ACTIVE_WEIGHT_CUT_FLAGS))


def _injury_phrase(athlete: dict[str, Any]) -> str:
    raw_text = str(athlete.get("injuries_raw_text") or "").strip()
    if raw_text:
        return raw_text
    injuries = [str(value).strip() for value in clean_list(athlete.get("injuries")) if str(value).strip()]
    if injuries:
        return ", ".join(injuries[:3])
    return "an active injury"


def _weight_cut_is_high_pressure(athlete: dict[str, Any], readiness_flags: set[str]) -> bool:
    if "aggressive_weight_cut" in readiness_flags:
        return True
    fatigue = str(athlete.get("fatigue", "")).strip().lower()
    days_until_fight = athlete.get("days_until_fight")
    return fatigue in {"moderate", "high"} or (
        isinstance(days_until_fight, int) and days_until_fight <= 28
    )


def render_lead_summary(planning_brief: dict[str, Any]) -> str:
    """Render the injury / weight-cut lead summary, or ``""`` when neither applies.

    The output leads with the keywords the validator scans for so that, once
    placed in the first lines of the plan, the lead-summary contract is met.
    """
    if not isinstance(planning_brief, dict):
        return ""
    athlete = _athlete_model(planning_brief)
    if not athlete:
        return ""
    readiness_flags = _readiness_flags(athlete)

    lines: list[str] = []
    if _injury_active(athlete, readiness_flags):
        lines.append(
            f"- **Injury watch:** {_injury_phrase(athlete)} — train around it: "
            "respect the listed restrictions, keep rehab in, and stop on sharp pain."
        )
    if _weight_cut_active(athlete, readiness_flags):
        if _weight_cut_is_high_pressure(athlete, readiness_flags):
            lines.append(
                "- **Weight cut:** active cut under pressure — manage cut stress toward "
                "target weight and protect recovery margin as the fight nears."
            )
        else:
            lines.append(
                "- **Weight cut:** active cut in play — manage cut stress toward target "
                "weight and protect recovery margin."
            )

    if not lines:
        return ""
    return "\n".join(["## Readiness & Constraints", "", *lines]).strip()
