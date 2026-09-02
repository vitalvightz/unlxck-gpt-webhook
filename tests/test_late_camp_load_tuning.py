"""Late-camp load tuning: sharp but safe.

Small deterministic caps that reduce late physical load without touching
coach combat day preservation, low-cost filler coexistence, surface-only
injury handling, or the D-21..D-18 final pressure exposure.
"""

from __future__ import annotations

from fightcamp import conditioning
from fightcamp.late_camp_role_morph import apply_late_camp_role_morph
from fightcamp.stage2_payload_late_fight import (
    _build_late_fight_plan_spec,
    _late_fight_countdown_exercise_rules,
    _late_fight_rendering_rules,
)
from fightcamp.stage2_validator import validate_stage2_output


def _athlete(days: int, **extra) -> dict:
    model = {
        "sport": "boxing",
        "days_until_fight": days,
        "plan_creation_weekday": "monday",
        "fatigue": "low",
        "readiness_flags": [],
        "training_days": ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday"],
        "hard_sparring_days": [],
    }
    model.update(extra)
    return model


# --- 1. D-17 and closer: strength softens to neural maintenance, not loaded ---
#
# D-14..D-21 now use the normal camp planner, so this progressive constraint is
# applied by the scheduled-day late-camp morph (keyed on the session's own D-day,
# not the plan's generation day), not by a separate bridge allocator.

def test_full_strength_role_at_d17_is_reduced_volume_strength_retention():
    # D-17..D-14 intentionally RETAIN meaningful (reduced-volume) strength; the
    # wording/metadata must stay truthful so the finalizer keeps real reduced
    # loading instead of collapsing the session to a neural-only touch.
    week = _strength_week("primary_strength_day", 17)
    apply_late_camp_role_morph({"weeks": [week]})
    role = week["session_roles"][0]
    assert role["rpe_cap"] == "6-7"
    rule = role["selection_rule"].lower()
    assert "strength retention" in rule
    assert "neural maintenance" not in rule
    assert "never render this as a loaded" not in rule
    assert role["strength_dose_cap"]["max_sets"] <= 3
    assert role["strength_dose_cap"]["loaded_allowed"] is True
    assert role["dose_adjustment_reason"] == "late_camp_strength_retention"
    # Semantic intent stays truthful: meaningful strength is preserved here.
    assert role["intent_validation"]["satisfied"] is True


def test_full_strength_role_at_d13_becomes_neural_maintenance():
    # Just inside the closer band the wording progressively becomes neural
    # maintenance / primer — loaded strength is still permitted here (D-8+),
    # but it is no longer framed as a strength-retention session.
    week = _strength_week("primary_strength_day", 13)
    apply_late_camp_role_morph({"weeks": [week]})
    role = week["session_roles"][0]
    rule = role["selection_rule"].lower()
    assert "neural maintenance" in rule
    assert "never render this as a loaded" in rule


def test_full_strength_role_at_d18_or_further_keeps_meaningful():
    # D-18 and further out: meaningful strength is retained — the morph must not
    # cap it or relabel it as a neural touch. This is the D-18 side of the old
    # D-22 -> D-21 cliff, now smooth and generation-day-independent.
    week = _strength_week("primary_strength_day", 18)
    apply_late_camp_role_morph({"weeks": [week]})
    role = week["session_roles"][0]
    assert role["role_key"] == "primary_strength_day"
    assert "strength_dose_cap" not in role
    assert role.get("late_camp_strength_morph") is not True
    assert "neural maintenance" not in str(role.get("selection_rule") or "").lower()


# --- 2. Weekly-map strength roles soften and lose the "Strength" label -------

def _strength_week(role_key: str, d_day: int) -> dict:
    return {
        "session_roles": [
            {
                "role_key": role_key,
                "category": "strength",
                "scheduled_day_hint": "monday",
            }
        ],
        "calendar_days": [{"weekday": "monday", "d_day": d_day}],
    }


