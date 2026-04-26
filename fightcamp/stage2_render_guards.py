from __future__ import annotations
import re
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .training_context import TrainingContext

from .normalization import clean_list, normalize_text, dedupe_preserve_order
from .stage2_payload_late_fight import _uses_late_fight_stage2_payload

NO_ACTIVE_INJURY_MARKERS = {
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

def meaningful_injury_values(values: Any) -> list[str]:
    cleaned = []
    for value in clean_list(values):
        token = re.sub(r"[^\w\s]", "", normalize_text(value)).replace("_", " ")
        if token and token not in NO_ACTIVE_INJURY_MARKERS:
            cleaned.append(value)
    return cleaned

def has_active_injury_from_training_context(training_context: TrainingContext) -> bool:
    return bool(
        meaningful_injury_values(getattr(training_context, "injuries", []))
        or getattr(training_context, "parsed_injuries", None)
        or getattr(training_context, "guided_injury", None)
        or getattr(training_context, "injury_restrictions", None)
    )

def has_active_injury_from_athlete_model(athlete_model: dict) -> bool:
    if "has_active_injury" in athlete_model:
        return bool(athlete_model.get("has_active_injury"))
    return bool(
        meaningful_injury_values(athlete_model.get("injuries", []))
        or athlete_model.get("parsed_injuries")
        or athlete_model.get("guided_injury")
        or athlete_model.get("injury_restrictions")
    )

def render_guard_flags(
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
    has_active_injury = has_active_injury_from_athlete_model(athlete_model)
    return {
        "has_active_injury": has_active_injury,
        "suppress_rehab_headings": not has_active_injury,
        "suppress_phase_toolbox_sections": late_fight_countdown,
        "render_mode": "late_fight_countdown_only" if late_fight_countdown else "camp_plan",
    }

def append_render_guard_writing_rules(
    rewrite_guidance: dict,
    *,
    athlete_model: dict,
    payload_mode: str = "",
    days_until_fight: int | None = None,
) -> dict:
    updated = dict(rewrite_guidance or {})
    rules = list(updated.get("writing_rules") or [])
    guards = render_guard_flags(
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
