"""End-to-end coverage for late-camp effective-prescription resolution.

These exercise the real production wiring — the scheduled-day morph, the
deterministic prescription resolver, the finalizer-packet compaction, and the
Stage 2 validator — rather than the resolver unit surface alone. The countdown
band is a ceiling: the same D-day always resolves to the same-or-lower dose as
readiness/cut state worsens, never higher.
"""

from __future__ import annotations

from fightcamp.late_camp_role_morph import apply_late_camp_role_morph
from fightcamp.prescription_resolver import apply_effective_strength_prescriptions
from fightcamp.stage2_finalizer_packet import build_stage2_finalizer_packet
from fightcamp.stage2_validator import validate_stage2_output


# --------------------------------------------------------------------------- #
# Builders
# --------------------------------------------------------------------------- #

def _strength_slot(
    name: str,
    prescription: str,
    *,
    quality_class: str,
    anchor_capable: bool,
    movement: str,
    priority: int,
) -> dict:
    support_only = quality_class in {"support_isometric", "support_accessory", "rehab_support"}
    return {
        "slot_id": f"spp_strength_{priority}_{name.lower().replace(' ', '_')}",
        "role": movement,
        "priority": priority,
        "session_index": 1,
        "quality_class": quality_class,
        "anchor_capable": anchor_capable,
        "support_only": support_only,
        "selected": {
            "name": name,
            "prescription": prescription,
            "quality_class": quality_class,
            "anchor_capable": anchor_capable,
        },
    }


def _anchor_slot(name="Trap Bar Deadlift", presc="4 x 3 @ RPE 7", priority=1):
    return _strength_slot(name, presc, quality_class="anchor_loaded", anchor_capable=True, movement="hinge", priority=priority)


def _secondary_slot(name="Barbell Overhead Press", presc="3 x 6", priority=2):
    return _strength_slot(name, presc, quality_class="anchor_loaded", anchor_capable=True, movement="press", priority=priority)


def _support_slot(name="Pallof Press", presc="3 x 8", priority=3):
    return _strength_slot(name, presc, quality_class="support_isometric", anchor_capable=False, movement="anti_rotation", priority=priority)


def _power_slot(name="Broad Jump", presc="5 x 3", priority=4):
    return _strength_slot(name, presc, quality_class="anchor_power", anchor_capable=True, movement="jump", priority=priority)


def _resolve(d_day: int, slots: list[dict], *, weekday="tuesday", phase="SPP", athlete_model=None):
    """Run the real morph + resolver for one strength role at ``d_day``."""
    weekly_role_map = {
        "weeks": [
            {
                "phase": phase,
                "week_index": 3,
                "calendar_days": [{"weekday": weekday, "d_day": d_day}],
                "session_roles": [
                    {
                        "role_key": "primary_strength_day",
                        "category": "strength",
                        "scheduled_day_hint": weekday,
                    }
                ],
            }
        ]
    }
    candidate_pools = {phase: {"strength_slots": slots}}
    apply_late_camp_role_morph(weekly_role_map)
    apply_effective_strength_prescriptions(
        weekly_role_map=weekly_role_map,
        candidate_pools=candidate_pools,
        athlete_model=athlete_model or {"fatigue": "low", "weight_cut_pct": 0.0},
    )
    return weekly_role_map["weeks"][0]["session_roles"][0]


def _by_name(role: dict, name: str) -> dict:
    for item in role.get("effective_strength_prescriptions") or []:
        if item.get("name") == name:
            return item
    raise AssertionError(f"{name} not in resolved prescriptions: {role.get('effective_strength_prescriptions')}")


# --------------------------------------------------------------------------- #
# A. D-18 anchor — uncapped by the late-camp strength layer
# --------------------------------------------------------------------------- #

def test_case_a_d18_anchor_remains_uncapped():
    role = _resolve(18, [_anchor_slot()])
    # The morph never touches D-18+, so no dose cap and no resolver overlay: the
    # exercise-bank dose stays authoritative and meaningful.
    assert "strength_dose_cap" not in role
    assert "effective_strength_prescriptions" not in role
    assert "effective_strength_envelope" not in role
    assert role.get("late_camp_strength_morph") is not True


