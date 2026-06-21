"""Stage 2 render guard helpers.

Extracted from `stage2_payload` so the rules that decide whether to suppress
rehab/prehab headings or GPP/SPP/TAPER toolbox sections live in one place.

Behaviour is unchanged. The no-injury marker comparison strips punctuation
(via the inner ``re.sub`` step), so values like ``"none."``, ``"N/A"``, and
``"n/a!"`` all collapse to a marker token before lookup.
"""
from __future__ import annotations

import re
from typing import Any

from .normalization import clean_list, dedupe_preserve_order, normalize_text
from .stage2_payload_late_fight import _coerce_days, _uses_late_fight_stage2_payload
from .stage2_payload_open_ongoing import _uses_open_ongoing_payload
from .training_context import TrainingContext


_NO_ACTIVE_INJURY_MARKERS = {
    "",
    "none",
    "no",
    "no injury",
    "no injuries",
    "none reported",
    "n/a",
    "na",
    "nil",
    "nothing",
    "all clear",
}


def _meaningful_injury_values(values: Any) -> list[str]:
    cleaned = []
    for value in clean_list(values):
        token = re.sub(r"[^\w\s]", "", normalize_text(value)).replace("_", " ")
        if token and token not in _NO_ACTIVE_INJURY_MARKERS:
            cleaned.append(value)
    return cleaned


def _has_active_injury_from_training_context(training_context: TrainingContext) -> bool:
    return bool(
        _meaningful_injury_values(getattr(training_context, "injuries", []))
        or getattr(training_context, "parsed_injuries", None)
        or getattr(training_context, "guided_injury", None)
        or getattr(training_context, "injury_restrictions", None)
    )


def _has_active_injury_from_athlete_model(athlete_model: dict) -> bool:
    if "has_active_injury" in athlete_model:
        return bool(athlete_model.get("has_active_injury"))
    return bool(
        _meaningful_injury_values(athlete_model.get("injuries", []))
        or athlete_model.get("parsed_injuries")
        or athlete_model.get("guided_injury")
        or athlete_model.get("injury_restrictions")
    )


def _render_guard_flags(
    *, athlete_model: dict, payload_mode: str = "", days_until_fight: int | None = None
) -> dict[str, Any]:
    late_fight_countdown = bool(
        (payload_mode or "")
        in {
            "bridge_compression_payload",
            "pre_fight_compressed_payload",
            "late_fight_week_payload",
            "late_fight_transition_payload",
            "late_fight_session_payload",
            "pre_fight_day_payload",
            "fight_day_protocol_payload",
        }
        or _uses_late_fight_stage2_payload(days_until_fight)
    )
    # A scheduled fight (a coercible days_until_fight) means the athlete is on a
    # countdown, not an open-ended system. Honour the explicit parameter so the
    # open-ongoing fallback only fires when no fight is scheduled, even if the
    # athlete_model dict itself omits days_until_fight.
    scheduled_fight = _coerce_days(days_until_fight) is not None
    open_ongoing_mode = (not scheduled_fight) and _uses_open_ongoing_payload(athlete_model)
    has_active_injury = _has_active_injury_from_athlete_model(athlete_model)
    render_mode = "open_ongoing_system" if open_ongoing_mode else ("late_fight_countdown_only" if late_fight_countdown else "camp_plan")
    return {
        "has_active_injury": has_active_injury,
        "suppress_rehab_headings": not has_active_injury,
        "suppress_phase_toolbox_sections": late_fight_countdown or open_ongoing_mode,
        "render_mode": render_mode,
    }


def _append_render_guard_writing_rules(
    rewrite_guidance: dict,
    *,
    athlete_model: dict,
    payload_mode: str = "",
    days_until_fight: int | None = None,
) -> dict:
    updated = dict(rewrite_guidance or {})
    rules = list(updated.get("writing_rules") or [])
    guards = _render_guard_flags(
        athlete_model=athlete_model,
        payload_mode=payload_mode,
        days_until_fight=days_until_fight,
    )
    if guards["suppress_rehab_headings"]:
        rules.extend(
            [
                "athlete_model.has_active_injury is false: do not render any section titled Rehab, Injury Rehab, Brief Rehab, Prehab, Prepare / brief rehab, or Rehab / Mobility.",
                "When athlete_model.has_active_injury is false, general low-load support may appear only as Activation, Movement Prep, Mobility, Warm-up, or Reset work — never as rehab/prehab.",
                "Do not turn generic trunk, glute, shoulder, or mobility prep into rehab unless athlete_model.has_active_injury is true.",
            ]
        )
    if guards["suppress_phase_toolbox_sections"]:
        rules.extend(
            [
                "Late-fight countdown mode is active: do not render standalone GPP, SPP, or TAPER toolbox/reference sections.",
                "Candidate pools are internal selection data only. Do not output 'key drills to keep in your toolbox', 'available options', 'SPP tools', 'GPP tools', or phase reference menus.",
                "In late-fight countdown mode, only render scheduled D-day prescriptions, coach-owned days, explicit transition windows, and fight-day protocol.",
            ]
        )
    updated["writing_rules"] = dedupe_preserve_order(rules)
    updated["render_guards"] = guards
    return updated
