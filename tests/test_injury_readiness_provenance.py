"""Contact readiness cannot silently become a whole-programme injury diagnosis."""
from copy import deepcopy

import pytest

from fightcamp.sparring_readiness import sparring_readiness_flags
from fightcamp.stage2_role_map import (
    _readiness_compression_floor, _apply_high_fatigue_week_compression,
    _boxing_crowded_role_priority, _select_boxing_crowded_week_non_spar_roles,
)


def _snapshot(history, **overrides):
    evidence = []
    flags = sparring_readiness_flags({"as_of": "2026-10-24", **history}, evidence=evidence)
    return {"readiness_flags": flags, "readiness_evidence": evidence,
            "injuries": ["Occasional pain"], "parsed_injuries": [{"severity": "low"}], **overrides}


@pytest.mark.parametrize("location", ["left knee", "right shoulder", "left ankle", "right wrist"])
@pytest.mark.parametrize("impact", ["", "not_limiting"])
def test_legacy_intake_default_is_contact_evidence_not_medical_severity(location, impact):
    row = {"id": "legacy-row", "source": "intake", "description": f"Sometimes my {location} hurts",
           "severity": "moderate", "severity_source": None, "status": "open"}
    if impact:
        row["description"] += f" [training_impact:{impact}]"
    before = deepcopy(row)
    model = _snapshot({"active_injuries": [row]})
    assert _readiness_compression_floor(model) == 0
    assert all(e["scope"] == "contact" for e in model["readiness_evidence"])
    assert row == before


@pytest.mark.parametrize("checkin, expected", [
    ({"pain": "manageable"}, 0), ({"pain": "high"}, 1),
    ({"active_injury": "worse"}, 1),
    ({"pain": "high", "training_day": "2026-10-01"}, 0),
    ({"active_injury": "worse", "training_day": "2026-10-25"}, 0),
])
def test_current_checkin_scope_and_recency(checkin, expected):
    row = {"training_day": "2026-10-24", **checkin}
    model = _snapshot({"checkins": [row]}, parsed_injuries=[{"severity": "low", "training_impact": "not_limiting"}])
    assert _readiness_compression_floor(model) == expected
    if expected:
        assert model["readiness_evidence"][0]["source"] == "today_checkins"
        assert model["readiness_evidence"][0]["training_day"] == "2026-10-24"


def test_latest_checkin_wins_over_an_older_worsening_report():
    model = _snapshot({"checkins": [
        {"training_day": "2026-10-23", "active_injury": "worse"},
        {"training_day": "2026-10-24", "pain": "none", "active_injury": "better"},
    ]})
    assert _readiness_compression_floor(model) == 0


@pytest.mark.parametrize("row", [
    {"severity": "high", "description": "[training_impact:not_limiting]"},
    {"severity": "moderate", "manual_severity": "moderate"},
    {"severity": "low", "manual_severity": "high", "description": "[training_impact:not_limiting]"},
    {"severity": "moderate", "severity_source": "clinician"},
    {"severity": "low", "latest_reported_status": "worse"},
    {"severity": "low", "injury_type": "concussion"},
])
def test_independent_persisted_safety_evidence_cannot_be_softened(row):
    model = _snapshot({"active_injuries": [{"source": "intake", **row}]})
    assert _readiness_compression_floor(model) == 1
    assert model["readiness_evidence"][0]["scope"] == "training_capacity"


def test_unproven_or_stale_flag_is_not_global_capacity_evidence():
    model = {"readiness_flags": ["moderate_injury"], "parsed_injuries": [{"severity": "low"}]}
    assert _readiness_compression_floor(model) == 0
    assert _readiness_compression_floor({**model, "fatigue": "high"}) == 1


def test_multiple_injuries_keep_the_restrictive_independent_one():
    model = _snapshot({"active_injuries": [
        {"source": "intake", "severity": "moderate", "description": "Occasional knee pain"},
        {"source": "clinician", "severity": "severe", "description": "Shoulder injury"},
    ]})
    assert _readiness_compression_floor(model) == 1
    assert {e["scope"] for e in model["readiness_evidence"]} == {"contact", "training_capacity"}


def _role(key, category="strength", system=""):
    return {"role_key": key, "category": category, "preferred_system": system}


@pytest.mark.parametrize("goal, expected", [("strength", "primary_strength_day"),
    ("power", "primary_strength_day"), ("speed", "primary_strength_day"),
    ("conditioning", "aerobic_base_day")])
def test_semantic_must_keep_uses_goal_priority_with_one_real_slot(goal, expected):
    # One non-spar slot, with a REAL fatigue reduction. The phase's semantic
    # primary_strength requirement must receive the same rank as aerobic.
    athlete = {"sport": "mma", "primary_goal": goal, "key_goals": [goal], "fatigue": "high",
               "training_frequency": 4, "training_days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Sunday"],
               "hard_sparring_days": ["Wednesday", "Sunday"]}
    week = {"phase": "GPP", "must_keep": ["primary_strength", "aerobic"]}
    roles = [_role("primary_strength_day"), _role("aerobic_base_day", "conditioning", "aerobic"),
             _role("hard_sparring_day", "sparring"), _role("hard_sparring_day", "sparring")]
    kept, _ = _apply_high_fatigue_week_compression(week, roles, [], athlete)
    assert len(kept) == 3
    assert expected in [r["role_key"] for r in kept]


