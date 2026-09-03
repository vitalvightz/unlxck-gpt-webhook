"""Goal survival is an effective-stimulus contract, not a role-name check."""
from copy import deepcopy

import pytest

from fightcamp.goal_preservation import (
    classify_goal_preservation, collect_goal_evidence, reconcile_goal_preservation,
    validate_goal_preservation,
)
from fightcamp.late_camp_role_morph import apply_late_camp_role_morph
from fightcamp.prescription_resolver import apply_effective_strength_prescriptions
from fightcamp.stage2_finalizer_packet import build_stage2_finalizer_packet
from fightcamp.stage2_payload import _compress_short_camp_priorities, build_planning_brief
from fightcamp.stage2_pipeline import build_stage2_retry
from fightcamp.stage2_validator import validate_stage2_output


def _slot(name="Deadlift", quality="anchor_loaded", **changes):
    return {"slot_id": name, "session_index": 1, "role": "hinge",
            "quality_class": quality, "anchor_capable": True,
            "selected": {"name": name, "quality_class": quality, "prescription": "3 x 3 @ RPE 7",
                         "movement_patterns": ["speed"] if quality == "anchor_power" else ["hinge"], **changes}}


def _role(day=18, **changes):
    return {"role_key": "strength_touch_day", "category": "strength", "strength_session_index": 1,
            "session_index": 1, "scheduled_day_hint": "Monday", "scheduled_countdown_label": f"D-{day}", **changes}


def _brief(days=20, roles=None, slots=None):
    roles = [_role()] if roles is None else roles
    day = int(roles[0]["scheduled_countdown_label"][2:]) if roles else 18
    return {
        "athlete_snapshot": {"key_goals": ["speed", "strength"], "primary_goal": "speed",
                             "days_until_fight": days, "fatigue": "low", "training_frequency": 4},
        "priority_focus": {"primary_goal": "speed", "secondary_goals": ["strength"]},
        "weekly_role_map": {"weeks": [{"week_index": 1, "phase": "SPP",
            "declared_training_days": ["Monday", "Thursday"],
            "calendar_days": [{"weekday": "monday", "d_day": day}, {"weekday": "thursday", "d_day": 15}],
            "session_roles": roles, "suppressed_roles": []}]},
        "candidate_pools": {"SPP": {"strength_slots": slots if slots is not None else [
            _slot(), _slot("Medicine Ball Rotational Slam", "anchor_power")]}},
        "restrictions": [],
    }


def _resolve(brief):
    apply_late_camp_role_morph(brief["weekly_role_map"])
    apply_effective_strength_prescriptions(weekly_role_map=brief["weekly_role_map"],
        candidate_pools=brief["candidate_pools"], athlete_model=brief["athlete_snapshot"])
    return reconcile_goal_preservation(brief)


def _goal(brief, goal):
    return next(entry for entry in brief["goal_preservation"] if entry["goal"] == goal)


def test_normal_camp_primary_and_secondary_have_explicit_states_and_real_evidence():
    brief = _resolve(_brief())
    assert [(e["goal"], e["state"]) for e in brief["goal_preservation"]] == [("speed", "build"), ("strength", "maintain")]
    assert _goal(brief, "strength")["evidence"][0]["name"] == "Deadlift"
    assert _goal(brief, "strength")["satisfied"]
    assert validate_goal_preservation(brief) == []


@pytest.mark.parametrize("days", [0, 1, 3, 5, 7, 8, 20, 56])
def test_all_timelines_classify_every_selected_goal(days):
    athlete = _brief(days)["athlete_snapshot"]
    result = _compress_short_camp_priorities(athlete)
    assert {entry["goal"] for entry in result["goal_preservation"]} == {"speed", "strength"}
    assert result["is_short_camp"] is (days <= 7)
    if days <= 7:
        assert 1 <= len(result["primary_targets"]) <= 2
        assert len(result["maintenance_targets"]) <= 1


