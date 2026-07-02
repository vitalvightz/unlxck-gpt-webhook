"""Tests for the late-camp conditioning role morph overlay.

Hard fight-pace / glycolytic conditioning scheduled at D-13 or closer must
morph to a low-cost rhythm touch. D-19/D-18 own the final real pressure
exposure and stay hard. Low aerobic gas-tank support is never touched.
"""

from __future__ import annotations

import json

from fightcamp.late_camp_role_morph import apply_late_camp_role_morph
from fightcamp.stage2_payload import build_planning_brief


HARD_ROLE_KEYS = (
    "fight_pace_repeatability_day",
    "main_fight_pace_day",
    "highest_glycolytic_day",
    "controlled_repeatability_day",
)

HARD_PRESSURE_FIELDS = (
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
)


def _calendar(day_to_d):
    return [{"weekday": weekday, "d_day": d_day} for weekday, d_day in day_to_d.items()]


def _week(session_roles, *, calendar_days):
    return {"session_roles": session_roles, "calendar_days": calendar_days}


def _map(week):
    return {"weeks": [week]}


def _hard_role(role_key, weekday, **extra):
    role = {
        "role_key": role_key,
        "category": "conditioning",
        "preferred_system": "glycolytic",
        "scheduled_day_hint": weekday,
        "combat_pressure": True,
        "meaningful_stress": True,
        "mandatory_hard_conditioning_exposure": True,
        "prescribed_intensity_rpe": "8-9",
        "prescribed_dose": "4-6 x 2-3 min fight-pace on / 60 sec off @ RPE 8-9",
        "glycolytic_target": "high",
        "density_target": "high",
        "hard_pressure": True,
        "high_glycolytic": True,
        "combat_pressure_floor": True,
        "governance": {
            "meaningful_stress": True,
            "main_job": "conditioning",
            "support_cap": "light_only",
            "forbidden_secondary_stressors": ["hinge_transfer"],
            "hard_suppression_reasons": [],
        },
    }
    role.update(extra)
    return role


def _find(week, role_key):
    return [r for r in week["session_roles"] if r.get("role_key") == role_key]


# --- 1 & 2: D-19/D-18 final hard pressure exposure is preserved ---------------

def test_d19_fight_pace_role_remains_hard():
    week = _week(
        [_hard_role("fight_pace_repeatability_day", "monday")],
        calendar_days=_calendar({"monday": 19}),
    )
    apply_late_camp_role_morph(_map(week))
    role = _find(week, "fight_pace_repeatability_day")[0]
    assert role["preferred_system"] == "glycolytic"
    assert role["prescribed_intensity_rpe"] == "8-9"
    assert not _find(week, "light_fight_pace_touch_day")


def test_d18_fight_pace_role_remains_hard():
    week = _week(
        [_hard_role("fight_pace_repeatability_day", "tuesday")],
        calendar_days=_calendar({"tuesday": 18}),
    )
    apply_late_camp_role_morph(_map(week))
    role = _find(week, "fight_pace_repeatability_day")[0]
    assert role["preferred_system"] == "glycolytic"
    assert role["combat_pressure"] is True
    assert not _find(week, "light_fight_pace_touch_day")


def test_d14_fight_pace_role_is_not_morphed():
    week = _week(
        [_hard_role("main_fight_pace_day", "monday")],
        calendar_days=_calendar({"monday": 14}),
    )
    apply_late_camp_role_morph(_map(week))
    assert _find(week, "main_fight_pace_day")
    assert not _find(week, "light_fight_pace_touch_day")


# --- 3 & 4: D-13 and D-12 morph to rhythm touch -------------------------------

def test_d13_fight_pace_role_morphs_to_rhythm_touch():
    week = _week(
        [_hard_role("fight_pace_repeatability_day", "monday")],
        calendar_days=_calendar({"monday": 13}),
    )
    apply_late_camp_role_morph(_map(week))
    role = _find(week, "light_fight_pace_touch_day")[0]
    assert role["athlete_facing_label"] == "Rhythm flush"
    assert role["preferred_system"] == "aerobic"
    assert role["rpe_cap"] == "4-6"
    assert role["original_role_key"] == "fight_pace_repeatability_day"
    assert role["late_camp_role_morph"] is True