# --------------------------------------------------------------------------- #
# B. D-17 anchor — reduced to a valid strength-retention dose, authoritative
# --------------------------------------------------------------------------- #

def test_case_b_d17_anchor_effective_dose_is_authoritative():
    role = _resolve(17, [_anchor_slot()])
    anchor = _by_name(role, "Trap Bar Deadlift")
    assert anchor["base_prescription"] == "4 x 3 @ RPE 7"
    assert anchor["effective_prescription"] == "3 x 3 @ RPE 6-7 max"
    assert anchor["dose_authority"] == "scheduled_countdown_overlay"
    assert anchor["dose_role_kind"] == "anchor"
    assert anchor["effective_loaded"] is True
    assert anchor["dose_adjustment_reason"] == "late_camp_strength_retention"
    # Meaningful strength still satisfied at D-17.
    assert role["intent_validation"]["satisfied"] is True


def test_case_b_d17_effective_reaches_stage2_packet_and_base_not_authoritative():
    role_map = {
        "weeks": [
            {
                "phase": "SPP",
                "week_index": 3,
                "calendar_days": [{"weekday": "tuesday", "d_day": 17}],
                "session_roles": [
                    {"role_key": "primary_strength_day", "category": "strength", "scheduled_day_hint": "tuesday"}
                ],
            }
        ]
    }
    apply_late_camp_role_morph(role_map)
    apply_effective_strength_prescriptions(
        weekly_role_map=role_map,
        candidate_pools={"SPP": {"strength_slots": [_anchor_slot()]}},
        athlete_model={"fatigue": "low"},
    )
    packet = build_stage2_finalizer_packet(
        stage2_payload={"weekly_role_map": role_map},
        planning_brief={"weekly_role_map": role_map, "athlete_snapshot": {"fatigue": "low"}},
    )
    compact_role = packet["selected_plan"]["weekly_role_map"]["weeks"][0]["session_roles"][0]
    presc = compact_role["effective_strength_prescriptions"][0]
    assert presc["effective_prescription"] == "3 x 3 @ RPE 6-7 max"
    # base is preserved for provenance but is NOT the authoritative render dose.
    assert presc["base_prescription"] == "4 x 3 @ RPE 7"
    assert compact_role["effective_strength_envelope"]["max_sets"] == 3
    rules = " ".join(packet["hard_rules"])
    assert "effective_prescription is the authoritative dose" in rules
    assert "never the base_prescription" in rules


# --------------------------------------------------------------------------- #
# C. D-17 secondary loses more volume than the anchor
# --------------------------------------------------------------------------- #

def test_case_c_d17_secondary_loses_more_volume_than_anchor():
    role = _resolve(17, [_anchor_slot(), _secondary_slot()])
    anchor = _by_name(role, "Trap Bar Deadlift")
    secondary = _by_name(role, "Barbell Overhead Press")
    assert anchor["dose_role_kind"] == "anchor"
    assert secondary["dose_role_kind"] == "secondary"
    assert secondary["effective_prescription"] == "2 x 5 @ RPE 6-7 max"
    # Secondary loses a set relative to the anchor.
    assert secondary["effective_max_sets"] < anchor["effective_max_sets"]


# --------------------------------------------------------------------------- #
# D. D-17 support reduces volume but is NOT forced into low-rep strength work
# --------------------------------------------------------------------------- #

def test_case_d_d17_support_reduces_sets_keeps_reps():
    role = _resolve(17, [_anchor_slot(), _support_slot()])
    support = _by_name(role, "Pallof Press")
    assert support["dose_role_kind"] == "support"
    assert support["effective_prescription"] == "2 x 8 @ RPE 6-7 max"
    # Reps stay at 8 — never squeezed into a 2-3 rep strength prescription.
    assert support["effective_max_reps"] == 8
    assert support["effective_loaded"] is False


# --------------------------------------------------------------------------- #
# E. D-10 full strength → neural maintenance behaviour
# --------------------------------------------------------------------------- #

def test_case_e_d10_full_strength_is_neural_maintenance():
    role = _resolve(10, [_anchor_slot()])
    anchor = _by_name(role, "Trap Bar Deadlift")
    # Band caps to 2 x 3; loaded work is still permitted this far out.
    assert anchor["effective_prescription"] == "2 x 3 @ RPE 6-7 max"
    assert anchor["effective_loaded"] is True
    assert anchor["dose_adjustment_reason"] == "late_camp_reduced_strength_maintenance"
    assert "neural maintenance" in role["selection_rule"].lower()