def test_real_build_planning_brief_wires_contract_after_effective_resolution():
    source = _brief()
    brief = build_planning_brief(
        athlete_model={**source["athlete_snapshot"], "sport": "mma", "training_days": ["Monday", "Thursday"],
                       "camp_length_weeks": 3},
        restrictions=[], candidate_pools=source["candidate_pools"], omission_ledger={}, rewrite_guidance={},
        phase_briefs={"SPP": {"objective": "fight transfer", "session_counts": {"strength": 1},
                              "emphasize": [], "deprioritize": [], "risk_flags": [], "selection_guardrails": {}}},
    )
    assert brief["priority_focus"]["primary_goal"] == "speed"
    assert brief["priority_focus"]["secondary_goals"] == ["strength"]
    assert brief["goal_preservation_version"] == "goal_preservation.v1"
    assert brief["compressed_priorities"]["goal_preservation"] == brief["goal_preservation"]


def test_removed_role_is_restored_only_on_legal_day_and_inside_session_budget():
    brief = _brief(roles=[])
    week = brief["weekly_role_map"]["weeks"][0]
    week["goal_repair_candidates"] = [_role()]
    week["suppressed_roles"] = [{"category": "strength", "role_key": "strength_touch_day"}]
    _resolve(brief)
    assert len(brief["weekly_role_map"]["weeks"][0]["session_roles"]) == 1
    assert _goal(brief, "speed")["repair_attempts"][0]["result"] == "restored"
    assert validate_goal_preservation(brief) == []


@pytest.mark.parametrize("quality", ["anchor_power", "rehab_support", "support_isometric", "support_accessory"])
def test_strength_role_name_and_old_intent_do_not_make_nonstrength_work_qualify(quality):
    brief = _brief(slots=[_slot("Medicine Ball Rotational Slam", quality)])
    _resolve(brief)
    entry = _goal(brief, "strength")
    assert entry["evidence"] == []
    assert not entry["satisfied"]
    assert brief["weekly_role_map"]["weeks"][0]["session_roles"][0]["intent_validation"]["satisfied"] is False
    assert any(error["goal"] == "strength" for error in validate_goal_preservation(brief))


def test_effective_no_loading_overrides_loaded_candidate_and_cap_name():
    brief = _brief(roles=[_role(13)])
    apply_late_camp_role_morph(brief["weekly_role_map"])
    apply_effective_strength_prescriptions(weekly_role_map=brief["weekly_role_map"], candidate_pools=brief["candidate_pools"])
    role = brief["weekly_role_map"]["weeks"][0]["session_roles"][0]
    role["effective_strength_envelope"]["loaded_allowed"] = False
    reconcile_goal_preservation(brief)
    assert not _goal(brief, "strength")["evidence"]


def test_sheyi_like_suppressed_gpp_then_power_only_d13_explicitly_defers_strength():
    brief = _brief(days=26, roles=[_role(13)], slots=[_slot("Medicine Ball Rotational Slam", "anchor_power")])
    brief["athlete_snapshot"].update(sport="mma", weaknesses=["footwork", "power"],
        equipment=["barbell", "kettlebells", "medicine_ball"], hard_sparring_days=["Tuesday", "Friday"])
    week = brief["weekly_role_map"]["weeks"][0]
    week["calendar_days"] = [{"weekday": "monday", "d_day": 13}, {"weekday": "thursday", "d_day": 18}, {"weekday": "friday", "d_day": 25}]
    week["suppressed_roles"] = [{"category": "strength", "role_key": "primary_strength_day",
                                 "compression_reason_codes": ["two_hard_spar_days"]}]
    _resolve(brief)
    strength = _goal(brief, "strength")
    assert strength["state"] == "defer"
    assert strength["satisfied"] is False
    assert strength["evidence"] == []
    assert "calendar_capacity" in strength["reason_codes"]
    assert not any(e["goal"] == "strength" for e in validate_goal_preservation(brief))
    assert week["session_roles"][0]["effective_strength_envelope"]["loaded_allowed"] is False


@pytest.mark.parametrize("day", [0, 1, 3, 7])
def test_final_week_legitimate_strength_deferral(day):
    brief = _brief(days=day, roles=[_role(day)])
    _resolve(brief)
    strength = _goal(brief, "strength")
    assert strength["state"] == "defer"
    assert "fight_proximity" in strength["reason_codes"]
    assert not any(e["goal"] == "strength" for e in validate_goal_preservation(brief))


def test_secondary_preserved_when_primary_readiness_reduces_to_maintenance():
    initial = classify_goal_preservation({**_brief()["athlete_snapshot"], "fatigue": "high"})
    assert [e["state"] for e in initial] == ["maintain", "maintain"]
    assert all("high_fatigue" in e["reason_codes"] for e in initial)


