"""Late-camp conditioning role morph (deterministic overlay).

The D-14/D-13 late conditioning lock stops the combat-pressure floor from
*adding* new hard work, but a hard SPP glycolytic / fight-pace role that the
baseline planner scheduled can still survive at D-13 and closer, producing
sessions like "D-12 — Fight-pace conditioning, 4 x 3:00 @ RPE 8". That is too
hard too late: D-19/D-18 own the final real pressure exposure.

This module is a small deterministic overlay that runs after every role has a
scheduled D-day (after ``fill_missing_session_days`` and the camp-week fillers,
before labels are stamped). It only reduces load. It also records a semantic
post-morph validation result so a role cannot silently keep its old intent label
when its final dose no longer satisfies that intent.

Stage 3 wires the final calendar-integrity governor immediately after this
scheduled-day morph. If integrity relocates a normal-camp role, the same morph
core runs once more so countdown dose is re-resolved by this module rather than
by the calendar governor.
"""

from __future__ import annotations

from typing import Any


FIGHT_PACE_MORPH_MAX_D = 13
STRENGTH_NEURAL_MORPH_MAX_D = 17
STRENGTH_LABEL_MORPH_MAX_D = 12
COMBAT_FLOOR_MIN_D = 18

HARD_FIGHT_PACE_ROLE_KEYS = frozenset(
    {
        "fight_pace_repeatability_day",
        "main_fight_pace_day",
        "highest_glycolytic_day",
        "controlled_repeatability_day",
    }
)

FULL_STRENGTH_ROLE_KEYS = frozenset(
    {
        "primary_strength_day",
        "secondary_strength_day",
        "structural_strength_day",
        "transfer_strength_day",
        "neural_plus_strength_day",
    }
)

_RHYTHM_TOUCH_ROLE_KEY = "light_fight_pace_touch_day"
_RHYTHM_TOUCH_LABEL = "Rhythm flush"
_NEURAL_TOUCH_LABEL = "Neural speed touch"

_STRENGTH_DOSE_BANDS = (
    (14, 3, 3, "6-7", "2-3 sets", "2-3 reps", "low-volume strength-retention touch",
     "familiar low-load strength retention only; never a grinding loaded session"),
    (10, 2, 3, "6-7", "2 sets", "2-3 reps", "reduced strength maintenance touch",
     "familiar low-load strength maintenance only; never a grinding loaded session"),
    (8, 2, 2, "6-7", "1-2 sets", "1-2 reps", "minimal strength maintenance touch",
     "single familiar low-load maintenance lift; no back-off volume, no failure"),
    (7, 2, 1, "6", "1-2 sets", "isometric / neural microdose", "neural / max-force micro-touch",
     "isometric or neural microdose only; no loaded strength-transfer reps"),
    (5, 1, 1, "5-6", "1 set", "low-cost neural / power microdose", "low-cost neural / power microdose",
     "low-cost neural / power expression only; no loaded strength work"),
    (2, 1, 1, "5", "1 set", "throw / primer microdose", "sharpness microdose only",
     "throws / primers only, tiny sharpness dose; no loaded strength work"),
    (0, 0, 0, "3-5", "no loaded lifting", "none", "no meaningful lifting stimulus",
     "no meaningful lifting stimulus; readiness touch / mobility only"),
)


def late_fight_strength_dose_cap(d_day):
    """Return the deterministic strength-lift dose cap for ``d_day``."""
    try:
        d = int(d_day)
    except (TypeError, ValueError):
        return None
    if d < 0 or d > STRENGTH_NEURAL_MORPH_MAX_D:
        return None
    for min_d, max_sets, max_reps, rpe_cap, set_cap, rep_cap, dose_label, movement_note in _STRENGTH_DOSE_BANDS:
        if d >= min_d:
            return {
                "max_sets": max_sets,
                "max_reps": max_reps,
                "rpe_cap": rpe_cap,
                "set_cap": set_cap,
                "rep_cap": rep_cap,
                "dose_label": dose_label,
                "movement_note": movement_note,
            }
    return None


def _strength_dose_selection_rule(cap: dict) -> str:
    return (
        f"Low-volume neural maintenance touch only: {cap['set_cap']} x "
        f"{cap['rep_cap']} at RPE {cap['rpe_cap']} max with full recovery. "
        f"{cap['movement_note'][0].upper()}{cap['movement_note'][1:]}. "
        "Never render this as a loaded strength-transfer session — keep bar/"
        "implement speed high and the dose tiny."
    )