def test_full_strength_role_at_d12_loses_strength_label():
    week = _strength_week("transfer_strength_day", 12)
    apply_late_camp_role_morph({"weeks": [week]})
    role = week["session_roles"][0]
    assert role["athlete_facing_label"] == "Neural speed touch"
    assert role["rpe_cap"] == "6-7"
    assert "neural maintenance" in role["selection_rule"].lower()


def test_full_strength_role_at_d6_loses_strength_label():
    week = _strength_week("neural_plus_strength_day", 6)
    apply_late_camp_role_morph({"weeks": [week]})
    role = week["session_roles"][0]
    assert role["athlete_facing_label"] == "Neural speed touch"


def test_full_strength_role_at_d15_softens_dose_but_keeps_label():
    week = _strength_week("transfer_strength_day", 15)
    apply_late_camp_role_morph({"weeks": [week]})
    role = week["session_roles"][0]
    assert role["rpe_cap"] == "6-7"
    assert "athlete_facing_label" not in role


def test_full_strength_role_at_d18_is_untouched():
    week = _strength_week("transfer_strength_day", 18)
    apply_late_camp_role_morph({"weeks": [week]})
    role = week["session_roles"][0]
    assert "rpe_cap" not in role
    assert "late_camp_strength_morph" not in role


# --- 3. D-6 and closer: no kettlebell swings / loaded power cleans -----------

def test_d6_kettlebell_swing_is_blocked_by_validator():
    spec = _build_late_fight_plan_spec(6, _athlete(6))
    report = validate_stage2_output(
        planning_brief={"late_fight_plan_spec": spec},
        final_plan_text="""
        D-6 (Monday) — Neural speed touch
        - Kettlebell Swings — 3 x 8
        """,
    )
    codes = {warning["code"] for warning in report["warnings"]}
    assert "late_fight_countdown_blocked_drill" in codes, codes


def test_d6_countdown_rules_block_kettlebell_and_power_clean():
    rules = {rule["countdown_label"]: rule for rule in _late_fight_countdown_exercise_rules(6)}
    blocked = [drill.lower() for drill in rules["D-6"]["blocked_drills"]]
    assert "kettlebell" in blocked
    assert "power clean" in blocked


# --- 4. D-10 neural speed volume is capped lower ------------------------------

def test_d10_conditioning_caps_limit_bursts():
    caps = conditioning._late_fight_dosage_caps(10)
    assert "3-4 max (5-6 sec @ RPE 6-7" in caps
    assert "optional only, never required" in caps


def test_d10_rendering_rules_cap_neural_speed():
    rules = _late_fight_rendering_rules(10)
    assert any("3-4 x 5-6 sec" in rule and "RPE 6-7" in rule for rule in rules["rules"])


# --- 5. D-3 med-ball is never required ----------------------------------------

def test_d3_countdown_rules_block_med_ball():
    rules = {rule["countdown_label"]: rule for rule in _late_fight_countdown_exercise_rules(3)}
    blocked = [drill.lower() for drill in rules["D-3"]["blocked_drills"]]
    assert "medicine ball" in blocked
    assert "chest pass" in blocked
    preferred = " ".join(rules["D-3"]["preferred_drills"]).lower()
    assert "shadowboxing" in preferred


def test_d3_med_ball_chest_pass_is_blocked_by_validator():
    spec = _build_late_fight_plan_spec(3, _athlete(3))
    report = validate_stage2_output(
        planning_brief={"late_fight_plan_spec": spec},
        final_plan_text="""
        D-3 (Thursday) — Freshness reset
        - Medicine Ball Chest Pass — 3 x 5
        """,
    )
    codes = {warning["code"] for warning in report["warnings"]}
    assert "late_fight_countdown_blocked_drill" in codes, codes


# --- 6. D-1 stays a tiny readiness touch --------------------------------------

def test_d1_shadowboxing_cap_present_in_rules():
    rules = _late_fight_rendering_rules(1)
    assert any("2 x 60-90 sec" in rule for rule in rules["rules"])


def test_d1_micro_dose_cap_unchanged():
    rules = _late_fight_rendering_rules(1)
    assert any("RPE 3-5" in rule for rule in rules["rules"])
    assert "RPE 6-7" in rules["forbidden_terms"]