def test_build_and_maintain_with_no_effective_evidence_block_stage2_release():
    brief = _resolve(_brief(roles=[]))
    report = validate_stage2_output(planning_brief=brief, final_plan_text="Strength and speed are perfectly preserved.")
    assert {e["goal"] for e in report["errors"] if e["code"] == "goal_preservation_failed"} == {"speed", "strength"}
    result = build_stage2_retry(stage1_result={"planning_brief": brief}, final_plan_text="Ready to fight.")
    assert result["status"] != "PASS"
    assert result["requires_planner_regeneration"]
    assert result["repair_prompt"] is None


def test_missing_contract_missing_goal_and_forged_deferral_all_fail():
    brief = _resolve(_brief())
    brief["goal_preservation"] = [e for e in brief["goal_preservation"] if e["goal"] != "strength"]
    assert any(e["goal"] == "strength" for e in validate_goal_preservation(brief))
    brief = _resolve(_brief(roles=[]))
    strength = _goal(brief, "strength")
    strength.update(state="defer", reason_codes=["injury_constraint"], constraints=[{"reason_code": "injury_constraint"}])
    assert any(e["goal"] == "strength" for e in validate_goal_preservation(brief))


def test_mutation_after_reconciliation_is_detected_instead_of_trusting_cached_evidence():
    brief = _resolve(_brief(roles=[_role(16)]))
    brief["weekly_role_map"]["weeks"][0]["session_roles"][0]["effective_strength_prescriptions"][0]["effective_loaded"] = False
    assert any(e["goal"] == "strength" for e in validate_goal_preservation(brief))


def test_injury_restriction_and_session_cap_are_authoritative():
    brief = _brief(roles=[], slots=[_slot(restriction_tags=["loaded_rotation"])])
    week = brief["weekly_role_map"]["weeks"][0]
    week["goal_repair_candidates"] = [_role()]
    brief["restrictions"] = [{"restriction": "loaded rotation", "strength": "avoid"}]
    _resolve(brief)
    assert brief["weekly_role_map"]["weeks"][0]["session_roles"] == []
    assert not _goal(brief, "strength")["satisfied"]


def test_calendar_sandwich_rule_is_consumed_without_being_overridden():
    brief = _brief(roles=[])
    week = brief["weekly_role_map"]["weeks"][0]
    week["calendar_days"] = [{"weekday": "tuesday", "d_day": 20}, {"weekday": "wednesday", "d_day": 19}, {"weekday": "friday", "d_day": 17}]
    week["declared_training_days"] = ["Wednesday"]
    week["hard_sparring_plan"] = [{"day": day, "status": "hard_as_planned", "effective_load": "hard"} for day in ("Tuesday", "Friday")]
    week["goal_repair_candidates"] = [_role()]
    _resolve(brief)
    assert not brief["weekly_role_map"]["weeks"][0]["session_roles"]
    assert any(a["result"] == "calendar_forbidden" for a in _goal(brief, "strength")["repair_attempts"])


def test_determinism_and_finalizer_packet_preserve_structured_contract():
    original = _brief()
    first, second = _resolve(deepcopy(original)), _resolve(deepcopy(original))
    assert first == second
    snapshot = deepcopy(first)
    packet = build_stage2_finalizer_packet(stage2_payload={}, planning_brief=first)
    assert packet["selected_plan"]["goal_preservation"] == first["goal_preservation"]
    assert first == snapshot
    assert "meaningful_strength" in " ".join(packet["hard_rules"])


def test_recovery_does_not_satisfy_conditioning_and_arbitrary_prose_cannot_create_evidence():
    brief = _brief(roles=[_role(category="recovery", role_key="recovery_reset_day", duration_min=20)])
    brief["athlete_snapshot"]["key_goals"] = ["conditioning"]
    brief["priority_focus"] = {"primary_goal": "conditioning"}
    brief["final_plan_text"] = "Extremely effective conditioning and maximal strength."
    evidence = collect_goal_evidence(brief)
    assert not any("energy_system_training" in e["intents"] for e in evidence)


def test_build_requires_recurring_coverage_not_one_ancient_exposure():
    brief = _brief(days=56)
    _resolve(brief)
    assert _goal(brief, "speed")["missing_coverage"]
    assert any(e["goal"] == "speed" for e in validate_goal_preservation(brief))