# --------------------------------------------------------------------------- #
# F. D-7 → primer / microdose (no loaded strength)
# --------------------------------------------------------------------------- #

def test_case_f_d7_anchor_becomes_no_loaded_lifting():
    role = _resolve(7, [_anchor_slot()])
    anchor = _by_name(role, "Trap Bar Deadlift")
    assert anchor["effective_loaded"] is False
    assert "no loaded lifting" in anchor["effective_prescription"].lower()
    assert anchor["dose_adjustment_reason"] == "late_camp_neural_microdose"
    # Loaded strength intent no longer survives this close to the fight.
    assert role["strength_dose_cap"]["loaded_allowed"] is False
    assert role["intent_validation"]["satisfied"] is False
    assert role["effective_strength_envelope"]["loaded_allowed"] is False


# --------------------------------------------------------------------------- #
# G. D-3 → tiny activation / no loaded strength
# --------------------------------------------------------------------------- #

def test_case_g_d3_no_loaded_strength_power_is_tiny():
    role = _resolve(3, [_anchor_slot(), _power_slot()])
    anchor = _by_name(role, "Trap Bar Deadlift")
    power = _by_name(role, "Broad Jump")
    # Loaded anchor is suppressed entirely.
    assert anchor["effective_loaded"] is False
    assert "no loaded lifting" in anchor["effective_prescription"].lower()
    # Neural/power keeps its own quality but is trimmed to a tiny single-set dose.
    assert power["dose_role_kind"] == "power"
    assert power["effective_max_sets"] == 1


# --------------------------------------------------------------------------- #
# H. Athlete state may only reduce the dose further, never raise it
# --------------------------------------------------------------------------- #

def test_case_h_high_risk_state_never_raises_dose():
    low_risk = _resolve(17, [_anchor_slot()], athlete_model={"fatigue": "low", "weight_cut_pct": 0.0})
    high_fatigue = _resolve(17, [_anchor_slot()], athlete_model={"fatigue": "high", "weight_cut_pct": 0.0})
    aggressive_cut = _resolve(
        17,
        [_anchor_slot()],
        athlete_model={"fatigue": "low", "weight_cut_pct": 6.0, "readiness_flags": ["aggressive_weight_cut"]},
    )
    low_sets = _by_name(low_risk, "Trap Bar Deadlift")["effective_max_sets"]
    fatigue_sets = _by_name(high_fatigue, "Trap Bar Deadlift")["effective_max_sets"]
    cut_sets = _by_name(aggressive_cut, "Trap Bar Deadlift")["effective_max_sets"]
    assert fatigue_sets <= low_sets
    assert cut_sets <= low_sets
    # A worsened profile reduces (here 3 -> 2) but never floors below a single set.
    assert fatigue_sets == 2
    assert cut_sets >= 1


def test_case_h_moderate_cut_does_not_reduce_below_countdown_band():
    # The K profile's ~3.4% cut is not aggressive, so it must not shave the dose.
    role = _resolve(17, [_anchor_slot()], athlete_model={"fatigue": "low", "weight_cut_pct": 3.4})
    assert _by_name(role, "Trap Bar Deadlift")["effective_prescription"] == "3 x 3 @ RPE 6-7 max"


# --------------------------------------------------------------------------- #
# I / J. Validator enforcement against the effective envelope
# --------------------------------------------------------------------------- #

def _brief_with_envelope(d_day: int, envelope: dict, weekday="tuesday") -> dict:
    return {
        "weekly_role_map": {
            "weeks": [
                {
                    "phase": "SPP",
                    "calendar_days": [{"weekday": weekday, "d_day": d_day}],
                    "session_roles": [
                        {
                            "role_key": "primary_strength_day",
                            "category": "strength",
                            "scheduled_day_hint": weekday,
                            "effective_strength_envelope": envelope,
                        }
                    ],
                }
            ]
        }
    }