def test_d12_fight_pace_role_morphs_to_rhythm_touch():
    week = _week(
        [_hard_role("main_fight_pace_day", "wednesday")],
        calendar_days=_calendar({"wednesday": 12}),
    )
    apply_late_camp_role_morph(_map(week))
    role = _find(week, "light_fight_pace_touch_day")[0]
    assert role["preferred_system"] == "aerobic"
    assert role["original_role_key"] == "main_fight_pace_day"


def test_every_hard_role_key_morphs_inside_d13():
    for role_key in HARD_ROLE_KEYS:
        week = _week(
            [_hard_role(role_key, "monday")],
            calendar_days=_calendar({"monday": 11}),
        )
        apply_late_camp_role_morph(_map(week))
        assert _find(week, "light_fight_pace_touch_day"), role_key


def test_generic_glycolytic_conditioning_role_morphs_inside_d13():
    week = _week(
        [_hard_role("repeatability_support_day", "monday")],
        calendar_days=_calendar({"monday": 12}),
    )
    apply_late_camp_role_morph(_map(week))
    assert _find(week, "light_fight_pace_touch_day")


def test_countdown_label_fallback_resolves_d_day():
    role = _hard_role("fight_pace_repeatability_day", "")
    role["countdown_label"] = "D-12"
    week = _week([role], calendar_days=[])
    apply_late_camp_role_morph(_map(week))
    assert _find(week, "light_fight_pace_touch_day")


# --- 5: morphed role carries no hard-pressure metadata ------------------------

def test_morphed_role_has_no_hard_pressure_metadata():
    week = _week(
        [_hard_role("highest_glycolytic_day", "monday")],
        calendar_days=_calendar({"monday": 13}),
    )
    apply_late_camp_role_morph(_map(week))
    role = _find(week, "light_fight_pace_touch_day")[0]
    for field in HARD_PRESSURE_FIELDS:
        assert field not in role, field
    governance = role["governance"]
    assert governance["meaningful_stress"] is False
    assert "support_cap" not in governance
    assert "forbidden_secondary_stressors" not in governance
    assert not any(str(key).lower().startswith("hard") for key in governance)
    assert role["stress_class"] == "support"
    assert role["cost_class"] == "low"


# --- 6: no progression / hard-density wording ---------------------------------

def test_morphed_role_has_no_progression_wording():
    week = _week(
        [_hard_role("fight_pace_repeatability_day", "monday")],
        calendar_days=_calendar({"monday": 12}),
    )
    apply_late_camp_role_morph(_map(week))
    role = _find(week, "light_fight_pace_touch_day")[0]
    text = json.dumps(role).lower()
    for banned in ("progress", "overload", "rpe 8", "rpe 9", "add a round", "increase"):
        assert banned not in text, banned
    # The rhythm-touch focus is spelled out instead.
    rule = role["selection_rule"].lower()
    for term in ("rhythm", "timing", "breathing", "guard reset", "full recovery"):
        assert term in rule, term


# --- 7: quota / protected slots cannot preserve hard glycolytic inside D-13 ---

def test_protected_slot_flags_cannot_preserve_hard_glycolytic_at_d13():
    role = _hard_role(
        "fight_pace_repeatability_day",
        "monday",
        upgraded_from_combat_pressure_floor=True,
        declared_day_locked=True,
        must_keep=True,
    )
    role["governance"]["cannot_override"] = ["must_keep", "session_counts"]
    week = _week([role], calendar_days=_calendar({"monday": 13}))
    apply_late_camp_role_morph(_map(week))
    morphed = _find(week, "light_fight_pace_touch_day")
    assert morphed
    assert "upgraded_from_combat_pressure_floor" not in morphed[0]


# --- 8: low aerobic gas-tank support stays allowed -----------------------------