def test_direct_countdown_uses_visible_sequence_not_earlier_weekly_mirror():
    brief = _brief(days=10)
    brief["late_fight_session_sequence"] = []
    reconcile_goal_preservation(brief)
    assert not _goal(brief, "strength")["evidence"]


@pytest.mark.parametrize("replacement", ["", "- Medicine Ball Rotational Slam: 3 x 3 @ RPE 7", "- Deadlift: 1 x 1 @ RPE 3", "- Deadlift: 3 x 3 @ RPE 2"])
def test_rendering_cannot_drop_or_reduce_a_deterministic_strength_witness(replacement):
    brief = _resolve(_brief())
    report = validate_stage2_output(planning_brief=brief, final_plan_text=f"D-18 Monday\n{replacement}\nD-0\nFight day protocol.")
    assert any(e["code"] == "goal_preservation_render_mismatch" and e["exercise"] == "Deadlift" for e in report["errors"])


def test_rendering_preserves_named_witnesses_and_dose_without_prose_goal_claims():
    brief = _resolve(_brief())
    text = "D-18 Monday\n- Deadlift: 3 x 3 @ RPE 7\n- Medicine Ball Rotational Slam: 3 x 3 @ RPE 7\nD-0\nFight day protocol."
    report = validate_stage2_output(planning_brief=brief, final_plan_text=text)
    assert not any(e["code"].startswith("goal_preservation") for e in report["errors"])


def test_primary_cannot_be_silently_downgraded_and_empty_prose_cannot_forge_a_deferral():
    brief = _resolve(_brief())
    _goal(brief, "speed")["state"] = "maintain"
    assert any(e["goal"] == "speed" for e in validate_goal_preservation(brief))


def test_strength_force_isometric_needs_explicit_maintenance_governance():
    for meaningful in (False, True):
        brief = _brief(slots=[_slot("Pin Pull", "anchor_force_isometric", real_strength_maintenance=meaningful)])
        _resolve(brief)
        assert _goal(brief, "strength")["satisfied"] is meaningful


def test_loaded_exercise_at_rehab_intensity_is_not_strength_maintenance():
    brief = _brief(slots=[_slot(prescription="3 x 3 @ RPE 2")])
    _resolve(brief)
    assert not _goal(brief, "strength")["evidence"]


def test_selected_power_class_overrides_stale_slot_strength_class():
    slot = _slot()
    slot["selected"]["quality_class"] = "anchor_power"
    brief = _resolve(_brief(slots=[slot]))
    assert not _goal(brief, "strength")["evidence"]


def test_explicit_late_window_eligibility_is_not_bypassed_by_goal_evidence():
    brief = _resolve(_brief(slots=[_slot(late_windows=["d13_to_d8"])]))
    assert not _goal(brief, "strength")["evidence"]


def test_conditioning_maintenance_insert_is_not_mistaken_for_build_or_recovery():
    role = _role(category="support_insert", role_key="aerobic_shadow_flow", duration_min=[8, 12],
                 support_insert_category="conditioning_maintenance")
    evidence = collect_goal_evidence(_brief(roles=[role]))
    assert any("energy_system_training" in e["intents"] and not e["development_quality"] for e in evidence)
    assert not any("meaningful_strength" in e["intents"] for e in evidence)


def test_next_exercise_dose_cannot_pay_for_omitted_strength_dose():
    brief = _resolve(_brief())
    text = "D-18 Monday\n- Deadlift\n- Medicine Ball Rotational Slam: 3 x 3 @ RPE 7\nD-0\nFight day protocol."
    report = validate_stage2_output(planning_brief=brief, final_plan_text=text)
    assert any(e["code"] == "goal_preservation_render_mismatch" and e["exercise"] == "Deadlift" for e in report["errors"])


def test_wrapped_strength_dose_stays_bound_to_selected_exercise():
    brief = _resolve(_brief())
    text = "D-18 Monday\n- Deadlift\n  3 x 3\n  RPE: 7\n- Medicine Ball Rotational Slam: 3 x 3 @ RPE 7\nD-0\nFight day protocol."
    report = validate_stage2_output(planning_brief=brief, final_plan_text=text)
    assert not any(e["code"].startswith("goal_preservation") for e in report["errors"])
