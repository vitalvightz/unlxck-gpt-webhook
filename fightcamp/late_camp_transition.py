"""Normal-camp late-transition (taper morph) overlay.

A *normal* fight camp (plan created more than 21 days out, so it never enters the
short-notice late-fight template) still runs its final ~3 weeks straight through
the D-21 → D-0 window. Without an overlay those final weeks keep prescribing the
same hard fight-pace conditioning and hard sparring the camp used mid-block, so
the athlete walks into fight week carrying combat pressure instead of freshness.

This module is a light, deterministic overlay that morphs those final weeks into
a taper *without* hard-switching into ``stage2_payload_late_fight``. It runs on
the already-built ``weekly_role_map`` (after ``fill_missing_session_days`` has
placed every role on a real day, before labels are stamped) and:

* preserves the D-21 → D-18 combat-pressure floor untouched;
* morphs hard fight-pace conditioning at D-13 and closer into a low-cost
  rhythm / freshness touch, clearing the stale hard-pressure metadata;
* downgrades hard sparring at D-17 and closer into technical-only combat with
  no extra S&C stacked on it;
* keeps a single low-cost rhythm touch visible on an otherwise-unused taper day,
  but never under active safety pressure (fatigue, weight cut, active injury, a
  compressed week) and never by refilling a day left unused for a safety reason.

The overlay only ever *reduces* prescribed load, so the morph itself always runs;
only the optional taper-day rhythm touch is gated behind the safety checks above.
"""

from __future__ import annotations

from typing import Any

from .gap_fill_inserts import (
    _has_active_weight_cut,
    classify_injury_state,
)
from .normalization import clean_list, normalize_fatigue_level


# --- Taper window boundaries (countdown days) --------------------------------
# D-21 → D-18 is the preserved combat-pressure floor: nothing morphs here.
FLOOR_MAX_D = 21
FLOOR_MIN_D = 18
# Hard sparring softens to technical-only from D-17 inward.
HARD_SPARRING_MORPH_D = 17
# Hard fight-pace conditioning softens to a rhythm touch from D-13 inward.
FIGHT_PACE_MORPH_D = 13
# Never place app support work on the day before / of the fight.
MIN_INSERT_D = 2


# Hard, glycolytic fight-pace conditioning roles that carry real combat pressure.
# Lower-cost aerobic/alactic sharpness roles are intentionally excluded — they are
# already taper-appropriate and stay as-is.
_HARD_FIGHT_PACE_ROLE_KEYS = frozenset(
    {
        "fight_pace_repeatability_day",
        "main_fight_pace_day",
        "highest_glycolytic_day",
        "controlled_repeatability_day",
    }
)

_HARD_SPARRING_ROLE_KEY = "hard_sparring_day"

# Canonical low-cost morph targets (both already recognised by role_labels).
_RHYTHM_TOUCH_ROLE_KEY = "light_fight_pace_touch_day"  # "Rhythm flush"
_RHYTHM_TOUCH_LABEL = "Rhythm flush"
_LIGHT_COMBAT_ROLE_KEY = "light_combat_day"  # "Light technical combat"
_LIGHT_COMBAT_LABEL = "Light technical combat"

# Role-level metadata that encodes "this is hard, meaningful combat pressure".
# These are stripped when a role is morphed into a low-cost touch so nothing
# downstream re-reads a stale hard-pressure signal off the softened role.
_HARD_PRESSURE_ROLE_FIELDS = (
    "meaningful_stress",
    "combat_pressure",
    "hard_pressure",
    "high_glycolytic",
    "glycolytic_target",
    "density_target",
    "hard_sparring_status",
    "hard_sparring_class",
    "hard_sparring_reason_codes",
    "hard_sparring_reason",
)

# Markers that block refilling an intentionally-unused day, or block any extra
# taper-day inserts, because the day/week is protecting the athlete.
_SAFETY_REASON_MARKERS = (
    "injur",
    "fatigue",
    "weight cut",
    "weight_cut",
    "cut_stress",
    "compress",
    "spar",
    "safety",
    "medical",
    "red_flag",
    "red flag",
    "deload",
)


def _week_calendar_d_day(week: dict[str, Any], weekday: str) -> int | None:
    """Resolve the countdown day for a weekday from the week's calendar spine."""
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
    return _week_calendar_d_day(week, role.get("scheduled_day_hint"))


def _in_taper_window(d_day: int | None) -> bool:
    return d_day is not None and 0 <= d_day <= FLOOR_MAX_D