_D17_ENVELOPE = {
    "scheduled_d_day": 17,
    "loaded_allowed": True,
    "max_sets": 3,
    "max_reps": 3,
    "rpe_cap_high": 7,
    "loaded_exercise_names": ["Trap Bar Deadlift"],
    "dose_adjustment_reason": "late_camp_strength_retention",
}


def test_case_i_validator_flags_dose_above_effective():
    brief = _brief_with_envelope(17, _D17_ENVELOPE)
    report = validate_stage2_output(
        planning_brief=brief,
        final_plan_text="D-17 (Tuesday) — Strength\n- Trap Bar Deadlift — 4 x 3 @ RPE 7\n",
    )
    codes = {e["code"] for e in report["errors"]}
    assert "late_camp_effective_prescription_exceeded" in codes
    assert report["is_valid"] is False


def test_case_i_validator_passes_correct_effective_dose():
    brief = _brief_with_envelope(17, _D17_ENVELOPE)
    report = validate_stage2_output(
        planning_brief=brief,
        final_plan_text="D-17 (Tuesday) — Strength\n- Trap Bar Deadlift — 3 x 3 @ RPE 6-7\n",
    )
    codes = {e["code"] for e in report["errors"]}
    assert "late_camp_effective_prescription_exceeded" not in codes


def test_case_j_validator_flags_loaded_lifting_when_none_allowed():
    envelope = {
        "scheduled_d_day": 5,
        "loaded_allowed": False,
        "rpe_cap_high": 6,
        "loaded_exercise_names": ["Trap Bar Deadlift"],
        "dose_adjustment_reason": "late_camp_neural_power_microdose",
    }
    brief = _brief_with_envelope(5, envelope, weekday="friday")
    report = validate_stage2_output(
        planning_brief=brief,
        final_plan_text="D-5 (Friday) — Primer\n- Trap Bar Deadlift — 2 x 2\n",
    )
    codes = {e["code"] for e in report["errors"]}
    assert "late_camp_effective_prescription_exceeded" in codes
    assert report["is_valid"] is False


# --------------------------------------------------------------------------- #
# K. Production-like regression: the D-17 geometry that exposed the bug
# --------------------------------------------------------------------------- #

def _k_athlete_model() -> dict:
    return {
        "sport": "boxing",
        "status": "amateur",
        "tactical_style": "counter_striker",
        "primary_goal": "power",
        "key_goals": ["power", "speed"],
        "fatigue": "low",
        "weight_cut_pct": 3.4,
        "weight_cut_risk": True,
        "readiness_flags": [],
        "training_days": ["monday", "tuesday", "wednesday", "thursday", "friday", "sunday"],
        "support_work_days": ["monday"],
        "hard_sparring_days": ["thursday"],
        "weekly_frequency": 4,
    }


