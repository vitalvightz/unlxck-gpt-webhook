"""Late-camp conditioning role morph (deterministic overlay).

The D-14/D-13 late conditioning lock stops the combat-pressure floor from
*adding* new hard work, but a hard SPP glycolytic / fight-pace role that the
baseline planner scheduled can still survive at D-13 and closer, producing
sessions like "D-12 — Fight-pace conditioning, 4 x 3:00 @ RPE 8". That is too
hard too late: D-19/D-18 own the final real pressure exposure.

This module is a small deterministic overlay that runs after every role has a
scheduled D-day (after ``fill_missing_session_days`` and the camp-week fillers,
before labels are stamped). Rule:

    If a conditioning role is hard fight-pace / glycolytic and its scheduled
    D-day is D-13 or closer, morph it to a low-cost rhythm touch
    (``light_fight_pace_touch_day``) and clear its hard-pressure metadata.

    If a full strength role is scheduled at D-17 or closer, cap it to a
    low-volume neural maintenance touch (RPE 6-7, 2-3 sets); at D-12 or
    closer its athlete-facing label also stops rendering as "Strength".

The overlay only ever reduces prescribed load. It never touches:

* the D-21 → D-18 combat-pressure floor (its final hard exposure stays hard);
* low aerobic gas-tank support, warm-ups, and existing rhythm work;
* anything scheduled at D-14 or further out.

Because it runs last, no conditioning quota or protected-slot rule can preserve
hard glycolytic work at D-13 or closer.
"""

from __future__ import annotations

from typing import Any


# Hard fight-pace conditioning morphs to a rhythm touch from D-13 inward.
FIGHT_PACE_MORPH_MAX_D = 13
# Full strength-transfer softens to low-volume neural maintenance from D-17
# inward; from D-12 inward the "Strength" role label is also replaced so late
# camp never renders a full strength day.
STRENGTH_NEURAL_MORPH_MAX_D = 17
STRENGTH_LABEL_MORPH_MAX_D = 12
# D-21 → D-18 is the preserved combat-pressure floor; D-19/D-18 keep the final
# hard exposure. The morph window sits strictly inside D-13, so the floor is
# never touched by construction.
COMBAT_FLOOR_MIN_D = 18

# Hard, glycolytic fight-pace conditioning roles that carry real combat
# pressure. Lower-cost aerobic/alactic roles are already taper-appropriate.
HARD_FIGHT_PACE_ROLE_KEYS = frozenset(
    {
        "fight_pace_repeatability_day",
        "main_fight_pace_day",
        "highest_glycolytic_day",
        "controlled_repeatability_day",
    }
)

# Full strength roles that render the "Strength" label. strength_touch_day /
# small_strength_touch_day / neural_primer_day are already taper-sized.
FULL_STRENGTH_ROLE_KEYS = frozenset(
    {
        "primary_strength_day",
        "secondary_strength_day",
        "structural_strength_day",
        "transfer_strength_day",
        "neural_plus_strength_day",
    }
)

# Canonical low-cost morph target (already recognised by role_labels).
_RHYTHM_TOUCH_ROLE_KEY = "light_fight_pace_touch_day"
_RHYTHM_TOUCH_LABEL = "Rhythm flush"
_NEURAL_TOUCH_LABEL = "Neural speed touch"

_NEURAL_MAINTENANCE_SELECTION_RULE = (
    "Low-volume neural maintenance touch only: 2-3 crisp low-load sets at "
    "RPE 6-7 max with full recovery between sets. Keep bar/implement speed "
    "high and the dose tiny. No loaded strength-transfer session, no "
    "kettlebell swings, no loaded power cleans this close to the fight."
)