@pytest.mark.parametrize("key", ["primary_strength_day", "structural_strength_day", "neural_plus_strength_day"])
def test_crowded_week_recognizes_the_same_semantic_anchor(key):
    anchor = _role(key)
    support = _role("aerobic_base_day", "conditioning", "aerobic")
    must_keep = {"primary_strength", "aerobic"}
    assert _boxing_crowded_role_priority(anchor, must_keep) == 100
    selected = _select_boxing_crowded_week_non_spar_roles([support, anchor], allowed_non_spar=1, must_keep=must_keep)
    assert selected == [anchor]


@pytest.mark.parametrize("impact,severity,expected", [
    ("", "low", 0), ("not_limiting", "low", 0),
    ("limiting", "moderate", 1), ("cant_train", "high", 1),
])
def test_current_intake_impact_remains_authoritative_with_unverified_tracker(impact, severity, expected):
    model = _snapshot({"active_injuries": [{"source": "intake", "severity": "moderate"}]},
                      parsed_injuries=[{"severity": severity, "training_impact": impact}])
    assert _readiness_compression_floor(model) == expected


@pytest.mark.parametrize("remaining_coach", [False, True])
def test_capacity_reason_is_not_a_permanent_repair_veto(remaining_coach):
    from fightcamp.goal_repair_effective_contact_policy import effective_goal_repair_compression_state

    week = {"appointment_budget": {"requested": 4}, "session_roles": [
        {"role_key": "light_combat_day", "category": "technical", "scheduled_countdown_label": "D-24"}
    ] if remaining_coach else [], "intentional_compression": {"active": False}}
    suppressed = [{"compression_reason_codes": ["coach_owned_appointment_capacity"]}]
    assert effective_goal_repair_compression_state(week, suppressed)[1] == []



@pytest.mark.parametrize("sport", ["mma", "boxing"])
def test_light_coach_days_do_not_consume_app_compression_budget(sport):
    athlete = {"sport": sport, "primary_goal": "strength", "key_goals": ["strength"],
               "training_frequency": 4, "training_days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Sunday"],
               "support_work_days": ["Tuesday", "Friday"], "hard_sparring_days": ["Wednesday", "Sunday"]}
    roles = [_role("primary_strength_day"), _role("aerobic_base_day", "conditioning", "aerobic"),
             _role("hard_sparring_day", "sparring"), _role("hard_sparring_day", "sparring")]
    week = {"phase": "GPP", "must_keep": ["primary_strength", "aerobic"]}
    kept, _ = _apply_high_fatigue_week_compression(week, roles, [], athlete)
    assert {r["role_key"] for r in kept} >= {"primary_strength_day", "aerobic_base_day"}
    assert "coach_owned_appointment_capacity" not in (week.get("intentional_compression") or {}).get("reason_codes", [])


def test_legacy_fatigue_reason_keeps_the_true_cause_of_compression():
    from fightcamp.stage2_role_map import _high_fatigue_compression_reason_codes

    athlete = {"fatigue": "high", "injuries": ["Occasional knee pain"], "parsed_injuries": [{"severity": "low"}]}
    assert _high_fatigue_compression_reason_codes(athlete) == ["high_fatigue"]



def test_stale_capacity_ledger_cannot_justify_goal_deferral():
    from fightcamp.goal_preservation import _deferral_constraints, classify_goal_preservation
    from test_goal_preservation import _brief

    brief = _brief(roles=[])
    week = brief["weekly_role_map"]["weeks"][0]
    week["appointment_budget"] = {"requested": 4}
    week["suppressed_roles"] = [{"category": "strength", "role_key": "primary_strength_day",
        "compression_reason_codes": ["weekly_appointment_capacity"]}]
    entry = next(e for e in classify_goal_preservation(brief["athlete_snapshot"]) if e["goal"] == "strength")
    assert _deferral_constraints(entry, brief, [{"min_d_day": 14, "max_d_day": 20}]) == []



def test_unverified_injury_ledger_cannot_veto_recovery_or_justify_primary_loss():
    from fightcamp.goal_preservation import _deferral_constraints, classify_goal_preservation, validate_goal_preservation
    from test_goal_preservation import _brief, _role, _resolve

    brief = _brief(roles=[])
    brief["athlete_snapshot"].update(primary_goal="strength", key_goals=["strength"],
        parsed_injuries=[{"severity": "low", "severity_source": "injury_type_default"}],
        readiness_flags=["injury_management", "moderate_injury"])
    brief["priority_focus"] = {"primary_goal": "strength"}
    week = brief["weekly_role_map"]["weeks"][0]
    week["goal_repair_candidates"] = [_role()]
    week["suppressed_roles"] = [{"category": "strength", "role_key": "strength_touch_day",
        "compression_reason_codes": ["injury_management"]}]
    entry = classify_goal_preservation(brief["athlete_snapshot"])[0]
    assert _deferral_constraints(entry, brief, [{"min_d_day": 14, "max_d_day": 20}]) == []
    _resolve(brief)
    assert brief["goal_preservation"][0]["satisfied"]
    assert validate_goal_preservation(brief) == []