def test_case_k_production_regression_d17_strength_is_meaningful_but_reduced():
    # Faithful reproduction of the reported geometry: a boxing counter-striker,
    # power-primary athlete, low fatigue, moderate ~3.4% cut, training Mon-Fri +
    # Sun (no Saturday), support Monday, hard sparring Thursday, weekly freq 4,
    # with the strength session scheduled at D-17 (Tuesday).
    weekly_role_map = {
        "weeks": [
            {
                "phase": "SPP",
                "week_index": 3,
                "calendar_days": [
                    {"weekday": "monday", "d_day": 18},
                    {"weekday": "tuesday", "d_day": 17},
                    {"weekday": "wednesday", "d_day": 16},
                    {"weekday": "thursday", "d_day": 15},
                    {"weekday": "friday", "d_day": 14},
                    {"weekday": "sunday", "d_day": 12},
                ],
                "session_roles": [
                    {"role_key": "primary_strength_day", "category": "strength", "scheduled_day_hint": "tuesday"},
                    {"role_key": "hard_sparring_day", "category": "sparring", "scheduled_day_hint": "thursday"},
                ],
            }
        ]
    }
    candidate_pools = {
        "SPP": {
            "strength_slots": [
                _anchor_slot("Trap Bar Deadlift", "4 x 3 @ RPE 7", priority=1),
                _support_slot("Pallof Press", "3 x 8", priority=2),
            ]
        }
    }
    athlete_model = _k_athlete_model()

    apply_late_camp_role_morph(weekly_role_map)
    apply_effective_strength_prescriptions(
        weekly_role_map=weekly_role_map,
        candidate_pools=candidate_pools,
        athlete_model=athlete_model,
    )
    packet = build_stage2_finalizer_packet(
        stage2_payload={"weekly_role_map": weekly_role_map, "athlete_model": athlete_model},
        planning_brief={"weekly_role_map": weekly_role_map, "athlete_snapshot": athlete_model},
    )

    strength_role = next(
        role
        for week in packet["selected_plan"]["weekly_role_map"]["weeks"]
        for role in week["session_roles"]
        if role.get("role_key") == "primary_strength_day"
    )
    resolved = {item["name"]: item for item in strength_role["effective_strength_prescriptions"]}
    anchor = resolved["Trap Bar Deadlift"]

    # Meaningful but reduced: NOT the untouched 4 x 3 bank dose ...
    assert anchor["base_prescription"] == "4 x 3 @ RPE 7"
    assert anchor["effective_prescription"] == "3 x 3 @ RPE 6-7 max"
    assert anchor["dose_authority"] == "scheduled_countdown_overlay"
    # ... and NOT a band-primer-only fake strength session — real load remains.
    assert anchor["effective_loaded"] is True
    assert strength_role["effective_strength_envelope"]["loaded_allowed"] is True
    envelope = strength_role["effective_strength_envelope"]
    assert envelope["scheduled_d_day"] == 17
    assert envelope["max_sets"] == 3

    # The validator accepts the resolved dose and rejects the raw bank dose.
    ok = validate_stage2_output(
        planning_brief={"weekly_role_map": weekly_role_map},
        final_plan_text="D-17 (Tuesday) — Strength\n- Trap Bar Deadlift — 3 x 3 @ RPE 6-7\n",
    )
    assert "late_camp_effective_prescription_exceeded" not in {e["code"] for e in ok["errors"]}
    bad = validate_stage2_output(
        planning_brief={"weekly_role_map": weekly_role_map},
        final_plan_text="D-17 (Tuesday) — Strength\n- Trap Bar Deadlift — 4 x 3 @ RPE 7\n",
    )
    assert "late_camp_effective_prescription_exceeded" in {e["code"] for e in bad["errors"]}

# Hardened per-exercise enforcement regressions (production job
# c2aab317-4b6b-4bcd-8284-24429a0fd9aa recreated without database access).
def _brief_with_prescriptions(d_day: int, prescriptions: list[dict]) -> dict:
    envelope = {
        "scheduled_d_day": d_day,
        "loaded_allowed": any(item.get("effective_loaded") for item in prescriptions),
        "loaded_exercise_names": [item["name"] for item in prescriptions],
    }
    brief = _brief_with_envelope(d_day, envelope)
    role = brief["weekly_role_map"]["weeks"][0]["session_roles"][0]
    role["effective_strength_prescriptions"] = prescriptions
    return brief


def test_d16_mixed_lifts_use_their_own_effective_ceiling():
    prescriptions = [
        {"name": "Back Squat", "dose_role_kind": "anchor", "effective_loaded": True,
         "effective_max_sets": 3, "effective_max_reps": 3, "effective_rpe_cap": 7},
        {"name": "Romanian Deadlift", "dose_role_kind": "secondary", "effective_loaded": True,
         "effective_max_sets": 2, "effective_max_reps": 5, "effective_rpe_cap": 6},
    ]
    report = validate_stage2_output(
        planning_brief=_brief_with_prescriptions(16, prescriptions),
        final_plan_text=("D-16 (Tuesday) — Strength\n- Back Squat: 3 x 5 @ RPE 7\n"
                         "- Romanian Deadlift: 2 x 8 @ RPE 6-7\n"),
    )
    findings = [e for e in report["errors"] if e["code"] == "late_camp_effective_prescription_exceeded"]
    assert {item["exercise"] for item in findings} == {"Back Squat", "Romanian Deadlift"}
    assert report["is_valid"] is False