def _in_combat_pressure_floor(d_day: int | None) -> bool:
    return d_day is not None and FLOOR_MIN_D <= d_day <= FLOOR_MAX_D


def _clear_hard_pressure_metadata(role: dict[str, Any], *, main_job: str) -> None:
    """Strip stale hard-pressure signals and stamp a low-cost governance state."""
    for field in _HARD_PRESSURE_ROLE_FIELDS:
        role.pop(field, None)
    role["stress_class"] = "support"
    role["cost_class"] = "low"

    governance = dict(role.get("governance") or {})
    for field in ("support_cap", "forbidden_secondary_stressors"):
        governance.pop(field, None)
    for key in list(governance.keys()):
        if str(key).lower().startswith("hard"):
            governance.pop(key, None)
    governance["meaningful_stress"] = False
    governance["main_job"] = main_job
    governance["authority"] = "late_camp_transition"
    role["governance"] = governance


def _morph_fight_pace_to_rhythm(role: dict[str, Any], d_day: int) -> None:
    original = str(role.get("role_key") or "")
    role["original_role_key"] = original
    role["role_key"] = _RHYTHM_TOUCH_ROLE_KEY
    role["athlete_facing_label"] = _RHYTHM_TOUCH_LABEL
    role["category"] = "conditioning"
    role["preferred_system"] = "aerobic"
    role["preferred_tags"] = ["aerobic", "low_impact", "low_cns", "rhythm", "freshness"]
    role["preferred_exercise_names"] = []
    role["recovery_compatible"] = True
    role["counts_toward_conditioning_cap"] = False
    role["late_camp_transition"] = True
    role["day_assignment_reason"] = (
        f"Late-camp taper morph: hard fight-pace conditioning softened to a "
        f"low-cost rhythm/freshness touch at D-{d_day}."
    )
    role["selection_rule"] = (
        "Low-cost rhythm/freshness only: RPE <= 4, low impact, low CNS. "
        "Do not turn this into hard fight-pace or glycolytic density work."
    )
    _clear_hard_pressure_metadata(role, main_job="conditioning")


def _morph_hard_sparring_to_technical(role: dict[str, Any], d_day: int) -> None:
    original = str(role.get("role_key") or "")
    role["original_role_key"] = original
    role["role_key"] = _LIGHT_COMBAT_ROLE_KEY
    role["athlete_facing_label"] = _LIGHT_COMBAT_LABEL
    role["technical_only"] = True
    role["no_extra_sc"] = True
    role["late_camp_transition"] = True
    role["day_assignment_reason"] = (
        f"Late-camp taper morph: hard sparring softened to technical-only "
        f"combat with no extra S&C at D-{d_day}."
    )
    role["selection_rule"] = (
        "Technical-only light combat: controlled touch sparring or drilling. "
        "No hard rounds, no extra strength & conditioning stacked on the day."
    )
    _clear_hard_pressure_metadata(role, main_job="technical")


def _morph_week_roles(week: dict[str, Any]) -> None:
    for role in week.get("session_roles") or []:
        if not isinstance(role, dict):
            continue
        d_day = _role_d_day(week, role)
        if not _in_taper_window(d_day):
            continue
        # Preserve the D-21 → D-18 combat-pressure floor untouched.
        if _in_combat_pressure_floor(d_day):
            continue
        role_key = str(role.get("role_key") or "")
        if role_key == _HARD_SPARRING_ROLE_KEY and d_day <= HARD_SPARRING_MORPH_D:
            _morph_hard_sparring_to_technical(role, d_day)
        elif role_key in _HARD_FIGHT_PACE_ROLE_KEYS and d_day <= FIGHT_PACE_MORPH_D:
            _morph_fight_pace_to_rhythm(role, d_day)


# --- Optional taper-day rhythm touch (safety-gated) --------------------------
def _text_has_safety_marker(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in _SAFETY_REASON_MARKERS)


def _week_is_compressed(week: dict[str, Any], athlete_model: dict[str, Any]) -> bool:
    ic = week.get("intentional_compression")
    if ic and (ic.get("active") if isinstance(ic, dict) else ic):
        return True
    flags_text = " ".join(str(flag) for flag in clean_list(week.get("coach_note_flags")))
    if "compress" in flags_text.lower():
        return True
    for day_entry in week.get("intentionally_unused_days") or []:
        if not isinstance(day_entry, dict):
            continue
        if day_entry.get("compression_reason_codes") or day_entry.get("intentional_compression"):
            return True
    readiness = " ".join(str(flag) for flag in clean_list(athlete_model.get("readiness_flags")))
    return "compress" in readiness.lower()