_HARD_PRESSURE_ROLE_FIELDS = (
    "combat_pressure",
    "meaningful_stress",
    "mandatory_hard_conditioning_exposure",
    "prescribed_intensity_rpe",
    "prescribed_dose",
    "glycolytic_target",
    "density_target",
    "hard_pressure",
    "high_glycolytic",
    "combat_pressure_floor",
    "floor_purpose",
    "floor_stop_rule",
    "upgraded_from_combat_pressure_floor",
)

_RHYTHM_TOUCH_SELECTION_RULE = (
    "Low-cost rhythm touch only: RPE 4-6 max with full recovery between "
    "efforts. Focus on rhythm, timing, entries and exits, breathing, and "
    "guard reset. No glycolytic density, no lactic burn — keep the dose flat "
    "and never build this session toward harder work."
)


def _week_calendar_d_day(week: dict[str, Any], weekday: Any) -> int | None:
    normalized = str(weekday or "").strip().lower()
    if not normalized:
        return None
    for day in week.get("calendar_days") or []:
        if not isinstance(day, dict):
            continue
        if str(day.get("weekday") or "").strip().lower() == normalized:
            try:
                return int(day.get("d_day"))
            except (TypeError, ValueError):
                return None
    return None


def _role_d_day(week: dict[str, Any], role: dict[str, Any]) -> int | None:
    d_day = _week_calendar_d_day(week, role.get("scheduled_day_hint"))
    if d_day is not None:
        return d_day
    for key in ("scheduled_countdown_label", "countdown_label"):
        label = str(role.get(key) or "").strip().upper()
        if label.startswith("D-"):
            digits = []
            for char in label[2:]:
                if char.isdigit():
                    digits.append(char)
                else:
                    break
            if digits:
                return int("".join(digits))
    return None


def _is_hard_fight_pace_conditioning_role(role: dict[str, Any]) -> bool:
    role_key = str(role.get("role_key") or "").strip().lower()
    if role_key == _RHYTHM_TOUCH_ROLE_KEY:
        return False
    if role_key in HARD_FIGHT_PACE_ROLE_KEYS:
        return True
    category = str(role.get("category") or "").strip().lower()
    system = str(role.get("preferred_system") or "").strip().lower()
    return category == "conditioning" and system == "glycolytic"


def _clear_hard_pressure_metadata(role: dict[str, Any]) -> None:
    for field in _HARD_PRESSURE_ROLE_FIELDS:
        role.pop(field, None)
    role["stress_class"] = "support"
    role["cost_class"] = "low"
    governance = role.get("governance")
    if not isinstance(governance, dict):
        governance = {}
    governance = dict(governance)
    for key in list(governance):
        lowered = str(key).lower()
        if lowered.startswith("hard") or "hard_pressure" in lowered:
            governance.pop(key)
    governance.pop("support_cap", None)
    governance.pop("forbidden_secondary_stressors", None)
    governance["meaningful_stress"] = False
    governance["main_job"] = "conditioning"
    governance["authority"] = "late_camp_role_morph"
    role["governance"] = governance


def _morph_to_rhythm_touch(role: dict[str, Any], d_day: int) -> None:
    role["original_role_key"] = str(role.get("role_key") or "")
    role["original_training_intent"] = "hard_conditioning"
    role["role_key"] = _RHYTHM_TOUCH_ROLE_KEY
    role["athlete_facing_label"] = _RHYTHM_TOUCH_LABEL
    role["category"] = "conditioning"
    role["preferred_system"] = "aerobic"
    role["preferred_tags"] = ["aerobic", "rhythm", "timing", "breathing", "low_cns", "freshness"]
    role.pop("preferred_exercise_names", None)
    role["rpe_cap"] = "4-6"
    role["recovery_compatible"] = True
    role["counts_toward_conditioning_cap"] = False
    role["late_camp_role_morph"] = True
    role["selection_rule"] = _RHYTHM_TOUCH_SELECTION_RULE
    role["day_assignment_reason"] = (
        f"Late-camp morph: hard fight-pace conditioning softened to a rhythm "
        f"touch at D-{d_day}; the final hard pressure exposure lives at D-19/D-18."
    )
    _clear_hard_pressure_metadata(role)


def _soften_full_strength_role(role: dict[str, Any], d_day: int) -> None:
    cap = late_fight_strength_dose_cap(d_day) or {
        "rpe_cap": "6-7",
        "set_cap": "2-3 sets",
        "rep_cap": "2-3 reps",
        "max_sets": 3,
        "max_reps": 3,
        "movement_note": "familiar low-load strength retention only",
    }
    role.setdefault("original_training_intent", "meaningful_strength")
    role["rpe_cap"] = cap["rpe_cap"]
    role["set_cap"] = cap["set_cap"]
    role["rep_cap"] = cap["rep_cap"]
    role["strength_dose_cap"] = {"max_sets": cap["max_sets"], "max_reps": cap["max_reps"]}
    role["selection_rule"] = _strength_dose_selection_rule(cap)
    role["late_camp_strength_morph"] = True
    role["day_assignment_reason"] = (
        f"Late-camp morph: full strength-transfer softened to a "
        f"{cap['set_cap']} x {cap['rep_cap']} @ RPE {cap['rpe_cap']} "
        f"neural maintenance touch at D-{d_day}."
    )
    if d_day <= STRENGTH_LABEL_MORPH_MAX_D:
        role["athlete_facing_label"] = _NEURAL_TOUCH_LABEL