# Deterministic strength-lift dose caps by countdown day.
#
# The late-camp morph replaces a strength role's dose with these caps so the
# *lifting* dose (sets x reps x RPE), not just conditioning minutes, thins as
# the fight approaches. Caps apply from D-17 inward (STRENGTH_NEURAL_MORPH_MAX_D);
# D-18 and further out keep meaningful strength retention and are never capped.
#
# Each band is (min_d, max_sets, max_reps, rpe_cap, set_cap, rep_cap, dose_label,
# movement_note). Bands are ordered widest countdown -> closest to the fight so
# the first band whose min_d <= d wins.
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
    """Return the deterministic strength-lift dose cap for a role at ``d_day``.

    Returns ``None`` for D-18 and further out (meaningful strength is retained
    and never capped) and for values that are not a valid non-negative day.
    Otherwise returns a dict with ``max_sets`` / ``max_reps`` (numeric ceilings
    that decrease monotonically as the fight approaches), the human-readable
    ``rpe_cap`` / ``set_cap`` / ``rep_cap`` strings, a ``dose_label`` and a
    ``movement_note`` describing what is still allowed.
    """
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
    """Build the athlete-facing selection rule text from a dose cap."""
    return (
        f"Low-volume neural maintenance touch only: {cap['set_cap']} x "
        f"{cap['rep_cap']} at RPE {cap['rpe_cap']} max with full recovery. "
        f"{cap['movement_note'][0].upper()}{cap['movement_note'][1:]}. "
        "Never render this as a loaded strength-transfer session — keep bar/"
        "implement speed high and the dose tiny."
    )

# Role-level metadata that encodes "this is hard, meaningful combat pressure".
# Stripped on morph so nothing downstream re-reads a stale hard signal.
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
    d_day = _week_calendar_d_day(week, role.get("scheduled_day_hint"))
    if d_day is not None:
        return d_day
    # Fallback: countdown labels the role-map builder stamps directly.
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
    """Strip stale hard-pressure signals and stamp a low-cost governance state."""
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
    """Cap a full strength role to a countdown-graded low-volume neural touch."""
    cap = late_fight_strength_dose_cap(d_day) or {
        "rpe_cap": "6-7",
        "set_cap": "2-3 sets",
        "rep_cap": "2-3 reps",
        "max_sets": 3,
        "max_reps": 3,
        "movement_note": "familiar low-load strength retention only",
    }
    role["rpe_cap"] = cap["rpe_cap"]
    role["set_cap"] = cap["set_cap"]
    role["rep_cap"] = cap["rep_cap"]
    # Numeric ceilings so downstream/QA can assert the lifting dose actually
    # shrinks across the countdown (not just the prose).
    role["strength_dose_cap"] = {"max_sets": cap["max_sets"], "max_reps": cap["max_reps"]}
    role["selection_rule"] = _strength_dose_selection_rule(cap)
    role["late_camp_strength_morph"] = True
    role["day_assignment_reason"] = (
        f"Late-camp morph: full strength-transfer softened to a "
        f"{cap['set_cap']} x {cap['rep_cap']} @ RPE {cap['rpe_cap']} "
        f"neural maintenance touch at D-{d_day}."
    )
    if d_day <= STRENGTH_LABEL_MORPH_MAX_D:
        # D-12 and closer never render the "Strength" role label.
        role["athlete_facing_label"] = _NEURAL_TOUCH_LABEL


def apply_late_camp_role_morph(weekly_role_map: dict[str, Any]) -> dict[str, Any]:
    """Morph hard fight-pace conditioning at D-13 and closer to a rhythm touch.

    Mutates and returns the map. Safe to call on any ``weekly_role_map``: roles
    without a resolvable scheduled D-day, or scheduled at D-14 and further out,
    are left untouched.
    """
    if not isinstance(weekly_role_map, dict):
        return weekly_role_map
    for week in weekly_role_map.get("weeks", []) or []:
        if not isinstance(week, dict):
            continue
        for role in week.get("session_roles") or []:
            if not isinstance(role, dict):
                continue
            role_key = str(role.get("role_key") or "").strip().lower()
            if role_key in FULL_STRENGTH_ROLE_KEYS:
                d_day = _role_d_day(week, role)
                if d_day is not None and 0 <= d_day <= STRENGTH_NEURAL_MORPH_MAX_D:
                    _soften_full_strength_role(role, d_day)
                continue
            if not _is_hard_fight_pace_conditioning_role(role):
                continue
            d_day = _role_d_day(week, role)
            if d_day is None or not 0 <= d_day <= FIGHT_PACE_MORPH_MAX_D:
                continue
            _morph_to_rhythm_touch(role, d_day)
    return weekly_role_map