def test_working_dose_parser_ignores_earlier_warmup_dose():
    brief = _brief_with_prescriptions(16, [
        {"name": "Back Squat", "dose_role_kind": "anchor", "effective_loaded": True,
         "effective_max_sets": 3, "effective_max_reps": 3, "effective_rpe_cap": 7},
    ])
    report = validate_stage2_output(
        planning_brief=brief,
        final_plan_text="D-16 (Tuesday) — Strength\n- Back Squat: 2 x 10 warm-up, then 4 sets of 3 @ RPE 7\n",
    )
    finding = next(e for e in report["errors"] if e["code"] == "late_camp_effective_prescription_exceeded")
    assert "sets 4" in finding["violations"][0]


def test_no_loaded_band_ignores_negative_prose_but_blocks_a_working_dose():
    brief = _brief_with_prescriptions(10, [
        {"name": "Back Squat", "dose_role_kind": "anchor", "effective_loaded": False},
    ])
    prose = validate_stage2_output(planning_brief=brief,
        final_plan_text="D-10 (Tuesday) — Primer\n- No back squat today. Use breathing and mobility.\n")
    assert not any(e["code"] == "late_camp_effective_prescription_exceeded" for e in prose["errors"])
    loaded = validate_stage2_output(planning_brief=brief,
        final_plan_text="D-10 (Tuesday) — Primer\n- Back squat: 2 x 3 @ RPE 6\n")
    assert any(e["code"] == "late_camp_effective_prescription_exceeded" for e in loaded["errors"])


def test_two_strength_sessions_resolve_only_their_owned_slots():
    slots = [_anchor_slot("Back Squat", priority=1), _anchor_slot("Trap Bar Deadlift", priority=2)]
    slots[0]["session_index"] = 1
    slots[1]["session_index"] = 2
    role_map = {"weeks": [{"phase": "SPP", "calendar_days": [
        {"weekday": "tuesday", "d_day": 16}, {"weekday": "thursday", "d_day": 14}],
        "session_roles": [
            {"role_key": "primary_strength_day", "category": "strength", "scheduled_day_hint": "tuesday"},
            {"role_key": "secondary_strength_day", "category": "strength", "scheduled_day_hint": "thursday"},
        ]}]}
    apply_late_camp_role_morph(role_map)
    apply_effective_strength_prescriptions(weekly_role_map=role_map,
        candidate_pools={"SPP": {"strength_slots": slots}})
    roles = role_map["weeks"][0]["session_roles"]
    assert [x["name"] for x in roles[0]["effective_strength_prescriptions"]] == ["Back Squat"]
    assert [x["name"] for x in roles[1]["effective_strength_prescriptions"]] == ["Trap Bar Deadlift"]


def test_string_priority_selects_critical_loaded_anchor_first():
    secondary = _anchor_slot("Romanian Deadlift", priority=1)
    anchor = _anchor_slot("Back Squat", priority=2)
    secondary["priority"] = "high"
    anchor["priority"] = "critical"
    role = _resolve(16, [secondary, anchor])
    assert _by_name(role, "Back Squat")["dose_role_kind"] == "anchor"
    assert _by_name(role, "Romanian Deadlift")["dose_role_kind"] == "secondary"


def test_non_nxm_power_and_isometric_prescriptions_survive_no_loaded_band():
    power = _power_slot("Medicine Ball Throw", "3 throws each side")
    iso = _support_slot("Mid-thigh Isometric", "3 holds of 5 seconds")
    role = _resolve(5, [_anchor_slot(), power, iso])
    assert _by_name(role, "Medicine Ball Throw")["effective_prescription"] == "3 throws each side"
    assert _by_name(role, "Mid-thigh Isometric")["effective_prescription"] == "3 holds of 5 seconds"


def test_remorph_after_relocation_outside_window_clears_stale_d16_truth():
    role_map = {"weeks": [{"phase": "SPP", "calendar_days": [{"weekday": "tuesday", "d_day": 16}],
        "session_roles": [{"role_key": "primary_strength_day", "category": "strength", "scheduled_day_hint": "tuesday"}]}]}
    apply_late_camp_role_morph(role_map)
    role = role_map["weeks"][0]["session_roles"][0]
    assert role["scheduled_d_day"] == 16
    role_map["weeks"][0]["calendar_days"][0]["d_day"] = 18
    apply_late_camp_role_morph(role_map)
    for key in ("strength_dose_cap", "set_cap", "rep_cap", "rpe_cap", "scheduled_d_day",
                "effective_strength_prescriptions", "effective_strength_envelope"):
        assert key not in role