def test_low_aerobic_gas_tank_support_is_untouched_inside_d13():
    support = {
        "role_key": "aerobic_support_day",
        "category": "conditioning",
        "preferred_system": "aerobic",
        "scheduled_day_hint": "tuesday",
        "gas_tank_recovery_touch": True,
    }
    week = _week([dict(support)], calendar_days=_calendar({"tuesday": 12}))
    apply_late_camp_role_morph(_map(week))
    assert week["session_roles"][0] == support


def test_existing_rhythm_touch_is_left_alone():
    role = {
        "role_key": "light_fight_pace_touch_day",
        "category": "conditioning",
        "preferred_system": "aerobic",
        "scheduled_day_hint": "monday",
    }
    week = _week([dict(role)], calendar_days=_calendar({"monday": 10}))
    apply_late_camp_role_morph(_map(week))
    assert week["session_roles"][0] == role


def test_role_without_resolvable_d_day_is_a_noop():
    week = _week(
        [_hard_role("fight_pace_repeatability_day", "monday")],
        calendar_days=[],
    )
    apply_late_camp_role_morph(_map(week))
    assert _find(week, "fight_pace_repeatability_day")


# --- End-to-end: a normal camp brief never ships hard fight-pace inside D-13 --

def _normal_camp_brief():
    athlete_model = {
        "sport": "boxing",
        "status": "amateur",
        "rounds_format": "3x3",
        "camp_length_weeks": 6,
        "days_until_fight": 28,
        "short_notice": False,
        "fatigue": "low",
        "training_preference": "balanced",
        "training_days": ["monday", "tuesday", "wednesday", "thursday", "friday"],
        "key_goals": ["conditioning"],
        "weaknesses": ["gas_tank"],
        "equipment": ["bodyweight", "bands"],
        "injuries": [],
        "weight_cut_risk": False,
        "weight_cut_pct": 0.0,
        "readiness_flags": [],
    }
    phase_briefs = {
        "SPP": {
            "objective": "increase fight-specific repeatability and power transfer",
            "emphasize": ["sport speed", "fight-pace transfer"],
            "deprioritize": ["non-specific volume"],
            "risk_flags": [],
            "session_counts": {"strength": 1, "conditioning": 2, "recovery": 1},
            "selection_guardrails": {
                "must_keep_if_present": ["glycolytic"],
                "conditioning_drop_order_if_thin": ["aerobic"],
            },
            "weeks": 4,
            "days": 28,
        },
    }
    candidate_pools = {
        "SPP": {
            "strength_slots": [
                {
                    "role": "primary_strength",
                    "selected": {"name": "Trap Bar Deadlift"},
                    "alternates": [{"name": "Goblet Squat"}],
                }
            ],
            "conditioning_slots": [
                {
                    "role": "aerobic",
                    "selected": {"name": "Tempo Run"},
                    "alternates": [{"name": "Air Bike Flush"}],
                },
                {
                    "role": "glycolytic",
                    "selected": {"name": "Hard Shuttle"},
                    "alternates": [{"name": "Bag Sprint Round"}],
                },
            ],
            "rehab_slots": [],
        }
    }
    return build_planning_brief(
        athlete_model=athlete_model,
        restrictions=[],
        phase_briefs=phase_briefs,
        candidate_pools=candidate_pools,
        omission_ledger={},
        rewrite_guidance={},
    )


def test_normal_camp_brief_has_no_hard_fight_pace_inside_d13():
    brief = _normal_camp_brief()
    for week in brief["weekly_role_map"]["weeks"]:
        d_by_weekday = {
            str(day.get("weekday") or "").strip().lower(): day.get("d_day")
            for day in week.get("calendar_days") or []
            if isinstance(day, dict)
        }
        for role in week.get("session_roles") or []:
            weekday = str(role.get("scheduled_day_hint") or "").strip().lower()
            d_day = d_by_weekday.get(weekday)
            if not isinstance(d_day, int) or d_day > 13:
                continue
            assert role.get("role_key") not in HARD_ROLE_KEYS, (d_day, role.get("role_key"))
            if str(role.get("category") or "") == "conditioning":
                assert str(role.get("preferred_system") or "").lower() != "glycolytic", (
                    d_day,
                    role.get("role_key"),
                )
