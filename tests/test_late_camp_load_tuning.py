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


# --- 1. D-17 and closer: strength touch is neural maintenance, not loaded ----

def test_strength_touch_at_d17_or_closer_is_neural_maintenance_only():
    spec = _build_late_fight_plan_spec(18, _athlete(18))
    softened = [
        entry
        for entry in spec["session_sequence"]
        if entry.get("role_key") == "strength_touch_day"
        and isinstance(entry.get("countdown_offset"), int)
        and entry["countdown_offset"] <= 17
    ]
    for entry in softened:
        assert entry["rpe_cap"] == "6-7"
        rule = entry["selection_rule"].lower()
        assert "neural maintenance" in rule
        assert "never render this as a loaded" in rule


def test_strength_touch_at_d18_or_further_keeps_meaningful_rule():
    spec = _build_late_fight_plan_spec(21, _athlete(21))
    for entry in spec["session_sequence"]:
        if entry.get("role_key") != "strength_touch_day":
            continue
        offset = entry.get("countdown_offset")
        if isinstance(offset, int) and offset >= 18:
            assert "neural maintenance" not in str(entry.get("selection_rule") or "").lower()


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