def _strength_intent_survives(role: dict[str, Any]) -> bool:
    cap = role.get("strength_dose_cap")
    if cap is None:
        return True
    try:
        return int(cap.get("max_sets", 0)) >= 2 and int(cap.get("max_reps", 0)) >= 1
    except (TypeError, ValueError):
        return False


def _hard_conditioning_intent_survives(role: dict[str, Any]) -> bool:
    if role.get("late_camp_role_morph") is True:
        return False
    if role.get("counts_toward_conditioning_cap") is False:
        return False
    system = str(role.get("preferred_system") or "").strip().lower()
    return system in {"glycolytic", "alactic", "atp-pcr", "atp_pcr"}


def _stamp_intent_validation(role: dict[str, Any], d_day: int | None, original_intent: str | None) -> None:
    if not original_intent:
        return
    if original_intent == "meaningful_strength":
        satisfied = _strength_intent_survives(role)
    elif original_intent == "hard_conditioning":
        satisfied = _hard_conditioning_intent_survives(role)
    else:
        return
    validation = {
        "intent": original_intent,
        "satisfied": satisfied,
        "scheduled_d_day": d_day,
        "authority": "post_morph_semantic_validation",
    }
    if not satisfied:
        validation["reason_code"] = "countdown_morph_reduced_original_intent"
        validation["reason"] = (
            "Countdown safety morph reduced this role below the dose/system that "
            "originally earned the slot. Treat the original intent as unsatisfied "
            "for downstream QA; do not claim it survived merely because the role remains visible."
        )
    role["intent_validation"] = validation


def _apply_late_camp_role_morph_once(
    weekly_role_map: dict[str, Any],
) -> dict[str, Any]:
    """Apply only the scheduled-day dose morph; no calendar repair."""
    if not isinstance(weekly_role_map, dict):
        return weekly_role_map

    summary = {"checked": 0, "satisfied": 0, "unsatisfied": 0, "unsatisfied_roles": []}

    for week in weekly_role_map.get("weeks", []) or []:
        if not isinstance(week, dict):
            continue
        for role in week.get("session_roles") or []:
            if not isinstance(role, dict):
                continue
            d_day = _role_d_day(week, role)
            role_key = str(role.get("role_key") or "").strip().lower()
            original_intent = None

            if role_key in FULL_STRENGTH_ROLE_KEYS:
                original_intent = "meaningful_strength"
                if d_day is not None and 0 <= d_day <= STRENGTH_NEURAL_MORPH_MAX_D:
                    _soften_full_strength_role(role, d_day)
            elif _is_hard_fight_pace_conditioning_role(role):
                original_intent = "hard_conditioning"
                if d_day is not None and 0 <= d_day <= FIGHT_PACE_MORPH_MAX_D:
                    _morph_to_rhythm_touch(role, d_day)

            _stamp_intent_validation(role, d_day, original_intent)
            validation = role.get("intent_validation")
            if isinstance(validation, dict):
                summary["checked"] += 1
                if validation.get("satisfied"):
                    summary["satisfied"] += 1
                else:
                    summary["unsatisfied"] += 1
                    summary["unsatisfied_roles"].append(
                        {
                            "role_key": role.get("role_key"),
                            "original_role_key": role.get("original_role_key"),
                            "intent": validation.get("intent"),
                            "scheduled_d_day": d_day,
                            "reason_code": validation.get("reason_code"),
                        }
                    )

    weekly_role_map["post_morph_intent_validation"] = summary
    return weekly_role_map


def apply_late_camp_role_morph(weekly_role_map: dict[str, Any]) -> dict[str, Any]:
    """Apply countdown dose, then enforce final deterministic calendar integrity."""
    _apply_late_camp_role_morph_once(weekly_role_map)

    # Local import keeps the ownership graph acyclic: calendar_integrity consumes
    # the shared load policy but never imports this module. If it moves a normal
    # role, it calls this module's *dose-only* core once more before verification.
    from .calendar_integrity import apply_final_calendar_integrity

    return apply_final_calendar_integrity(
        weekly_role_map,
        remorph_callback=_apply_late_camp_role_morph_once,
    )