def _extra_inserts_allowed(week: dict[str, Any], athlete_model: dict[str, Any]) -> bool:
    """No extra taper-day work under any active safety pressure."""
    if normalize_fatigue_level(athlete_model) in {"moderate", "high"}:
        return False
    if _has_active_weight_cut(athlete_model):
        return False
    if classify_injury_state(athlete_model) == "moderate_plus":
        return False
    if _week_is_compressed(week, athlete_model):
        return False
    return True


def _unused_day_is_safety_blocked(day_entry: dict[str, Any]) -> bool:
    for key, value in day_entry.items():
        key_lower = str(key).lower()
        if key_lower in {"day"}:
            continue
        if "reason" in key_lower or key_lower == "role":
            if _text_has_safety_marker(str(value) if not isinstance(value, (list, tuple)) else " ".join(map(str, value))):
                return True
    return False


def _build_rhythm_touch_insert(day: str, unused_role: str, d_day: int) -> dict[str, Any]:
    return {
        "session_index": 0,
        "category": "conditioning",
        "role_key": _RHYTHM_TOUCH_ROLE_KEY,
        "athlete_facing_label": _RHYTHM_TOUCH_LABEL,
        "preferred_pool": "conditioning_slots",
        "preferred_system": "aerobic",
        "preferred_tags": ["aerobic", "low_impact", "low_cns", "rhythm", "freshness"],
        "scheduled_day_hint": day,
        "selection_rule": (
            "Low-cost rhythm/freshness only: RPE <= 4, low impact, low CNS. "
            "Keep the taper ticking over without costing freshness."
        ),
        "day_assignment_reason": (
            f"Late-camp taper: unused day kept as a low-cost rhythm/freshness "
            f"touch at D-{d_day}."
        ),
        "recovery_compatible": True,
        "counts_toward_conditioning_cap": False,
        "converted_from_unused_day": True,
        "original_unused_day_role": unused_role,
        "stress_class": "support",
        "cost_class": "low",
        "late_camp_transition": True,
        "governance": {
            "authority": "late_camp_transition_rhythm_touch",
            "meaningful_stress": False,
            "main_job": "conditioning",
        },
    }


def _refill_unused_taper_days(week: dict[str, Any], athlete_model: dict[str, Any]) -> None:
    unused_days = week.get("intentionally_unused_days")
    if not isinstance(unused_days, list) or not unused_days:
        return
    if not _extra_inserts_allowed(week, athlete_model):
        return

    session_roles = week.get("session_roles")
    if not isinstance(session_roles, list):
        return
    existing_days = {
        str(role.get("scheduled_day_hint") or "").strip().lower()
        for role in session_roles
        if isinstance(role, dict) and str(role.get("scheduled_day_hint") or "").strip()
    }

    kept_unused: list[Any] = []
    added = False
    for day_entry in unused_days:
        if added or not isinstance(day_entry, dict):
            kept_unused.append(day_entry)
            continue
        day = str(day_entry.get("day") or "").strip()
        unused_role = str(day_entry.get("role") or "").strip()
        d_day = _week_calendar_d_day(week, day)
        eligible = (
            bool(day)
            and day.lower() not in existing_days
            and unused_role in {"off_day", "recovery_only_day"}
            and d_day is not None
            and MIN_INSERT_D <= d_day <= FIGHT_PACE_MORPH_D
            and not _unused_day_is_safety_blocked(day_entry)
        )
        if not eligible:
            kept_unused.append(day_entry)
            continue
        session_roles.append(_build_rhythm_touch_insert(day, unused_role, d_day))
        existing_days.add(day.lower())
        added = True

    if added:
        week["intentionally_unused_days"] = kept_unused


def apply_late_camp_transition(
    weekly_role_map: dict[str, Any],
    athlete_model: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Morph a normal camp's final weeks into a taper. Mutates and returns the map.

    Safe to call on any ``weekly_role_map``: roles outside the D-21 → D-0 taper
    window (or without a resolvable calendar day) are left untouched, so a map
    with no late-window roles is a no-op.
    """
    if not isinstance(weekly_role_map, dict):
        return weekly_role_map
    athlete_model = athlete_model or {}
    for week in weekly_role_map.get("weeks", []) or []:
        if not isinstance(week, dict):
            continue
        _morph_week_roles(week)
        _refill_unused_taper_days(week, athlete_model)
    return weekly_role_map
